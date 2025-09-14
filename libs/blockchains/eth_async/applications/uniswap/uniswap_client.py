from typing import Literal

from core.logger import get_logger
from libs.blockchains.eth_async.base_evm_task_class import BaseEVMTaskClass
from libs.blockchains.eth_async.data.models import RawContract, CommonValues
from libs.blockchains.omnichain_functions import resolve_token_addresses
from libs.blockchains.omnichain_models import TokenAmount
from libs.blockchains.eth_async.ethclient import EthClient
from libs.blockchains.eth_async.exceptions import InsufficientFundsException
from libs.requests.web_requests import RequestsClient


class Uniswap(BaseEVMTaskClass["Uniswap"]):
    _headers = {
        'origin': 'https://app.uniswap.org',
        'referer': 'https://app.uniswap.org/',
        'x-api-key': 'JoyCGj29tT4pymvhaGciK4r1aIPvqW6W53xT1fwo',
        'x-app-version': '',
        'x-request-source': 'uniswap-web',
        'x-universal-router-version': '2.0',
    }
    _base_url = "https://trading-api-labs.interface.gateway.uniswap.org/v1/"
    _gas_strategy = {
        'displayLimitInflationFactor': 1.15,
        'limitInflationFactor': 1.15,
        'maxPriorityFeeGwei': 9,
        'minPriorityFeeGwei': 2,
        'percentileThresholdFor1559Fee': 75,
        'priceInflationFactor': 1.5,
    }

    CONTRACTS = None

    def __init__(self, eth_client: EthClient, requests_client: RequestsClient, log_context):
        self._requests_client = requests_client
        self._eth_client = eth_client
        self._logger = get_logger(class_name=self.__class__.__name__, **log_context)
        self._current_network = None
        super().__init__(self)


    async def _get_quote(self, amount: int | TokenAmount,
                         token_in: str | RawContract,
                         token_out: str | RawContract,
                         slippage: float,
                         exact: Literal['input', 'output']):
        if isinstance(token_in, RawContract):
            token_in = CommonValues.ZeroAddress if token_in.is_native_token else token_in.address
        else:
            token_in = token_in

        if isinstance(token_out, RawContract):
            token_out = CommonValues.ZeroAddress if token_out.is_native_token else token_out.address
        else:
            token_out = token_out

        url = self._base_url + "quote"
        body = {
            'amount': str(amount.Wei) if isinstance(amount, TokenAmount) else str(amount),
            'hooksOptions': "V4_NO_HOOKS",
            'slippageTolerance': slippage,
            # 'autoSlippage': 'DEFAULT',
            'gasStrategies': [self._gas_strategy],
            'protocols': ['V2'],
            'swapper': self.network_client.w3_account.address,
            'tokenIn': token_in,
            'tokenInChainId': self.network_client.network.chain_id,
            'tokenOut': token_out,
            'tokenOutChainId': self.network_client.network.chain_id,
            'type': 'EXACT_' + exact.upper(),
            'urgency': 'normal',
        }
        return await self._requests_client.post(url, [200],
                                                lambda r: (r.json()['quote'], r.json()['permitData']),
                                                additional_headers=self._headers, json=body)


    async def _request_swap_data(self, quote: dict, permit_data: dict | None, permit_sign: dict | None) -> dict:
        url = self._base_url + 'swap'
        body = {
            # 'deadline': int(time.time() + 300),
            'gasStrategies': [self._gas_strategy],
            'quote': quote,
            'refreshGasPrice': True,
            'simulateTransaction': True,
            'urgency': 'normal',
        }
        if permit_sign is not None:
            body['permitData'] = permit_data
            body['signature'] = permit_sign
            #"errorCode":"ResourceNotFound","detail":"Failed to fetch gas fee and/or simulate transaction"
        try:
            return await self._requests_client.post(url, [200], lambda r: r.json()['swap'],
                                                    additional_headers=self._headers, json=body)
        except Exception as e:
            if "Failed to fetch gas fee" in str(e):
                raise InsufficientFundsException(f"Insufficient funds for swap")
            raise e


    async def _sign_permit(self, permit_data: dict | None) -> str | None:
        if permit_data:
            permit_signed = await self.network_client.transactions.sign_message(typed_data=permit_data)
            self._logger.success(f"Signed permit data for swap")
            return '0x' + permit_signed.signature.hex()


    async def _swap(self, direction: Literal["input", "output"],
                    amount: int | TokenAmount,
                    token_from: RawContract | str,
                    token_to: RawContract | str,
                    slippage: float = 0.5,
                    from_decimals: int = 18,
                    to_decimals: int = 18,
                    approve_amount: int | TokenAmount = None):
        token_from, token_to, from_currency, to_currency = resolve_token_addresses(self, token_from, token_to)

        quote, permit_data = await self._get_quote(amount, token_from, token_to, slippage, direction)
        # self._logger.debug(f"Quote: {quote}")
        # self._logger.debug(f"Permit data: {permit_data}")
        amount = TokenAmount(int(quote['route'][0][0]['amountIn']), from_decimals, True)
        from_token_symbol = quote['route'][0][0]['tokenIn']['symbol']
        to_token_symbol = quote['route'][0][0]['tokenOut']['symbol']

        self._logger.info(f"Swap on Uniswap: {amount} {from_currency} -> {to_currency}")

        permit = await self._sign_permit(permit_data)
        swap_data = await self._request_swap_data(quote, permit_data, permit)
        if token_from != CommonValues.ZeroAddress:
            if isinstance(approve_amount, str) and approve_amount == "infinity":
                approve_amount = None
                approve_inf = True
            else:
                approve_inf = False

            spender = swap_data["to"]
            approve = await self.network_client.transactions.approve_interface(token=token_from,
                                                                     spender=spender,
                                                                     amount_in_tx=amount,
                                                                     amount_to_approve=approve_amount,
                                                                     approve_inf=approve_inf)
            if not approve:
                raise Exception(f"Failed to approve {approve_amount} {token_from} to {spender}")


        tx_hash = await self.network_client.transactions.send_tx(swap_data)

        to_decimals = int(quote['route'][0][0]['tokenOut']['decimals'])
        try:
            amount_to = TokenAmount(int(quote['route'][0][0]['amountOut']), to_decimals, True)
        except KeyError:
            try:
                amount_to = TokenAmount(int(quote['route'][0][1]['amountOut']), to_decimals, True)
            except KeyError:
                self._logger.warning(f"Failed to get amountOut from quote: {quote}")
                amount_to = "'Not found in quote'"

        self._logger.success(f"Successfully swapped {amount} {from_token_symbol} to {amount_to} {to_token_symbol}")
        return tx_hash


    async def swap_exact_out(self, amount_to: int | TokenAmount,
                            token_from: RawContract | str,
                            token_to: RawContract | str,
                            slippage: float = 0.5,
                            from_decimals: int = 18,
                            to_decimals: int = 18,
                             approve_amount: int | TokenAmount = None):
        return await self._swap("output", amount_to, token_from, token_to,
                                slippage, from_decimals, to_decimals, approve_amount)

    async def swap_exact_in(self, amount_from: int | TokenAmount,
                            token_from: RawContract | str,
                            token_to: RawContract | str,
                            slippage: float = 0.5,
                            from_decimals: int = 18,
                            to_decimals: int = 18,
                            approve_amount: int | TokenAmount = None):
        return await self._swap("input", amount_from, token_from, token_to,
                                slippage, from_decimals, to_decimals, approve_amount)
