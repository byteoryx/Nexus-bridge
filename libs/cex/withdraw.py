import asyncio

import ccxt.async_support as ccxt

from core.init_settings import settings
from core.logger import get_logger
from libs.blockchains.eth_async.ethclient import NetworkClient
from utils.utils import excname


class CexWithdraw:
    def __init__(self, cex_name, log_context):
        self.log_context = log_context
        self.cex_name = cex_name
        self.logger = get_logger(
            class_name=cex_name.capitalize(),
            **self.log_context
        )
    
    eth_cex_networks_dict = {
        "bitget": {
            "base": "BASE",
            "optimism": "OPTIMISM",
            "arbitrum": "ARBONE",
        },
        "okx": {
            "base": "BASE",
            "optimism": "OPTIMISM",
            "arbitrum": "ARBONE",
        },
        "mexc": {
            "base": "BASE",
            "optimism": "OPTIMISM",
            "arbitrum": "ARBITRUM",
        },
    }

    async def wait_for_withdraw(self, cex, withdrawal):
        first_status = None
        for _ in range(20):
            withdrawals = await cex.fetch_withdrawals()
            for withdrawal_data in withdrawals:
                if withdrawal_data["id"] == withdrawal["id"]:
                    if not first_status:
                        first_status = withdrawal_data["status"]
                    # valid for mexc, okx, bitget

                    if withdrawal_data["status"] != first_status:
                        self.logger.success(f"Withdrawal tx id {withdrawal_data['txid']} done, "
                                            f"status: {withdrawal_data['status']}")
                        return True

                    else:
                        self.logger.warning(f"Withdrawal {withdrawal_data['id']} not ready,"
                                            f" status: {withdrawal_data['status']}")

            await asyncio.sleep(30)
        else:
            return False

    async def withdraw(self, withdraw_amount: float, network_name: str, network_client: NetworkClient):
        cex_settings = getattr(settings.cex, self.cex_name)
        cex = getattr(ccxt, self.cex_name)({
            "apiKey": cex_settings.api_key,
            "secret": cex_settings.api_secret_key,
            "password": cex_settings.passphrase,
            "enableRateLimit": True,
            "verbose": False,
            # "options": {
            #     "fetchCurrencies": True,
            # }
        })

        for attempt in range(settings.general.number_of_retries):
            try:
                code = network_client.network.coin_symbol
                params = {'network': self.eth_cex_networks_dict[self.cex_name][network_name.lower()]}

                self.logger.info(f"Starting to withdraw {withdraw_amount} {network_client.network.coin_symbol}"
                                 f" to {network_name.capitalize()} from {self.cex_name.capitalize()}")
                withdrawal = await cex.withdraw(code, withdraw_amount, network_client.w3_account.address, None, params)

                try:
                    return await self.wait_for_withdraw(cex, withdrawal)
                except ccxt.BaseError as e:
                    self.logger.error(f"Network error {excname(e)} while checking withdraw status, "
                                      "waiting for 2 minutes and assuming it was ok")
                    await asyncio.sleep(120)
                    return True
            except ccxt.BaseError as e:
                self.logger.error(f"{excname(e)} {str(e)}")
                await asyncio.sleep(settings.general.retry_delay)
            finally:
                await cex.close()
        else:
            self.logger.error(f"Withdrawal {withdraw_amount} {network_client.network.coin_symbol} failed")
            return False
