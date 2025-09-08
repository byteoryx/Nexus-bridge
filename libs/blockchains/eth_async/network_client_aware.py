from __future__ import annotations

from functools import wraps
import asyncio
from typing import TypeVar, TYPE_CHECKING

from aiohttp.client_exceptions import ClientHttpProxyError, ClientProxyConnectionError # proxy errors
from aiohttp.client_exceptions import ClientResponseError # RPC response errors

from core.logger import get_logger
from core.init_settings import settings
from libs.blockchains.eth_async.exceptions import InsufficientFundsException, NonceException, GasException, \
    AmountExceedsBalanceException, TransactionException

if TYPE_CHECKING:
    from libs.blockchains.eth_async.ethclient import NetworkClient

T = TypeVar('T')


class NetworkClientAware:
    """Базовый класс для всех классов, которые используют NetworkClient"""
    def __init__(self, 
                 client: "NetworkClient",
                 log_context,
                 retry_delay = settings.general.retry_delay, 
                 number_of_retries = settings.general.number_of_retries,
                 debug = settings.logging.debug_logging,
                 ) -> None:
        self.client = client
        self.__debug = debug
        self.__retry_delay = retry_delay
        self.__number_of_retries = number_of_retries
        
        if log_context:
            self.logger = get_logger(class_name=f"EthClient: {client.network.name}", **log_context)
        else:
            self.logger = get_logger(class_name=f"EthClient: {client.network.name}")

    @staticmethod
    def retry(func):
        """Общий декоратор retry для всех классов"""

        @wraps(func)
        async def wrapper(self, *args, **kwargs):
            tx_params = None

            if 'tx_params' in kwargs:
                tx_params = kwargs['tx_params']

            elif args:
                import inspect
                sig = inspect.signature(func)
                param_names = list(sig.parameters.keys())

                if 'self' in param_names:
                    param_names.remove('self')

                if 'tx_params' in param_names:
                    tx_params_index = param_names.index('tx_params')
                    if len(args) > tx_params_index:
                        tx_params = args[tx_params_index]

            for num in range(1, self.__number_of_retries + 1):
                try:
                    # self._logger.info(f'[{self.account.name}] | Retry attempt {num}/{self.rpc_config.max_retries}')
                    result = await func(self, *args, **kwargs)

                    if result is False:
                        self.logger.warning(
                            f"Attempt {num}/{self.__number_of_retries} for RPC failed, "
                            f"sleeping for {self.__retry_delay} seconds")
                        await asyncio.sleep(self.__retry_delay)
                        await self.client.increase_rpc_retry_count()
                        continue

                    return result

                except (ClientProxyConnectionError, ClientHttpProxyError):
                    await self.client.increase_rpc_retry_count()
                    # proxy errors
                    raise

                except ClientResponseError:
                    # common for just an error getting answer from RPC but not regarded to proxy
                    await self.client.change_rpc()
                    continue

                except Exception as e:
                    if tx_params and self.__debug:
                        self.logger.debug(f"Exception {e.__class__.__name__} occurred with tx_params: {tx_params}")

                    if any(phrase in str(e).lower() for phrase in ("proxy", "service unavailable", "503")):
                        raise ClientProxyConnectionError

                    if any(phrase in str(e).lower() for phrase in ("insufficient", "not enough")):
                        raise InsufficientFundsException(f"Insufficient funds for transaction")

                    if any(phrase in str(e).lower() for phrase in ("nonce too low",
                                                                   "replacement transaction underpriced",
                                                                   "invalid nonce")):
                        raise NonceException(f"Nonce too low")
                    
                    if any(phrase in str(e).lower() for phrase in ("exceeds allowance",)):
                        raise GasException(f"Gas exceeds allowance")

                    if any(phrase in str(e).lower() for phrase in ("intrinsic gas too low",)):
                            raise GasException(f"Need to increase gas")
                        
                    if any(phrase in str(e).lower() for phrase in ("fee cap less than block",
                                                                   "less than block base fee")):
                        raise GasException(f"Gas fee cap less than block base fee, increase gas limit")

                    if any(phrase in str(e).lower() for phrase in ("exceeds balance",
                                                                   "transfer amount exceeds balance")):
                        raise AmountExceedsBalanceException(f"Transfer amount exceeds balance")

                    if any(phrase in str(e).lower() for phrase in ("failed to send tx",
                                                                   "'code': -32603")):
                        raise TransactionException(str(e))

                    if any(phrase in str(e).lower() for phrase in ("execution reverted",)):
                        raise e

                    self.logger.error(f"Attempt {num}/{settings.general.number_of_retries} for RPC failed due to: "
                                      f"{e.__class__.__name__}: {str(e)}")
                    await self.client.increase_rpc_retry_count()

                    if "ClientConnectorError.__init__()" in str(e):
                        self.logger.warning(f"Above error is an aiohttp error")

                    if num == self.__number_of_retries: # if this is final iteration
                        raise e

                    self.logger.warning(f"Sleeping for {self.__retry_delay} seconds")
                    await asyncio.sleep(self.__retry_delay)

            # Если все попытки исчерпаны и не было исключения
            raise Exception(f"Failed action {func.__name__} with: args = {args}, kwargs = {kwargs}")

        return wrapper
