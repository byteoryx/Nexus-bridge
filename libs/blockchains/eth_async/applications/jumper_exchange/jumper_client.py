import json
from typing import Literal
import uuid

from web3 import Web3
from web3.contract import AsyncContract
from web3.exceptions import ContractLogicError
from web3.types import TxParams

from core.evm_contracts import EVMContracts
from core.init_settings import settings
from core.logger import get_logger
from libs.blockchains.eth_async.base_evm_task_class import BaseEVMTaskClass
from libs.blockchains.eth_async.data.models import RawContract, CommonValues, TxArgs
from libs.blockchains.omnichain_models import TokenAmount
from libs.blockchains.eth_async.exceptions import TxFailed
from libs.requests.exceptions import CustomRequestException, EXTERNAL_REQUEST_EXCEPTIONS
from tasks.controller import Controller
from utils.utils import log_sleep, excname


class JumperExchange(BaseEVMTaskClass["JumperExchange"]):
    _headers = {
        "referer": "https://jumper.exchange/",
        "sec-fetch-site": "same-site",
        "origin": "https://jumper.exchange",
    }

    CONTRACTS = None

    def __init__(self, controller: Controller, log_context):
        self.controller = controller
        self.requests = self.controller.requests_client
        self.eth_client = self.controller.eth_client
        self._logger = get_logger(class_name=self.__class__.__name__, **log_context)
        self._current_network = None
        super().__init__(self)

        self.session_id = self.generate_session_id()

    @staticmethod
    def generate_session_id():
        return str(uuid.uuid4())
    
    
    async def _get_routes(self, amount: str, from_token_address: str, to_token_address: str,
                          from_chain_id: int, to_chain_id: int, slippage: float = 0.005):
        """
        amount str wei
        """
        headers = self._headers | {
            "x-lifi-integrator": "jumper.exchange",
            "x-lifi-sdk": "3.7.0",
            "x-lifi-widget": "3.21.0",
        }

        json_data = {
            "fromAddress": self.eth_client.w3_account.address,
            "fromAmount": amount,
            "fromChainId": from_chain_id,
            "fromTokenAddress": from_token_address,
            "toChainId": to_chain_id,
            "toTokenAddress": to_token_address,
            "options": {
                "integrator": "jumper.exchange",
                "order": "CHEAPEST",
                "slippage": slippage,
                "maxPriceImpact": 0.4,
                "allowSwitchChain": True,
            },
        }
        url = f"https://api.jumper.exchange/p/lifi/advanced/routes"
        def handler(response):
            if response.status_code != 200:
                raise CustomRequestException(response)
            try:
                return response.json()
            except json.decoder.JSONDecodeError:
                return json.loads(response.text.strip())

        resp = await self.requests.post(url, [200], additional_headers=headers, json=json_data,
                                        resp_handler=handler)
        # self._logger.debug(f"_get_routes: {resp}")
        available_routes = resp["routes"]
        unavailable_routes = resp["unavailableRoutes"] # filteredOut # failed

        return available_routes, unavailable_routes

    async def _create_or_finish_transaction(self, action: Literal["execution_start", "execution_completed"],
                                            exchange: str, from_amount: int, from_amount_usd: float, from_chain_id: int,
                                            from_token: str, route_id: str, session_id: str, step_number: int,
                                            to_amount: int, to_amount_min: int, to_amount_usd: float, to_chain_id: int,
                                            to_token: str, gas_cost: int, gas_cost_usd: float,
                                            tx_hash: str = "", tx_status: Literal["STARTED", "COMPLETED"] = "STARTED",
                                            integrator: str = "jumper.exchange", is_final: bool = False):
        json_data = {
            "action": action,
            "browserFingerprint": "unknown",
            "exchange": exchange,
            "fromAmount": from_amount,
            "fromAmountUSD": from_amount_usd,
            "fromChainId": from_chain_id,
            "fromToken": from_token,
            "gasCost": gas_cost,
            "gasCostUSD": gas_cost_usd,
            "integrator": integrator,
            "isFinal": is_final,
            "routeId": route_id,
            "sessionId": session_id,
            "stepNumber": step_number,
            "toAmount": to_amount,
            "toAmountMin": to_amount_min,
            "toAmountUSD": to_amount_usd,
            "toChainId": to_chain_id,
            "toToken": to_token,
            "transactionHash": tx_hash,
            "transactionStatus": tx_status,
            "type": "SWAP",
            "url": f"https://jumper.exchange/?fromChain={from_chain_id}&fromToken={from_token}&toChain={to_chain_id}&toToken={to_token}",
            "walletProvider": "Rabby Wallet",
            "walletAddress": self.eth_client.w3_account.address,
            "referrer": "",
            "abtests": {
                "TEST_WIDGET_SUBVARIANTS": False,
            },
        }
        url = f"https://api.jumper.exchange/v1/wallets/transactions"
        # self._logger.debug(f"_create_or_finish_transaction json_data: {json_data}")
        resp = await self.requests.post(url, [200, 201],
                                            additional_headers=self._headers, json=json_data)
        if resp["message"] == "Success":
            return True
        return False

    async def _swap_with_permit(self, tool_key, transaction_data_dict, from_token_address, best_output_route, slippage,
                                token_from, from_amount,
                                steps, chain_id, from_token_symbol):
        for _ in range(5):
            try:
                typed_data, swap_data_for_permit, tool_from_quote = await self._get_quote_and_permit_data(
                    from_token_address=from_token_address,
                  from_amount=str(best_output_route["fromAmount"]),
                  from_chain=str(best_output_route["fromChainId"]),
                  to_chain=str(best_output_route["toChainId"]),
                  to_token=str(
                      best_output_route["toToken"]["address"]),
                  order="RECOMMENDED",
                  slippage=str(slippage),
                  integrator="jumper.exchange"
                )
                if tool_key != tool_from_quote:
                    self._logger.warning(f"tool_key: {tool_key} != tool_from_quote: {tool_from_quote}")
                    # await log_sleep(self)
                    # continue

                # self._logger.debug(typed_data)
                try:
                    data = typed_data[0]
                except IndexError:
                    raise Exception(f"Permit contract not found: {typed_data}")
                # for t_data in typed_data:
                #     if "permit2" in t_data["domain"]["name"].lower():
                #         data = t_data
                #         break
                # else:
                #     raise Exception(f"Permit contract not found: {typed_data}")

                # if "permit2" in data["domain"]["name"].lower():
                # if "permit" in data["types"]["name"].lower():
                approve_contract = data["message"]["spender"]
                # approve = await self.network_client.transactions.approve_interface(token_from,
                #                                                                    approve_contract,
                #                                                                    from_amount)
                approve = await self.network_client.transactions.approve_interface(token=token_from,
                                                                                   spender=approve_contract,
                                                                                   amount_in_tx=from_amount,)
                                                                                   # amount_to_approve=approve_amount,
                                                                                   # approve_inf=approve_inf)
                if approve:
                    # self._logger.debug(f"Signing data: {data}")
                    selected_step = steps[0]
                    for index, step in enumerate(steps):
                        self._logger.info(f"step tool {index} {step['tool']}")
                        if step["tool"] == tool_from_quote:
                            selected_step = step

                    if selected_step["tool"] != tool_key:
                        self._logger.warning(f"tool_key: {tool_key} != selected_step tool: {selected_step["tool"]}")
                        # await log_sleep(self)
                        # continue

                    assert transaction_data_dict["exchange"] == selected_step["tool"]
                    if await self._create_or_finish_transaction(**transaction_data_dict):
                        step_transaction = await self._request_swap_data(selected_step)
                        _diamondCalldata1 = step_transaction["data"]
                    else:
                        await log_sleep(self)
                        continue

                    contract: AsyncContract = await self.network_client.contracts.get(contract=approve_contract,
                                                                        abi=EVMContracts.jumper_diamond_proxy_abi)
                    permit_nonce = await self._get_permit_nonce(contract)
                    structured_message = {
                            "domain": {
                                "name": "Permit2",
                                "chainId": self.network_client.network.chain_id,
                                "verifyingContract": data["domain"]["verifyingContract"]
                            },
                            "message": {
                                "permitted": {
                                    "token": from_token_address,
                                    "amount": str(from_amount.Wei)
                                },
                                "spender": data["message"]["spender"],
                                "nonce": str(permit_nonce),
                                "deadline": data["message"]["deadline"][:-3]
                            },
                            "primaryType": "PermitTransferFrom",
                            "types": {
                                "EIP712Domain": [
                                    {
                                        "name": "name",
                                        "type": "string"
                                    },
                                    {
                                        "name": "chainId",
                                        "type": "uint256"
                                    },
                                    {
                                        "name": "verifyingContract",
                                        "type": "address"
                                    }
                                ],
                                "TokenPermissions": [
                                    {
                                        "name": "token",
                                        "type": "address"
                                    },
                                    {
                                        "name": "amount",
                                        "type": "uint256"
                                    }
                                ],
                                "PermitTransferFrom": [
                                    {
                                        "name": "permitted",
                                        "type": "TokenPermissions"
                                    },
                                    {
                                        "name": "spender",
                                        "type": "address"
                                    },
                                    {
                                        "name": "nonce",
                                        "type": "uint256"
                                    },
                                    {
                                        "name": "deadline",
                                        "type": "uint256"
                                    }
                                ]
                            }
                        }

                    permit_signed = await self.network_client.transactions.sign_message(
                        typed_data=structured_message, full_message=True)

                    self._logger.success(f"Signed permit data for swap: {structured_message}")
                    signature = "0x" + permit_signed.signature.hex()
                    self._logger.debug(f"Signed permit data for swap: {signature}")

                    permit_args = TxArgs(
                        permitted=(from_token_address, int(from_amount.Wei)),
                        nonce=int(structured_message["message"]["nonce"]),
                        deadline=int(structured_message["message"]["deadline"]),
                    )

                    args = TxArgs(_diamondCalldata=bytes.fromhex(_diamondCalldata1[2:]),
                                  _permit=permit_args.tuple(),
                                  _signature=permit_signed.signature)
                    # self._logger.debug(f"My args: {args}")

                    swap_data = contract.encode_abi("callDiamondWithPermit2", args.tuple())
                    tx_params = TxParams(
                        to=contract.address,
                        data=swap_data,
                        # data=HexStr("0x0193b9fc00000000000000000000000000000000000000000000000000000000000000c0000000000000000000000000833589fcd6edb6e08f4c7c32d4f71b54bda0291300000000000000000000000000000000000000000000000000000000004c4b400000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000006846ffea00000000000000000000000000000000000000000000000000000000000006400000000000000000000000000000000000000000000000000000000000000544733214a35247e8e75301d0a3c6d35295fea3013c44a80817a515544a7dc7e6da954ad3de00000000000000000000000000000000000000000000000000000000000000c0000000000000000000000000000000000000000000000000000000000000010000000000000000000000000096f193844ebae791aa90d59bb9e12215d7b18bab0000000000000000000000000000000000000000000000000006f71b9a628e6c0000000000000000000000000000000000000000000000000000000000000160000000000000000000000000000000000000000000000000000000000000000f6a756d7065722e65786368616e67650000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000002a30783030303030303030303030303030303030303030303030303030303030303030303030303030303000000000000000000000000000000000000000000000000000000000000000000000ac4c6e212a361c968f1725b4d055b47e63f80b75000000000000000000000000ac4c6e212a361c968f1725b4d055b47e63f80b75000000000000000000000000833589fcd6edb6e08f4c7c32d4f71b54bda02913000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000004c4b4000000000000000000000000000000000000000000000000000000000000000e0000000000000000000000000000000000000000000000000000000000000000100000000000000000000000000000000000000000000000000000000000002c45f3bd1c8000000000000000000000000833589fcd6edb6e08f4c7c32d4f71b54bda0291300000000000000000000000000000000000000000000000000000000004c4b400000000000000000000000001231deb6f5749ef6ce6943a275a1d3e7486f4eae000000000000000000000000eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee0000000000000000000000000000000000000000000000000006f71b9a628e6b0000000000000000000000003ced11c610556e5292fbc2e75d68c3899098c14c00000000000000000000000000000000000000000000000000000000000000e000000000000000000000000000000000000000000000000000000000000001a46be92b89000000000000000000000000833589fcd6edb6e08f4c7c32d4f71b54bda0291300000000000000000000000000000000000000000000000000000000004c4b40000000000000000000000000eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee00000000000000000000000000000000000000000000000000070011734809590000000000000000000000001231deb6f5749ef6ce6943a275a1d3e7486f4eae000000000000000000000000000000000000000000000000000000000000010000000000000000000000000000000000000000000000000000000000000000010000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000007101833589fcd6edb6e08f4c7c32d4f71b54bda0291301ffff0172ab388e2e2f6facef59e3c3fa2c4e29011c2d38003ced11c610556e5292fbc2e75d68c3899098c14c0001420000000000000000000000000000000000000601ffff02003ced11c610556e5292fbc2e75d68c3899098c14c000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000004148b0fcdf25785b1be71eeea989ec456a0b970182c653e7cb91a991d71cc693415b1d63cc46c354df4e985cb7ba1a8953718ace87967f3415c0abe3effe3d86b21b00000000000000000000000000000000000000000000000000000000000000"),
                        value=0
                    )
                    return tx_params

                break

            except CustomRequestException as e:
                if e.status_code == 400 and "not found on" in e.text:
                    self._logger.warning(f"No permit data for {from_token_symbol} on {chain_id}")
                    await log_sleep(self, 3)
                    continue
                else:
                    self._logger.error(f"Error getting quote with permit: {e.status_code} {e.text}")
                    raise

    async def _get_permit_nonce(self, contract):
        return await self.network_client.contracts.read_contract_function(contract,"nextNonce",
                                                                          owner=self.network_client.w3_account.address)


    async def swap(self,
                    from_amount: int | TokenAmount,
                    token_from: RawContract | str,
                    token_to: RawContract | str,
                    slippage: float = 0.005, # 0.5 %
                    ):
        str_amount = str(from_amount.Wei) if isinstance(from_amount, TokenAmount) else str(from_amount)
        if isinstance(token_from, RawContract):
            from_token_address = token_from.address
        else:
            from_token_address = CommonValues.ZeroAddress \
                if token_from.lower().strip() == "native" else Web3.to_checksum_address(token_from.strip())

        if isinstance(token_from, RawContract):
            to_token_address = token_to.address
        else:
            to_token_address = CommonValues.ZeroAddress \
                if token_to.lower().strip() == "native" else Web3.to_checksum_address(token_to.strip())

        chain_id = self.network_client.network.chain_id

        for attempt in range(1, settings.general.number_of_retries + 1):
            try:
                return await self._perform_swap(str_amount, from_token_address, to_token_address,
                                                chain_id, slippage, token_from, token_to, from_amount)

            except TxFailed:
                self._logger.error(f"Swap attempt {attempt}: tx failed")

            except CustomRequestException as e:
                self._logger.error(f"Swap attempt {attempt}: CustomRequestException: {e.status_code}, {e.text}")
                await log_sleep(self, settings.general.retry_delay)

            except EXTERNAL_REQUEST_EXCEPTIONS as e:
                self._logger.error(f"{excname(e)} {str(e)}")
                await self.controller.change_proxy()

            except ContractLogicError as e:
                self._logger.error(f"Swap attempt {attempt}: {excname(e)} {str(e)}")
        else:
            return False


    async def _perform_swap(self, str_amount, from_token_address, to_token_address, chain_id,
                            slippage, token_from, token_to, from_amount):
        available_routes, unavailable_routes = await self._get_routes(amount=str_amount,
                                                                      from_token_address=from_token_address,
                                                                      to_token_address=to_token_address,
                                                                      from_chain_id=chain_id,
                                                                      to_chain_id=chain_id,
                                                                      slippage=slippage)
        best_output_route = None
        for index, route in enumerate(available_routes):
            if any(tag in route["tags"] for tag in ("RECOMMENDED", "CHEAPEST", "FASTEST")):
                self._logger.success(f"Route with tags {route['tags']} was found")
                best_output_route = route
                route_id = best_output_route["id"] + ":" + str(index)

        if best_output_route is None:
            self._logger.warning(f"No route with tags found for {token_from} to {token_to}, will get default quote")
            output_comparison_dict = {(float(route["toAmountUSD"]) - float(route["gasCostUSD"])): route
                                      for route in available_routes}
            best_output_route = output_comparison_dict[max(output_comparison_dict)]
            route_id = best_output_route["id"] + ":" + str(0)  # hardcode

        from_token_decimals = best_output_route["fromToken"]["decimals"]
        from_token_symbol = best_output_route["fromToken"]["symbol"]
        to_token_decimals = best_output_route["toToken"]["decimals"]
        to_token_symbol = best_output_route["toToken"]["symbol"]
        output = str(int(best_output_route["toAmountMin"]) / 10 ** to_token_decimals)[:10]

        steps = best_output_route["steps"]
        tool_name = steps[0]["toolDetails"]["name"]
        tool_key = steps[0]["toolDetails"]["key"]  # нужно для подтверждения транзакции

        self._logger.info(f"Starting to swap {from_amount} {from_token_symbol} to minimum {output} {to_token_symbol}"
                          f" via {tool_name} with slippage {slippage * 100}%")
        transaction_data_dict = dict(
            action="execution_started",
            exchange=tool_key,
            from_amount=int(best_output_route["fromAmount"]),
            from_amount_usd=float(best_output_route["fromAmountUSD"]),
            from_chain_id=int(best_output_route["fromChainId"]),
            from_token=best_output_route["fromToken"]["address"],
            route_id=route_id,
            session_id=self.session_id,
            step_number=1,  # 1 for swaps, custom for bridges
            to_amount=int(best_output_route["toAmount"]),
            to_amount_min=int(best_output_route["toAmountMin"]),
            to_amount_usd=float(best_output_route["toAmountUSD"]),
            to_chain_id=int(best_output_route["toChainId"]),
            to_token=best_output_route["toToken"]["address"],
            gas_cost=int(steps[0]["estimate"]["gasCosts"][0]["amount"]),
            gas_cost_usd=float(steps[0]["estimate"]["gasCosts"][0]["amountUSD"]),
        )
        # self._logger.debug(transaction_data_dict)
        if not from_token_address == "0x0000000000000000000000000000000000000000":
            tx_params = await self._swap_with_permit(tool_key, transaction_data_dict, from_token_address,
                                                     best_output_route, slippage, token_from,
                                                     from_amount, steps, chain_id, from_token_symbol)
            if not tx_params:
                return False
        else:
            if await self._create_or_finish_transaction(**transaction_data_dict):
                tx_params = await self._request_swap_data(steps[0])
            else:
                return False

        # self._logger.debug(f"tx_params {tx_params}")
        if "gasLimit" in tx_params:
            tx_params.pop("gasLimit")

        tx_hash = await self.network_client.transactions.send_tx(tx_params)

        for _ in range(10):
            await log_sleep(self, 3)
            tx_data = await self.get_transaction_status(str(chain_id), str(chain_id), tool_key, tx_hash)
            self._logger.info(f"Checking transaction status: {tx_data["status"]}")
            if tx_data["status"] == "DONE":
                break
        else:
            raise Exception("Transaction failed")

        transaction_data_dict["action"] = "execution_completed"
        transaction_data_dict["tx_status"] = "COMPLETED"
        transaction_data_dict["tx_hash"] = tx_hash
        transaction_data_dict["is_final"] = True

        if await self._create_or_finish_transaction(**transaction_data_dict):
            to_amount = TokenAmount(transaction_data_dict["to_amount"], to_token_decimals, wei=True)
            to_amount_usd = transaction_data_dict["to_amount_usd"]
            self._logger.success(f"Successfully swapped {from_amount} {from_token_symbol}"
                                 f" to {to_amount} {to_token_symbol} (${to_amount_usd})\n"
                                 f"LI.FI explorer: {tx_data['lifiExplorerLink']}")
            return True
        else:
            self._logger.error(f"Tx OK, but confirm on Jumper failed")
            return True

    async def _request_swap_data(self, steps: dict):
        headers = self._headers | {
            "x-lifi-integrator": "jumper.exchange",
            "x-lifi-sdk": "3.7.0",
            "x-lifi-widget": "3.21.0",
        }
        url = "https://api.jumper.exchange/p/lifi/advanced/stepTransaction"
        resp = await self.requests.post(url, [200], additional_headers=headers, json=steps)
        # self._logger.debug(f"_request_swap_data: {resp}")
        return resp["transactionRequest"]

    async def _get_chains_data(self):
        headers = self._headers | {
            "x-lifi-integrator": "jumper.exchange",
            "x-lifi-sdk": "3.7.0",
        }

        params = {
            'chainTypes': 'EVM,SVM,UTXO,MVM',
        }
        url = "https://api.jumper.exchange/p/lifi/chains"
        resp = await self.requests.get(url, params=params, additional_headers=headers)
        return resp

    async def _get_tokens_data(self):
        headers = self._headers | {
            "x-lifi-integrator": "jumper.exchange",
            "x-lifi-sdk": "3.7.0",
            "x-lifi-widget": "3.21.0",
        }

        params = {
            'chainTypes': 'EVM,SVM,UTXO,MVM',
        }
        url = "https://api.jumper.exchange/p/lifi/tokens"
        resp = await self.requests.get(url, params=params, additional_headers=headers)
        return resp

    async def _sign_permit(self, permit_data: dict | None) -> str | None:
        if permit_data:
            permit_signed = await self.network_client.transactions.sign_message(typed_data=permit_data)
            # permit_signed = await self.network_client.transactions.sign_message(message=json.dumps(permit_data))
            self._logger.success(f"Signed permit data for swap")
            return '0x' + permit_signed.signature.hex()

    async def _get_quote_and_permit_data(self, from_token_address: str, from_amount: str,
                                         from_chain: str, to_chain: str, to_token: str, order: str,
                                         slippage: str, integrator: str):
        headers = self._headers | {
            "x-lifi-integrator": "jumper.exchange",
            "x-lifi-sdk": "3.7.0",
            "x-lifi-widget": "3.21.0",
        }

        params = {
            'fromAddress': self.eth_client.w3_account.address,
            'fromAmount': from_amount,
            'fromChain': from_chain,
            'fromToken': from_token_address,
            'toChain': to_chain,
            'toToken': to_token,
            'order': order,
            'slippage': slippage,
            'integrator': integrator,
        }
        self._logger.debug(f"Getting quote and permit data for swap: {params=}")
        url = "https://api.jumper.exchange/p/lifi/relayer/quote"
        def handler(response):
            try:
                if response.json()["status"] == "ok":
                    return response.json()
            except json.decoder.JSONDecodeError:
                raise CustomRequestException(response)

        resp = await self.requests.get(url, [200, 204], params=params,
                                       additional_headers=headers, resp_handler=handler)
        tool = resp["data"]["tool"]
        # self._logger.debug(f"Quote: {resp}")
        # self._logger.info(f"tool from quote: {tool}")
        typed_data = resp["data"]["typedData"]
        swap_data = resp["data"]["transactionRequest"]
        return typed_data, swap_data, tool


    async def get_transaction_status(self, from_chain: str, to_chain: str, bridge: str, tx_hash: str) -> dict:
        headers = self._headers | {
            "x-lifi-integrator": "jumper.exchange",
            "x-lifi-sdk": "3.7.0",
            "x-lifi-widget": "3.21.0",
        }

        params = {
            'fromChain': from_chain,
            'toChain': to_chain,
            'txHash': tx_hash,
            'bridge': bridge,
        }
        url = "https://api.jumper.exchange/p/lifi/status"
        resp = await self.requests.get(url, [200, 400], params=params, additional_headers=headers)
        # code 400 {"message":"Not an EVM Transaction.","code":1011}
        return resp


    async def get_leaderboard(self):
        url = f"https://api.jumper.exchange/v1/leaderboard/{self.network_client.w3_account.address}"
        headers = {'Referer': 'https://jumper.exchange/', 'sec-ch-ua-mobile': '?0',
                   "sec-ch-ua": self.requests.basic_headers["sec-ch-ua"],
                   "user-agent": self.requests.basic_headers["user-agent"],
                   "sec-ch-ua-platform": self.requests.basic_headers["sec-ch-ua-platform"]
        }
        resp = await self.requests.get(url, [200], fully_external_headers=headers)
        points: str = resp["data"]["points"]
        position: str = resp["data"]["position"]
        self._logger.info(f"Points: {points}, leaderboard position: {position}")
