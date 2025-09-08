from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any

from eth_typing import ChecksumAddress, HexStr
from hexbytes import HexBytes
from web3 import Web3
from web3.contract import AsyncContract
from web3.types import TxReceipt, _Hash32, TxParams, Nonce
from web3.exceptions import TimeExhausted
from eth_account.datastructures import SignedTransaction, SignedMessage
from eth_account.messages import encode_defunct, encode_typed_data

from core.init_settings import settings
from core.logger import get_logger
from .data import types
from .exceptions import TransactionException, GasException, NonceException, TxFailed
from libs.blockchains.classes import AutoRepr
from .network_client_aware import NetworkClientAware
from .data.models import CommonValues, TxArgs, Network, DefaultABIs, RawContract
from ..omnichain_models import TokenAmount

if TYPE_CHECKING:
    from .ethclient import NetworkClient


class Tx(AutoRepr):
    """
    An instance of transaction for easy execution of actions on it.

    Attributes:
        hash (Optional[_Hash32]): a transaction hash.
        params (Optional[dict]): the transaction parameters.
        receipt (Optional[TxReceipt]): a transaction receipt.
        function_identifier (Optional[str]): a function identifier.
        input_data (Optional[Dict[str, Any]]): an input data.

    """
    hash: _Hash32 | None
    params: dict | None
    receipt: TxReceipt | dict | None
    function_identifier: str | None
    input_data: dict[str, Any] | None

    def __init__(self, tx_hash: str | _Hash32 | None = None, params: dict | None = None) -> None:
        """
        Initialize the class.

        Args:
            tx_hash (Optional[Union[str, _Hash32]]): the transaction hash. (None)
            params (Optional[dict]): a dictionary with transaction parameters. (None)

        """
        if not tx_hash and not params:
            raise TransactionException("Specify 'tx_hash' or 'params' argument values!")

        if isinstance(tx_hash, str):
            tx_hash = HexBytes(tx_hash)

        self.hash = tx_hash
        self.params = params
        self.receipt = None
        self.function_identifier = None
        self.input_data = None


    async def parse_params(self, client) -> dict[str, Any]:
        """
        Parse the parameters of a sent transaction.

        Args:
            client (NetworkClient): the Client instance.

        Returns:
            Dict[str, Any]: the parameters of a sent transaction.

        """
        tx_data = await client.w3.eth.get_transaction(transaction_hash=self.hash)
        self.params = {
            'chainId': client.network.chain_id,
            'nonce': Nonce(tx_data.get('nonce')),
            'gasPrice': int(tx_data.get('gasPrice')),
            'gas': int(tx_data.get('gas')),
            'from': tx_data.get('from'),
            'to': tx_data.get('to'),
            'data': tx_data.get('input'),
            'value': int(tx_data.get('value')),
            'blockNumber': int(tx_data.get('blockNumber'))
        }
        return self.params

    async def wait_for_receipt(
            self, client: NetworkClient, timeout: int | float = 120, poll_latency: float = 0.1
    ) -> dict[str, Any]:
        """
        Wait for the transaction receipt.

        Args:
            client (NetworkClient): the Client instance.
            timeout (Union[int, float]): the receipt waiting timeout. (120 sec)
            poll_latency (float): the poll latency. (0.1 sec)

        Returns:
            Dict[str, Any]: the transaction receipt.

        """
        self.receipt = await client.transactions.wait_for_receipt(
            w3=client.w3,
            tx_hash=self.hash,
            timeout=timeout,
            poll_latency=poll_latency
        )
        return self.receipt

    async def decode_input_data(self):
        pass

    async def cancel(self, client: NetworkClient) -> dict[str, Any] | bool:
        # needs testing
        try:
            cancel_tx_params = {
                'chainId': client.network.chain_id,
                'nonce': self.params['nonce'],
                'gasPrice': self.params['gasPrice'] * 2,  # Увеличиваем цену на газ для приоритета
                'gas': self.params['gas'],
                'from': self.params['from'],
                'to': self.params['from'],  # Отправляем на свой же адрес
                'value': 0,  # Нулевой перевод
            }
            tx = TxParams(**cancel_tx_params)
            replacement_tx = await client.transactions.sign_and_send(tx_params=tx)
            return await replacement_tx.wait_for_receipt(client=client, timeout=300)
        except TransactionException as e:
            return False

    async def speed_up(self, client: NetworkClient) -> dict[str, Any] | bool:
        # inputs client and Tx (self)
        # needs testing
        try:
            self.params['gasPrice'] = (await client.transactions.gas_price()).Wei * 1.103
            tx_params = TxParams(**self.params)
            replacement_tx = await client.transactions.sign_and_send(tx_params=tx_params)
            return await replacement_tx.wait_for_receipt(client=client, timeout=300)
        except TransactionException as e:
            return False


