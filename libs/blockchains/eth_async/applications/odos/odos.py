from core.logger import get_logger
from libs.blockchains.eth_async.base_evm_task_class import BaseEVMTaskClass
from libs.blockchains.eth_async.data.models import RawContract, CommonValues
from libs.blockchains.omnichain_functions import resolve_token_addresses
from libs.blockchains.omnichain_models import TokenAmount
from libs.blockchains.eth_async.ethclient import EthClient
from libs.requests.web_requests import RequestsClient
from utils.utils import log_sleep


class Odos(BaseEVMTaskClass["Odos"]):
    _headers = {
        'origin': 'https://app.odos.xyz',
        'priority': 'u=1, i',
        'referer': 'https://app.odos.xyz/',
        'sec-fetch-dest': 'empty',
        'sec-fetch-mode': 'cors',
        'sec-fetch-site': 'same-site',
    }

    CONTRACTS = None

    def __init__(self, eth_client: EthClient, requests_client: RequestsClient, log_context):
        self._requests_client = requests_client
        self._eth_client = eth_client
        self._logger = get_logger(class_name=self.__class__.__name__, **log_context)
        self._current_network = None
        super().__init__(self)


    async def get_quote(self, from_token_address: str, to_token_address: str, amount_in_wei: int, slippage: float = 1.0):
        """
        slippage = 0.5
        """
        quote_url = "https://api.odos.xyz/sor/quote/v3"

        gas_price = await self.network_client.transactions.gas_price()

        payload = {
           "chainId": self.network_client.network.chain_id,
           "inputTokens":[
              {
                 "tokenAddress":from_token_address,
                 "amount": str(amount_in_wei)
              }
           ],
           "outputTokens":[
              {
                 "tokenAddress":to_token_address,
                 "proportion":1
              }
           ],
           "gasPrice": float(gas_price.Ether) * 10**9,
           "slippageLimitPercent": slippage,
           "sourceBlacklist":[

           ],
           "pathViz": True,
           # "referralCode":1,
           "compact": True,
           "likeAsset": True,
           "disableRFQs": True,
           "userAddr": self.network_client.w3_account.address,
           # "referralFee":0.0015,
           # "referralFeeRecipient":""
        }
        # self._logger.debug(f"Payload: {payload}")

        return await self._requests_client.post(quote_url, [200], additional_headers=self._headers,
                                                json=payload)

    async def assemble_transaction(self, path_id):
        assemble_url = "https://api.odos.xyz/sor/assemble"

        payload = {
            "userAddr": self.network_client.w3_account.address,
            "pathId": path_id,
            "simulate": True,
        }

        return await self._requests_client.post(assemble_url, [200], additional_headers=self._headers,
                                                json=payload)


    async def swap(self,
                    amount: TokenAmount,
                    token_from: RawContract | str,
                    token_to: RawContract | str,
                    slippage: float = 0.5,
                    approve_amount: int | TokenAmount = None):
        token_from, token_to, from_currency, to_currency = resolve_token_addresses(self, token_from, token_to)
        self._logger.info(f"Swap on Odos: {amount} {from_currency} -> {to_currency}")

        path_id = (await self.get_quote(token_from, token_to, amount.Wei, slippage))["pathId"]
        transaction_data = (await self.assemble_transaction(path_id))["transaction"]
        contract_address = self.network_client.w3.to_checksum_address(transaction_data["to"])

        if token_from != CommonValues.ZeroAddress:
            if isinstance(approve_amount, str) and approve_amount == "infinity":
                approve_amount = None
                approve_inf = True
            else:
                approve_inf = False

            approve = await self.network_client.transactions.approve_interface(token=token_from,
                                                                     spender=contract_address,
                                                                     amount_in_tx=amount,
                                                                     amount_to_approve=approve_amount,
                                                                     approve_inf=approve_inf)
            await log_sleep(self)

        tx_hash = await self.network_client.transactions.send_tx(transaction_data)
        return True
