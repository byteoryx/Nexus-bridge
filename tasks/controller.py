import asyncio
from functools import wraps
from http.cookiejar import CookieJar

import curl_cffi

from core.db_utils.models import Account
from core.db_utils.db import db
from core.init_settings import settings
from core.logger import get_logger
from libs.blockchains.eth_async.data.models import Network
from libs.blockchains.eth_async.ethclient import NetworkClient, EthClient
from libs.requests.session import BaseAsyncSession
from libs.requests.web_requests import RequestsClient
from utils.utils import get_caller_function, excname


class Controller:
    def __init__(self, account: Account, log_context):
        self.account = account
        self.logger = get_logger(class_name=self.__class__.__name__, **log_context)
        self.log_context = log_context
        self._proxy = account.proxy
        self.async_session: BaseAsyncSession | None = None
        self.requests_client: RequestsClient | None = None
        self.eth_client: EthClient | None = None


    @property
    def proxy(self):
        return self._proxy

    def _create_async_session(self, proxy: str | None = None) -> BaseAsyncSession:
        cookies = self.async_session.cookies.jar if self.async_session else CookieJar()

        return BaseAsyncSession(
            account=self.account,
            proxy=proxy or self.account.proxy,
            cookies=cookies,
            verify=False,
        )  # можно сюда тоже прокинуть прокси, но пока не буду. Сейчас прокси либо аккаунта,
        # либо внешние применяются напрямую в других клиентах. Но в сессию тоже можно было бы применить

    def _create_requests_client(self) -> RequestsClient:
        return RequestsClient(
            controller=self,
            account=self.account,
            session=self.async_session,
            log_context=self.log_context,
        )

    def _create_eth_client(self, proxy: str | None = None) -> EthClient:
        return EthClient(
            self.account.evm_private_key,
            proxy=proxy or self.account.proxy,
            networks=[network for network in settings.networks.list()],
            log_context=self.log_context
        )


    async def __aenter__(self, proxy: str | None = None, new = True):
        self.async_session = self._create_async_session(proxy)

        self.eth_client = self._create_eth_client(proxy)
        # self.aptos_client = self._create_aptos_client(proxy)

        if new:
            self.requests_client = self._create_requests_client()

        async with self.eth_client:  # , self.aptos_client
            return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        try:
            if self.eth_client:
                await self.eth_client.close()

            if self.async_session:
                await self.async_session.close()
        except Exception as e:
            self.logger.error(f"Error during closing sessions: {excname(e)} {str(e)}")

    async def change_proxy(self, new_proxy: str = None):
        if settings.logging.debug_logging:
            self.logger.debug(f"change_proxy {get_caller_function()}")

        self.logger.info(f"Changing proxy from {self.eth_client.proxy}")
        if not new_proxy:
            new_proxy = db.get_free_proxy()
            if not new_proxy:
                db.reset_proxies()
                new_proxy = db.get_free_proxy()
                if not new_proxy:
                    raise Exception("Failed to get new proxy even after reset")

        await self.__aexit__(None, None, None)
        await self.__aenter__(new_proxy, new=False)
        self.requests_client.async_session = self.async_session

        self.logger.success(f"Proxy successfully changed to {new_proxy}")

    async def get_balances(self, networks_list: list[str], token = None):
        balances = {}
        async with self.eth_client:
            for network in networks_list:
                network_client: NetworkClient = getattr(self.eth_client, network)
                balances[network] = await self.get_balance_for_network(network_client, network, token)
        return balances

    async def get_balances_usd(self, networks_list: list[str]):
        self.logger.info(f"Getting balances for networks: {', '.join(networks_list)}")
        balances = await self.get_balances(networks_list)
        balances_usd: dict[str, dict[str, float]] = {}
        for network, balance in balances.items():

            price = await self.get_price_for_native(network)
            balances_usd[network] = {"balance": (balance * price), "price": price}
            break

        return balances_usd

    async def get_price_for_native(self, network: str):
        attempt = 0
        price = None
        for attempt in range(1, settings.general.number_of_retries + 1):
            try:
                if "BSC" in network:
                    price = await self.get_token_price_from_binance('BNB')
                elif "Polygon" in network:
                    price = await self.get_token_price_from_binance('POL')
                elif "Zeta" in network:
                    price = await self.get_token_price_from_bybit('ZETA')
                elif "Cyber" in network:
                    price = await self.get_token_price_from_bybit('CYBER')
                elif "Celo" in network:
                    price = await self.get_token_price_from_bybit('CELO')
                elif "Degen" in network:
                    price = await self.get_token_price_from_bybit('DEGEN')
                else:  # "Eth" in network:
                    price = await self.get_token_price_from_binance('ETH')

            except curl_cffi.requests.exceptions.ProxyError:
                await self.change_proxy()

            except Exception as e:
                self.logger.error(f"{e.__class__.__name__} Error getting price for {network}. Attempt {attempt}")

        if not price:
            raise Exception(f"Failed to get price for {network} for {attempt} attempts")

        return price

    async def get_balance_for_network(self, network_client: NetworkClient, network: str, token = None):
        try:
            for i in range(network_client.rpc_config.max_retries):
                return float((await network_client.wallet.balance(token)).Ether)
        except Exception as e:
            self.logger.error(f"Error getting balance for {network}: {str(e)}")
            if "415" in str(e):
                await network_client.change_rpc()
            if any(code in str(e).lower() for code in ("502", "503")):
                await self.change_proxy()
                await network_client.change_rpc()

    @staticmethod
    def retry(func):
        """Decorator for retrying operations"""

        @wraps(func)
        async def wrapper(self, *args, **kwargs):
            for num in range(1, settings.general.number_of_retries + 1):
                try:
                    self._logger.info(
                        f'[{self.account.name}] | Retry attempt {num}/{settings.general.number_of_retries}')
                    result = await func(self, *args, **kwargs)

                    # Если функция вернула False, продолжаем попытки
                    if result is False:
                        self._logger.warning(
                            f"Attempt {num} failed, sleeping for {settings.general.retry_delay} seconds")
                        await asyncio.sleep(settings.general.retry_delay)
                        continue

                    # Если функция вернула True или любое другое значение, возвращаем его
                    return result

                except Exception as e:
                    self._logger.error(f"Attempt {num}/{settings.general.number_of_retries} failed due to: {e}")
                    if num == settings.general.number_of_retries:
                        # На последней попытке пробрасываем ошибку выше
                        raise
                    self._logger.warning(f"Sleeping for {settings.general.retry_delay} seconds")
                    await asyncio.sleep(settings.general.retry_delay)

            # Если все попытки исчерпаны и не было исключения
            return False

        return wrapper

    async def get_token_price_from_coingecko(self, token_address: str, network: Network):
        # Добавить получение имени сети от коингеко через отдельный запрос
        # # Нужен апи ключ
        # token_id = {
        #     "SOL": 'solana',
        #     "USDC": 'usd-coin',
        #     "USDT": 'tether',
        #     "tETH": 'ethereum'
        # }
        #
        # if token.upper() in ["USDC", "USDT"]:
        #     return 1.0

        url = (f"https://api.coingecko.com/api/v3/simple/token_price/id={network.name.lower()}"
               f"&contract_addresses={token_address}&vs_currencies=usd")

        try:
            response = await self.requests_client.get(url)
            print(response)

            return response.get(token_address, {}).get('usd', None)

        except Exception as e:
            raise RuntimeError(f"Ошибка при запросе цены токена: {str(e)}") from e

    async def get_token_price_from_binance(self, token: str, second_token: str = 'USDT') -> float:
        for i in range(1, settings.general.number_of_retries):
            if token.upper() in ('USDC', 'USDT', 'DAI', 'CEBUSD', 'BUSD', 'XDAI'):
                return 1
            if token == 'WETH':
                token = 'ETH'
            if token == 'WBTC':
                token = 'BTC'

            url = f"https://api.binance.com/api/v3/depth?limit=1&symbol={token.upper()}{second_token.upper()}"
            response = await self.requests_client.get(url)
            if response:
                if response.get("msg") and "Invalid" in response.get("msg"):
                    raise ValueError(f"Token symbol {token.upper()} not found on Binance")
                else:
                    return float(response["asks"][0][0])

    async def get_token_price_from_bybit(self, token: str, second_token: str = 'USDT') -> float:
        for i in range(1, settings.general.number_of_retries):
            if token.upper() in ('USDC', 'USDT', 'DAI', 'CEBUSD', 'BUSD', 'XDAI'):
                return 1
            if token == 'WETH':
                token = 'ETH'
            if token == 'WBTC':
                token = 'BTC'

            url = f"https://api.bybit.com/v5/market/tickers"
            params = {
                "category": "spot",
                "symbol": token.upper() + second_token.upper()
            }
            response = await self.requests_client.get(url=url, params=params)
            if response:
                if response["retCode"] == 0:
                    return float(response["result"]["list"][0]["lastPrice"])
                else:
                    raise ValueError(f"Error getting token price from Bybit: {response['retMsg']}")