class Transactions(NetworkClientAware):
    def __init__(self, client: NetworkClient, log_context) -> None:
        super().__init__(client, log_context=log_context)
        if log_context:
            self.logger = get_logger(class_name=f"EthClient: {client.network.name}", **log_context)
        else:
            self.logger = get_logger(class_name=f"EthClient: {client.network.name}")

    @NetworkClientAware.retry
    async def gas_price(self) -> TokenAmount:
        """
        Get the current gas price
        :return: gas price
        """
        # direct call of protected method because @property gas_price bypasses my retry decorator
        return TokenAmount(amount=await self.client.w3.eth._gas_price(), wei=True, decimals=self.client.network.decimals)

    @NetworkClientAware.retry
    async def max_priority_fee(self, block: dict | None = None) -> TokenAmount:
        # new method:
        # w3 = AsyncWeb3(provider=AsyncWeb3.AsyncHTTPProvider(endpoint_uri=self.client.network.rpc))
        # w3.middleware_onion.inject(ExtraDataToPOAMiddleware, layer=0)

        if not block:
            block = await self.client.w3.eth.get_block('latest')
            self.logger.debug(f'block {block}')

        block_number = block['number']
        latest_block_transaction_count = await self.client.w3.eth.get_block_transaction_count(block_number)
        self.logger.debug(f'latest_block_transaction_count {latest_block_transaction_count}')
        max_priority_fee_per_gas_lst = []
        for i in range(10):
            try:
                transaction = await self.client.w3.eth.get_transaction_by_block(block_number, i)
                self.logger.debug(f"transaction { transaction}")

                if 'maxPriorityFeePerGas' in transaction:
                    max_priority_fee_per_gas_lst.append(transaction['maxPriorityFeePerGas'])
            except Exception:
                continue

        if not max_priority_fee_per_gas_lst:
            # max_priority_fee_per_gas = await w3.eth.max_priority_fee
            max_priority_fee_per_gas = 0
        else:
            max_priority_fee_per_gas_lst.sort()
            max_priority_fee_per_gas = max_priority_fee_per_gas_lst[len(max_priority_fee_per_gas_lst) // 2]

        # old method
        # query = [
        #     {
        #         "id": random.randint(1,99),
        #         "jsonrpc": "2.0",
        #         "method": "eth_maxPriorityFeePerGas"
        #     }
        # ]
        # response = await async_post(url=self.client.network.rpc, data=query)
        # max_priority_fee_per_gas = int(response[0]['result'], 16)
        self.logger.info(f"max_priority_fee_per_gas {max_priority_fee_per_gas / 10**18}")

        return TokenAmount(amount=max_priority_fee_per_gas, wei=True, decimals=self.client.network.decimals)

    @NetworkClientAware.retry
    async def max_priority_fee_(self) -> TokenAmount:
        """
        Get the current max priority fee.

        Returns:
            Wei: the current max priority fee.

        """
        return TokenAmount(amount=await self.client.w3.eth.max_priority_fee, wei=True,
                           decimals=self.client.network.decimals)


    @NetworkClientAware.retry
    async def add_nonce(self, tx_params):
        try:
            if not tx_params.get('nonce'):
                tx_params['nonce'] = await self.client.wallet.nonce()
            return tx_params
        except:
            raise

    @NetworkClientAware.retry
    async def add_gas_price(self, tx_params):
        try:
            if 'gasPrice' not in tx_params and self.client.network.tx_type == 0:
                gas_price = await self.gas_price()
                # self.logger.debug(f"Current gas_price: {gas_price.Wei * 10**9} Gwei")
                tx_params['gasPrice'] = self.client.w3.to_wei(
                    gas_price.Wei * settings.gas.gas_price_multiplier, unit='wei')


            if 'maxPriorityFeePerGas' not in tx_params and self.client.network.tx_type == 2:
                latest_block = await self.client.w3.eth.get_block('latest')
                base_fee = latest_block['baseFeePerGas']

                if self.client.network.chain_id == 56: # baseFeePerGas in BSC always zero
                    base_fee = 10 ** 9

                tx_params['maxPriorityFeePerGas'] = self.client.w3.to_wei(
                    base_fee * settings.gas.gas_price_multiplier, unit='wei')

                tx_params['maxFeePerGas'] = base_fee + tx_params['maxPriorityFeePerGas']

                if self.client.network.chain_id == 137: # polygon returns 2 or 3 digit Wei on base fee
                    base_fee = base_fee * 10 ** 9
                    tx_params['maxPriorityFeePerGas'] = await self.client.w3.eth.max_priority_fee
                    tx_params['maxFeePerGas'] = tx_params['maxPriorityFeePerGas'] * 2

            return tx_params
        except:
            raise

    @NetworkClientAware.retry
    async def add_gas(self, tx_params):
        try:
            if 'gas' not in tx_params or not int(tx_params['gas']):
                gas = await self.client.w3.eth.estimate_gas(transaction=tx_params)
                tx_params['gas'] = int(gas * settings.gas.gas_limit_multiplier)
            return tx_params
        except Exception as e:
            if 'account' in str(e):
                self.logger.exception(e)
            raise GasException(f"Failed to estimate gas: {str(e)}") from e

    @NetworkClientAware.retry
    async def preflight_balance_check(self, tx_params):
        try:
            # balance = await self.client.wallet.balance()
            # if "gasPrice" in tx_params:
            #     needed_balance = tx_params["gas"] * tx_params["gasPrice"]
            #     if balance.Wei < needed_balance:
            #         raise InsufficientFundsException(f"Balance: {balance.Ether} {self.client.network.coin_symbol} "
            #                                 f"less than {needed_balance * 10**18} {self.client.network.coin_symbol}")

            call_res = await self.client.w3.eth.call(tx_params)
        except:
            raise

    async def auto_add_params(self, tx_params: TxParams) -> TxParams:
        """
        Add 'chainId', 'nonce', 'from', 'gasPrice' or 'maxFeePerGas' + 'maxPriorityFeePerGas' and 'gas' parameters to
            transaction parameters if they are missing.

        Args:
            tx_params (TxParams): parameters of the transaction.

        Returns:
            TxParams: parameters of the transaction with added values.

        """
        if 'chainId' not in tx_params:
            tx_params['chainId'] = self.client.network.chain_id
        if 'from' not in tx_params:
            tx_params['from'] = self.client.w3_account.address

        tx_params = await self.add_nonce(tx_params)
        tx_params = await self.add_gas_price(tx_params)
        # await self.preflight_balance_check(tx_params)
        tx_params = await self.add_gas(tx_params)

        return tx_params

    async def sign_transaction(self, tx_params: TxParams) -> SignedTransaction:
        """
        Sign a transaction.

        Args:
            tx_params (TxParams): parameters of the transaction.

        Returns:
            SignedTransaction: the signed transaction.

        """
        return self.client.w3.eth.account.sign_transaction(
            transaction_dict=tx_params, private_key=self.client.w3_account.key
        )

    @NetworkClientAware.retry
    async def sign_and_send(self, tx_params: TxParams) -> Tx | str |  None:
        """
        Sign and send a transaction. Additionally, add 'chainId', 'nonce', 'from', 'gasPrice' or
            'maxFeePerGas' + 'maxPriorityFeePerGas' and 'gas' parameters to transaction parameters if they are missing.

        Args:
            tx_params (TxParams): parameters of the transaction.

        Returns:
            Tx: the instance of the sent transaction.

        """
        auto_added_params = await self.auto_add_params(tx_params=tx_params)
        signed_tx = await self.sign_transaction(auto_added_params)
        tx_hash = await self.client.w3.eth.send_raw_transaction(transaction=signed_tx.raw_transaction)
        return Tx(tx_hash=tx_hash, params=tx_params) if tx_hash else None

    async def normalize_tx_params(self, tx_params: TxParams | dict):
        if tx_params.get("gasLimit"):
            tx_params['gas'] = tx_params.pop('gasLimit')

        if tx_params.get("gasPrice"):
            if self.client.network.tx_type == 2 or tx_params["gasPrice"] == 0:
                tx_params.pop('gasPrice')
            else:
                tx_params['gasPrice'] = self.client.w3.to_wei(tx_params['gasPrice'], unit='wei')

        if "maxPriorityFeePerGas" in tx_params:
            if tx_params["maxPriorityFeePerGas"] == 0:
                tx_params.pop("maxPriorityFeePerGas")

            if isinstance(tx_params['maxPriorityFeePerGas'], str) and tx_params['maxPriorityFeePerGas'].startswith("0x"):
                tx_params["maxPriorityFeePerGas"] = int(tx_params["maxPriorityFeePerGas"])
            else:
                tx_params["maxPriorityFeePerGas"] = int(tx_params["maxPriorityFeePerGas"])

        if tx_params.get("maxFeePerGas"):
            if tx_params["maxFeePerGas"] == 0:
                tx_params.pop("maxFeePerGas")

            if isinstance(tx_params['maxFeePerGas'], str) and tx_params['maxFeePerGas'].startswith("0x"):
                tx_params["maxFeePerGas"] = int(tx_params["maxPriorityFeePerGas"] * settings.gas.gas_price_multiplier, 16)
            else:
                tx_params["maxFeePerGas"] = int(tx_params["maxPriorityFeePerGas"] * settings.gas.gas_price_multiplier)

        if tx_params.get("data"):
            if isinstance(tx_params['data'], str):
                tx_params['data'] = HexStr(tx_params['data'])

        if tx_params.get("value"):
            if isinstance(tx_params['value'], str) and tx_params['value'].startswith("0x"):
                tx_params['value'] = int(tx_params['value'], 16)
            tx_params['value'] = Web3.to_wei(tx_params['value'], 'wei')

        if tx_params.get("to"):
            tx_params['to'] = Web3.to_checksum_address(tx_params['to'])

        if tx_params.get("from"):
            tx_params['from'] = Web3.to_checksum_address(tx_params['from'])

        if tx_params.get("gas"):
            if isinstance(tx_params['gas'], str) and tx_params['gas'].startswith("0x"):
                tx_params['gas'] = int(tx_params['gas'], 16)
            else:
                tx_params['gas'] = int(tx_params['gas'])

        if tx_params.get("chainId"):
            if isinstance(tx_params['chainId'], str) and tx_params['chainId'].startswith("0x"):
                tx_params['chainId'] = int(tx_params['chainId'], 16)
            else:
                tx_params['chainId'] = int(tx_params['chainId'])

        return tx_params

    async def send_tx(self, tx_params: TxParams | dict) -> str | bool:
        tx_params = await self.normalize_tx_params(tx_params)
        for _ in range(1, settings.general.number_of_retries + 1):
            try:
                tx = await self.sign_and_send(tx_params)
                if tx:
                    explorer_link = f"{self.client.network.explorer}tx/{'0x' + tx.hash.hex()}"
                    self.logger.info(f"Sent tx, waiting for receipt... ({explorer_link})")

                    receipt = await self.wait_for_receipt(tx_hash=tx.hash, timeout=200, poll_latency=1)
                    if receipt is None:
                        self.logger.warning(f"Sent tx but didn't get receipt: {explorer_link}\n")
                    elif receipt:
                        if receipt["status"] == 1:
                            self.logger.success(f"Successful transaction: {explorer_link}\n")
                            return '0x' + tx.hash.hex()

                        elif receipt["status"] == 0:
                            raise TxFailed(f"Transaction failed: {explorer_link}\n")
                return False
            except GasException as e:
                if "increase gas limit" in str(e):
                    if "maxFeePerGas" in tx_params:
                        tx_params["maxFeePerGas"] = tx_params["maxFeePerGas"] * 1.5
                    if "gasPrice" in tx_params:
                        tx_params["gasPrice"] = tx_params["gasPrice"] * 1.5
                    self.logger.warning(f"Low gas cap, retrying with x1.5 gas cap in 5 seconds")
                    await asyncio.sleep(5)
                    continue

                elif "Need to increase gas" in str(e):
                    tx_params.pop(f"gas")
                    self.logger.warning(f"Retrying with higher gas limit")
                    continue

                else:
                    raise e

            except NonceException as e:
                self.logger.warning(f"Nonce collision, retrying with pending block nonce...")
                tx_params["nonce"] = await self.client.wallet.nonce(block_identifier="pending")
                continue

            except TransactionException as e:
                self.logger.warning(f"{e}, retrying with new tx params...")
                for key in ("gasPrice", "maxFeePerGas", "maxPriorityFeePerGas", "gas", "chainId"):
                    if key in tx_params:
                        tx_params.pop(key)
                continue
        return False

    @NetworkClientAware.retry
    async def approved_amount(
            self, token: types.Contract, spender: types.Contract, owner: types.Address | None = None
    ) -> TokenAmount:
        """
        Get approved amount of token.

        Args:
            token (Contract): the contract evm_address or instance of token.
            spender (Contract): the spender evm_address, contract evm_address or instance.
            owner (Optional[Address]): the owner evm_address. (imported to client evm_address)

        Returns:
            TokenAmount: the approved amount.

        """
        contract_address, abi = await self.client.contracts.get_contract_attributes(token)
        contract = await self.client.contracts.default_token(contract_address)
        spender, abi = await self.client.contracts.get_contract_attributes(spender)
        if not owner:
            owner = self.client.w3_account.address

        return TokenAmount(
            amount=await contract.functions.allowance(
                Web3.to_checksum_address(owner),
                Web3.to_checksum_address(spender)
            ).call(),
            decimals=await self.client.transactions.get_decimals(contract=contract.address),
            wei=True
        )

    @NetworkClientAware.retry
    async def wait_for_receipt(
            self, tx_hash: str | _Hash32, timeout: int | float = 120, poll_latency: float = 0.1
    ) -> dict[str, Any]:
        """
        Wait for a transaction receipt.

        Args:
            tx_hash (Union[str, _Hash32]): the transaction hash.
            timeout (Union[int, float]): the receipt waiting timeout. (120)
            poll_latency (float): the poll latency. (0.1 sec)

        Returns:
            Dict[str, Any]: the transaction receipt.

        """
        try:
            return dict(await self.client.w3.eth.wait_for_transaction_receipt(
                transaction_hash=tx_hash, timeout=timeout, poll_latency=poll_latency
            ))
        except TimeExhausted:
            return {}

    async def transfer(self, amount: TokenAmount,
                       recipient: str | ChecksumAddress,
                       token: types.Contract = None,
                       encoded_data = b'',
                       ):
        if isinstance(recipient, str):
            recipient = Web3.to_checksum_address(recipient)

        if token:
            contract = await self.client.contracts.get(contract=token)
            if not encoded_data:
                args = TxArgs(
                    to=recipient,
                    value=self.client.w3.to_wei(amount.Wei, unit='wei'),
                )
                encoded_data = contract.encode_abi('transfer', args=args.tuple())
            tx_params = TxParams(
                to=contract.address,
                data=encoded_data,
                value=self.client.w3.to_wei(0, unit='wei')
            )
        else:
            tx_params = TxParams(
                to=recipient,
                data=encoded_data,
                value=self.client.w3.to_wei(amount.Wei, unit='wei')
            )

        return await self.client.transactions.send_tx(tx_params)

    @NetworkClientAware.retry
    async def approve(
            self, token: types.Contract, spender: types.Address, amount: types.Amount | None = None,
            gas_limit: types.GasLimit | None = None, nonce: int | Nonce | None = None
    ) -> Tx:
        """
        Approve token spending for specified evm_address.

        Args:
            token (Contract): the contract evm_address or instance of token to approve.
            spender (Address): the spender evm_address, contract evm_address or instance.
            amount (Optional[TokenAmount]): an amount to approve. (infinity)
            gas_limit (Optional[GasLimit]): the gas limit in Wei. (parsed from the network)
            nonce (Optional[int]): a nonce of the sender evm_address. (get it using the 'nonce' function)

        Returns:
            Tx: the instance of the sent transaction.
        """
        spender = Web3.to_checksum_address(spender)
        contract_address, abi = await self.client.contracts.get_contract_attributes(token)
        contract = await self.client.contracts.default_token(contract_address)

        if amount is None:
            amount = CommonValues.InfinityInt
        elif isinstance(amount, (int, float)):
            amount = TokenAmount(
                amount=amount,
                decimals=await self.client.transactions.get_decimals(contract=contract.address)
            ).Wei
        else:
            amount = amount.Wei

        if not nonce:
            nonce = Nonce(await self.client.wallet.nonce())

        tx_args = TxArgs(
            spender=spender,
            amount=amount
        )

        tx_params = TxParams(
            nonce=Nonce(nonce),
            to=contract.address,
            data=contract.encode_abi('approve', args=tx_args.tuple())
        )

        if gas_limit:
            if isinstance(gas_limit, int):
                gas_limit = TokenAmount(amount=gas_limit, wei=True, decimals=self.client.network.decimals)
            tx_params['gas'] = gas_limit.Wei

        return await self.sign_and_send(tx_params=tx_params)

    @NetworkClientAware.retry
    async def approve_interface(self, token: types.Contract, spender: types.Address, amount: types.Amount | None = None,
                                approve_inf: bool = False) -> bool:
        balance = await self.client.wallet.balance(token=token)
        if isinstance(token, RawContract):
            token_symbol = token.title
        elif isinstance(token, AsyncContract):
            token_symbol = await token.functions.symbol().call()
        else:
            token_symbol = await self.client.wallet.get_token_symbol(token)
        if balance.Wei <= 0:
            self.logger.error(f"Tried to approve token {token_symbol} but balance is zero")
            return False

        if isinstance(token, RawContract | AsyncContract):
            if token.address == CommonValues.ZeroAddress:
                self.logger.debug(f"Tried to approve native token, returning True")
                return True
        else:
            if token == CommonValues.ZeroAddress:
                self.logger.debug(f"Tried to approve native token, returning True")
                return True

        if not amount and not approve_inf:
            amount = balance
        elif not amount and approve_inf:
            amount = TokenAmount(CommonValues.InfinityInt, 18, True)

        approved = await self.client.transactions.approved_amount(
            token=token,
            spender=spender,
            owner=self.client.w3_account.address
        )

        if amount.Wei <= approved.Wei:
            self.logger.success(f"{approved} {token_symbol} already approved for {spender}")
            return True

        tx = await self.client.transactions.approve(
            token=token,
            spender=spender,
            amount=amount
        )

        if isinstance(tx, Tx):
            receipt = await self.wait_for_receipt(tx_hash=tx.hash, timeout=300, poll_latency=0.5)
        else:
            return False

        if receipt:
            self.logger.success(f"{amount} {token_symbol} successfully approved for {spender}")
            return True

        return False

    @NetworkClientAware.retry
    async def get_decimals(self, contract: types.Contract) -> int:
        contract_address, abi = await self.client.contracts.get_contract_attributes(contract)
        contract = await self.client.contracts.default_token(contract_address=contract_address)
        return await contract.functions.decimals().call()

    async def sign_message(self, message: str | None = None, typed_data: dict | None = None, full_message: bool = False,
                           message_hash_bytes = None) -> SignedMessage | None:
        """
        Sign message

        Args:
        message: str
        typed_data: dict {'domain':..., 'types':..., 'values':...}
        Returns:
            SignedMessage
        """
        if message:
            msghash = encode_defunct(text=message)
        elif typed_data and full_message:
            msghash = encode_typed_data(full_message=typed_data)

        elif typed_data:
            domain_data = typed_data['domain']
            message_types = typed_data['types']
            try:
                message_data = typed_data['values']
            except KeyError:
                message_data = typed_data['message']

            msghash = encode_typed_data(
            domain_data=domain_data,
            message_types=message_types,
            message_data=message_data
            )
        elif message_hash_bytes:
            if isinstance(message_hash_bytes, bytes):
                message_hash_bytes = message_hash_bytes.hex()

            msghash = encode_defunct(hexstr=message_hash_bytes)
        else:
            return None

        return self.client.w3.eth.account.sign_message(signable_message=msghash, private_key=self.client.w3_account.key)

    async def wrap_native_token(self, amount: TokenAmount):
        """
        Оборачивает нативную монету сети в wrapped версию (WETH, WBNB, WMATIC и т.д.)
        """
        wrapped_token_contract: AsyncContract = await self.client.contracts.get(
            self.client.network.wrapped_token_address,
            abi=DefaultABIs.Wrapped_Native_Token
        )
        transaction_params = TxParams(
            value=self.client.w3.to_wei(amount.Wei, unit="wei"),
            data=wrapped_token_contract.encode_abi("deposit"),
            to=self.client.network.wrapped_token_address
        )
        return await self.send_tx(transaction_params)

    async def unwrap_native_token(self, amount: TokenAmount):
        """
        Разворачивает wrapped токен обратно в нативный (WETH -> ETH, WBNB -> BNB и т.д.)
        """
        wrapped_token_contract: AsyncContract = await self.client.contracts.get(
            self.client.network.wrapped_token_address,
            abi=DefaultABIs.Wrapped_Native_Token
        )
        transaction_params = TxParams(
            value=self.client.w3.to_wei(0, unit="wei"),
            data=wrapped_token_contract.encode_abi("withdraw", [amount.Wei]),
            to=self.client.network.wrapped_token_address
        )
        return await self.send_tx(transaction_params)
