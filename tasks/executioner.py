import asyncio
import json
import random

import curl_cffi
from aiohttp.client_exceptions import ClientHttpProxyError, ClientProxyConnectionError
from curl_cffi.requests.exceptions import ProxyError, SSLError, Timeout
from web3.exceptions import BadFunctionCallOutput

from core.evm_contracts import EVMContracts
from core.db_utils.models import Account, RouteAction
from core.logger import get_logger
from core.init_settings import settings
from libs.blockchains.eth_async.applications.jumper_exchange.jumper_client import JumperExchange
from libs.blockchains.eth_async.applications.nexus_bridge.nexus_bridge import NexusBridge
from libs.blockchains.eth_async.applications.uniswap.uniswap_client import Uniswap
from libs.blockchains.eth_async.data.models import Networks, CommonValues
from libs.blockchains.eth_async.ethclient import NetworkClient
from libs.blockchains.omnichain_models import TokenAmount
from libs.blockchains.eth_async.exceptions import InsufficientFundsException
from libs.cex.withdraw import CexWithdraw
from utils.utils import randfloat, excname
from tasks.controller import Controller


class Executioner:
    def __init__(self, account: Account, total_account_num: int, action_num: int, total_actions: int):
        self.account = account
        self.try_num = 1
        self.action_num = action_num

        self.log_context = {
            "total_account_num": total_account_num,
            "action_num": action_num,
            "total_actions": total_actions,
            "account_name": account.name,
            "account_address": account.evm_address,
            "try_num": self.try_num,
        }

        self.logger = get_logger(
            class_name=self.__class__.__name__,
            **self.log_context
        )

    @staticmethod
    def random_to_none(action_params: dict, key: str):
        if action_params[key] == "random":
            action_params[key] = None
        return action_params

    async def sleep(self, time: float = 10, message: str = ""):
        self.logger.info(f"Sleeping for 💤{time}💤 seconds{message}.")
        await asyncio.sleep(time)

    async def gas_control(self, controller: Controller, network_name: str):
        if settings.gas.gas_control:
            network_client = getattr(controller.eth_client, network_name)
            maximum_gwei = settings.gas.maximum_gwei_dict[network_name]
            gas_price = await network_client.transactions.gas_price()
            gwei = gas_price.Wei / 10 ** 9
            if gwei > maximum_gwei:
                for _ in range(settings.general.number_of_retries):
                    self.logger.warning(f"High gas in {network_name.capitalize()}: {gwei} Gwei")
                    await self.sleep(settings.gas.gas_retry_delay)
                    gas_price = await network_client.transactions.gas_price()
                    gwei = gas_price.Wei / 10 ** 9
                    if gwei < maximum_gwei:
                        self.logger.success(f"Current gas price in {network_name.capitalize()} is good: {gwei} Gwei")
                        return True
                else:
                    return False

            else:
                self.logger.success(f"Current gas price in {network_name.capitalize()} is good: {gwei} Gwei")
                return True


    async def check_balance_and_withdraw(self, controller: Controller, network_name: str, action_params: dict) -> bool:
        network_client: NetworkClient = getattr(controller.eth_client, network_name)
        native_balance = await network_client.wallet.balance()

        min_balance = None
        for key in action_params["withdraw_on_min_amount_params"]:
            if "min_eth" in key and network_name in key:
                min_balance = action_params["withdraw_on_min_amount_params"][key]

        if min_balance is None:
            self.logger.error(f"Check your preset. Not found minimum balance in [[withdraw_on_min_amount_params]] block"
                              f" for network {network_name.capitalize()}")
            return False

        if float(native_balance.Ether) >= min_balance:
            self.logger.success(f"Native balance is {native_balance.Ether} {network_client.network.coin_symbol}")
            return True

        self.logger.warning(f"Native balance is {native_balance.Ether} {network_client.network.coin_symbol} "
                            f"less than {min_balance} {network_client.network.coin_symbol}")

        # here goes withdraw

        withdraw_amounts = None
        for key in action_params["withdraw_on_min_amount_params"]:
            if "withdraw_eth" in key and network_name in key:
                withdraw_amounts = action_params["withdraw_on_min_amount_params"][key]

        if not withdraw_amounts:
            self.logger.error(f"Check your preset. Not found withdraw amounts in [[withdraw_on_min_amount_params]] block"
                              f" for network {network_name.capitalize()}")
            return False

        cex_name = random.choice(action_params["withdraw_on_min_amount_params"]["cex_to_refill"]).lower()
        withdraw_amount = randfloat(*withdraw_amounts, step=0.0000001)

        cex_withdraw_client = CexWithdraw(cex_name, self.log_context)
        return await cex_withdraw_client.withdraw(withdraw_amount, network_name, network_client)


    def get_function(self, func_name: str):
        return self.__getattribute__(func_name)

    async def execute_action(self, action: RouteAction):
        action_params = json.loads(action.params.action_params) if action.params else {}

        action_type = action.action_type.lower()
        project_type = action_type.split("_")[0]
        if "random_swap" in action_type:
            project_type = random.choice(["uniswap", "jumper"])

        action_function = self.get_function(f"execute_{project_type}_actions")

        async with Controller(self.account, self.log_context) as controller:
            while self.try_num <= settings.general.number_of_retries:
                self.log_context["try_num"] = self.try_num
                self.logger = get_logger(class_name=self.__class__.__name__, **self.log_context)
                try:
                    self.logger.info(f"Starting action '{action.action_name}'")
                    result = await action_function(action_type, action_params, controller)

                    if result is True:
                        self.logger.success(f"Completed action {action.action_name}")
                    elif isinstance(result, dict):
                        for key, value in result.items():
                            if "insufficient" in value.lower():
                                self.logger.error(f"Failed action {action.action_name} with reason: {value}")
                                return False

                        self.logger.success(f"Completed action {action.action_name}: {result}")
                    else:
                        self.logger.error(f"Failed action {action.action_name} with reason: {result}")

                    return result

                except (ProxyError, Timeout, SSLError, curl_cffi.requests.exceptions.ConnectionError, # curl_cffi
                        ClientHttpProxyError, ClientProxyConnectionError) as e: # aiohttp
                    self.logger.error(f"{excname(e)} {str(e)}")
                    await controller.change_proxy()

                except InsufficientFundsException:
                    self.logger.error(f"Insufficient funds for transaction in action {action.action_type}")
                    return False

                except BadFunctionCallOutput:
                    self.logger.error(f"{excname(e)} {str(e)}")
                    if "uniswap" in action_type:
                        self.logger.error(f"Check provided token addresses: {action_params['swap_token_addresses']},"
                                          f" wrong address or token is not in desired Uniswap chain")
                        return False

                except Exception as e:
                    if settings.logging.debug_logging:
                        self.logger.exception(f"{excname(e)}. Action {action.action_type} failed: {str(e)}")
                    else:
                        self.logger.error(f"{excname(e)}. Action {action.action_type} failed: {str(e)}")
                    self.try_num += 1
                    await self.sleep(settings.general.retry_delay)

            else:
                return False # this is only if @BaseController.retry is used

    usdc_networks_mapping = {
        "base": EVMContracts.USDC_Base,
        "optimism": EVMContracts.USDC_Optimism,
        "arbitrum": EVMContracts.USDC_Arbitrum,
    }

    async def execute_jumper_actions(self, action_type: str, action_params: dict, controller: Controller):
        action_network = action_type.split("_")[-1]
        if action_network == "random":
            action_network = random.choice(action_params["swap"]["random_networks_to_swap"])
            self.logger.info(f"Selected random Jumper network: {action_network.capitalize()}")

        gas_result = await self.gas_control(controller, action_network)
        if not gas_result:
            self.logger.error(f"Oops, gas is still too high, quitting action")
            return False

        balance_check = await self.check_balance_and_withdraw(controller, action_network, action_params)
        if not balance_check:
            self.logger.error(f"Oops, balance is still too low, quitting action")
            return False

        jumper = JumperExchange(controller, self.log_context)
        jumper.use_network(action_network)

        swap_params = action_params.get("swap")

        results = {}

        if "swap" in action_type:
            chain_swap_params = swap_params.get(action_network)

            if isinstance(chain_swap_params, dict):
                return await self.jumper_swap(jumper, chain_swap_params, action_params, results)
            elif isinstance(chain_swap_params, list):
                for token_params in chain_swap_params:
                    results = await self.jumper_swap(jumper, token_params, action_params, results)

        return results

    async def jumper_swap(self, jumper, token_params, action_network, results):
        result_string = f"{action_network} from {token_params["from_token"]} to {token_params["to_token"]}"

        try:
            swap_amount = await self.get_evm_swap_amount(jumper.network_client,
                                                         token_params["from_token"], token_params["amount"])
            results[result_string] = await jumper.swap(swap_amount,
                                                       token_params["from_token"],
                                                       token_params["to_token"],
                                                       token_params["slippage"] / 100)

            if token_params["swap_mode"] == "to_and_from":
                if token_params["to_token"] == "native":
                    raise Exception(f"You are trying to swap back all native into token {token_params['from_token']}")

                swap_amount = await jumper.network_client.wallet.balance(token_params["to_token"])
                result_string = f"{action_network} from {token_params["to_token"]} to {token_params["from_token"]}"
                results[result_string] = await jumper.swap(swap_amount,
                                                           token_params["to_token"],
                                                           token_params["from_token"],
                                                           token_params["slippage"] / 100)
        except InsufficientFundsException as e:
            self.logger.error(f"{excname(e)} {str(e)}")
            results[result_string] = "Insufficient funds"

        return results

    async def get_evm_swap_amount(self, network_client: NetworkClient, token: str, swap_amounts: list[float | str]):
        token = token if token.lower() != "native" else None
        decimals = await network_client.transactions.get_decimals(token) if token else 18
        balance = await network_client.wallet.balance(token)
        self.logger.debug(f"Token balance: {balance}, token: {token}")
        if balance.Ether < 0.00000001:
            raise InsufficientFundsException(f"Insufficient funds for token {token}, balance is {balance}")

        if all(isinstance(amount, str) for amount in swap_amounts):
            swap1 = int(swap_amounts[0])
            swap2 = int(swap_amounts[1])
            if swap1 < 0 or swap2 < 0 or swap1 > swap2 or swap1 > 100 or swap2 > 100:
                raise Exception(f"Incorrect percentage for swap: {swap_amounts}")

            swap_percent = randfloat(swap1 / 100, swap2 / 100, 0.00000001)
            return TokenAmount(float(balance.Ether) * swap_percent, decimals, False)

        elif all(isinstance(amount, float) for amount in swap_amounts):
            amount = randfloat(*swap_amounts, step=0.00000001)
            amount = TokenAmount(amount, decimals, False)
            if amount < balance:
                token_str = token if token else "native"
                self.logger.error(f"Tried to swap {amount} {token_str} but balance is {balance} {token_str}")
                raise InsufficientFundsException
            return amount

        else:
            raise Exception(f"Swap amounts must be str or float: {swap_amounts}")

    async def execute_nexus_actions(self, action_type, action_params: dict, controller: Controller):
        action_network = action_type.split("_")[-1]
        nexus_bridge_params = action_params["nexus_bridge_params"]
        if action_network == "biggest":
            biggest_balance_network, biggest_balance = await self.get_biggest_usdc_balance(controller,
                                                        nexus_bridge_params["networks_to_check_balance_for_biggest"])
            self.logger.info(f"Biggest USDC balance: {biggest_balance} in network {biggest_balance_network.capitalize()}")

            action_network = biggest_balance_network

        gas_result = await self.gas_control(controller, action_network)
        if not gas_result:
            self.logger.error(f"Oops, gas is still too high, quitting action")
            return False

        balance_check = await self.check_balance_and_withdraw(controller, action_network, action_params)
        if not balance_check:
            self.logger.error(f"Oops, balance is still too low, quitting action")
            return False

        dest_networks_list: list = nexus_bridge_params["networks_to_bridge_to"]
        if action_network in dest_networks_list:
            dest_networks_list.remove(action_network)

        rand_dest_network = random.choice(nexus_bridge_params["networks_to_bridge_to"])
        # self.logger.info(f"Starting to bridge {action_type} {action_params}")
        dest_network = Networks.get_network_by_name(rand_dest_network)

        nexus = NexusBridge(controller, self.log_context)
        nexus.use_network(action_network)
        network_client = nexus.network_client

        usdc_contract = self.usdc_networks_mapping[action_network]
        usdc_balance = await network_client.wallet.balance(usdc_contract)

        bridge_amounts = nexus_bridge_params["usdc_amount_to_bridge"]
        bridge_amount = randfloat(bridge_amounts[0], bridge_amounts[1])
        bridge_usdc_amount = TokenAmount(bridge_amount, usdc_contract.decimals, False)

        approve_amounts = nexus_bridge_params.get("usdc_approve_amount")
        if approve_amounts:
            if isinstance(approve_amounts, list):
                approve_amount = randfloat(approve_amounts[0], approve_amounts[1])
                approve_amount = TokenAmount(approve_amount, usdc_contract.decimals, False)
            elif isinstance(approve_amounts, str) and approve_amounts.lower() == "infinity":
                approve_amount = approve_amounts
            else:
                raise ValueError(f"Incorrect usdc_approve_amount value: {approve_amounts}")
        else:
            approve_amount = bridge_usdc_amount

        self.logger.info(f"USDC balance in {action_network.capitalize()} before bridge: {usdc_balance} $USDC")
        if usdc_balance < bridge_usdc_amount:
            self.logger.warning(f"USDC balance is less than rolled bridge amount: {bridge_usdc_amount} $USDC."
                                f" Using whole USDC balance to bridge.")
            bridge_usdc_amount = usdc_balance

        return await nexus.bridge_usdc(bridge_usdc_amount, dest_network, usdc_contract, approve_amount)

    async def get_biggest_usdc_balance(self, controller: Controller, networks_list: list[str]):
        balances = {}
        for network in networks_list:
            network_client = getattr(controller.eth_client, network)
            usdc_contract = self.usdc_networks_mapping[network]
            balances[network] = await network_client.wallet.balance(usdc_contract)

        max_balance_network = max(balances, key=lambda x: balances[x])
        return max_balance_network, balances[max_balance_network]


    async def execute_initial_actions(self, action_type, action_params: dict, controller: Controller):
        init_withdraw_params = action_params["initial_withdraw_params"]

        cex_name = action_type.split("_")[-1]
        if cex_name == "random":
            cex_name = random.choice(init_withdraw_params["cex_to_random"]).lower()
            
        action_network = random.choice(init_withdraw_params["networks_to_withdraw"])

        # coin = init_withdraw_params["ticker"]
        network_client = getattr(controller.eth_client, action_network.lower())

        withdraw_amounts = None
        for key in init_withdraw_params:
            if "withdraw_eth" in key and action_network in key:
                withdraw_amounts = init_withdraw_params[key]

        if not withdraw_amounts:
            self.logger.error(f"Check your preset. Not found withdraw amounts in [[initial_withdraw_params]] block"
                              f" for network {action_network.capitalize()}")
            return False

        withdraw_amount = randfloat(*withdraw_amounts, step=0.0000001)

        cex_withdraw_client = CexWithdraw(cex_name, self.log_context)
        return await cex_withdraw_client.withdraw(withdraw_amount, action_network, network_client)


    async def execute_uniswap_actions(self, action_type, action_params: dict, controller: Controller):
        action_network = action_type.split("_")[-1]
        if action_network == "random":
            action_network = random.choice(action_params["swap"]["random_networks_to_swap"])
            self.logger.info(f"Selected random Uniswap network: {action_network.capitalize()}")

        gas_result = await self.gas_control(controller, action_network)
        if not gas_result:
            self.logger.error(f"Oops, gas is still too high, quitting action")
            return False

        balance_check = await self.check_balance_and_withdraw(controller, action_network, action_params)
        if not balance_check:
            self.logger.error(f"Oops, balance is still too low, quitting action")
            return False

        # self.logger.info(f"Swapping in {action_network}")

        uniswap = Uniswap(controller.eth_client, controller.requests_client, self.log_context)
        uniswap.use_network(action_network)
        swap_params = action_params.get("swap")

        results = {}

        chain_swap_params = swap_params.get(action_network)

        if isinstance(chain_swap_params, dict):
            return await self.uniswap_swap(uniswap, chain_swap_params, action_network, results)
        elif isinstance(chain_swap_params, list):
            for token_params in chain_swap_params:
                results = await self.uniswap_swap(uniswap, token_params, action_network, results)

        return results

    async def uniswap_swap(self, uniswap, token_params, action_network, results):
        result_string = f"{action_network} from {token_params["from_token"]} to {token_params["to_token"]}"

        try:
            swap_amount = await self.get_evm_swap_amount(uniswap.network_client,
                                                         token_params["from_token"], token_params["amount"])

            results[result_string] = await uniswap.swap_exact_in(
                amount_from=swap_amount,
                token_from=token_params["from_token"],
                token_to=token_params["to_token"],
                from_decimals=token_params["from_decimals"],
                to_decimals=token_params["to_decimals"],
                slippage=token_params["slippage"]  # не делим на 100
            )

            if token_params["swap_mode"] == "to_and_from":
                if token_params["to_token"] == "native":
                    raise Exception(f"You are trying to swap back all native into token {token_params['from_token']}")

                swap_amount = await uniswap.network_client.wallet.balance(token_params["to_token"])
                result_string = f"{action_network} from {token_params["to_token"]} to {token_params["from_token"]}"
                results[result_string] = await uniswap.swap_exact_in(
                    amount_from=swap_amount,
                    token_from=token_params["to_token"],
                    token_to=token_params["from_token"],
                    from_decimals=token_params["to_decimals"],
                    to_decimals=token_params["from_decimals"],
                    slippage=token_params["slippage"]  # не делим на 100
                )
        except InsufficientFundsException as e:
            self.logger.error(f"{excname(e)} {str(e)}")
            results[result_string] = "Insufficient funds"

        return results
