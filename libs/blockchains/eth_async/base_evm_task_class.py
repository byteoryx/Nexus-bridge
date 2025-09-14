from typing import TypeVar, Generic, Any

from web3.contract import AsyncContract

from libs.blockchains.eth_async.data import types
from libs.blockchains.eth_async.data.models import RawContract, Network
from libs.blockchains.eth_async.ethclient import NetworkClient


# Создаем TypeVar для дочерних классов
T = TypeVar('T', bound='BaseEVMTaskClass')

class BaseEVMTaskClass(Generic[T]):
    def __init__(self, class_object: Any):
        self._class_object = class_object

    @property
    def current_network(self) -> str:
        """Get current network name"""
        return self._class_object._current_network

    @property
    def network_client(self) -> NetworkClient:
        """Get current network client"""
        try:
            try:
                return getattr(self._class_object.eth_client, self._class_object._current_network)
            except AttributeError:
                return getattr(self._class_object._eth_client, self._class_object._current_network)
        except TypeError as e:
            try:
                logger = self._class_object.logger
            except AttributeError:
                logger = self._class_object._logger
            logger.error(f"Network client not found, probably network not set: {e}")

    async def read_contract(self, contract: types.Contract, func_name: str, *args, **kwargs):
        return await self.network_client.contracts.read_contract_function(contract, func_name, *args, **kwargs)

    def use_network(self, network_name: str) -> T:
        """
        Set network to use for subsequent operations

        Usage:
            sign.use_network('arbitrum').register_schema(...)
        """
        network_name = network_name.lower()
        # try:
        #     if self._class_object.CONTRACTS:
        #         if network_name not in self._class_object.CONTRACTS:
        #             raise ValueError(f"Network {network_name} not supported. Available networks:"
        #                              f" {', '.join(self._class_object.CONTRACTS.keys())}")
        # except NameError:
        #     pass
        self._class_object._current_network = network_name
        # self._class_object.logger = get_logger(class_name=f"{self._class_object.__class__.__name__}: "
        #                                                   f"{self.current_network.capitalize()}", **log_context)
        return self._class_object

    async def _get_async_contract(self, destination_chain: Network) -> AsyncContract:
        """Get AsyncContract instance for current network"""
        string = f"{self.current_network}_to_{destination_chain.name}".lower()

        contract = await self._get_raw_contract(string)

        return await self.network_client.contracts.get(contract=contract)

    async def _get_raw_contract(self, string) -> RawContract:
        """Get RawContract instance for current network"""
        current_network = self._class_object._current_network
        contract = self._class_object.CONTRACTS.get(string)
        if not contract:
            contract = self._class_object.CONTRACTS.get(self._normalize_network_name(current_network))

        if not contract:
            raise ValueError(f"Network {current_network} not supported. Available networks in {self.__class__.__name__}:"
                                          f" {', '.join(self._class_object.CONTRACTS.keys())}")

        return contract

    @staticmethod
    def _normalize_network_name(network_name: str) -> str:
        """Convert network name to proper case"""
        # Специальные случаи
        if network_name.lower() == 'bsc':
            return 'BSC'
        if network_name.lower() == 'opbnb':
            return 'opBNB'
        if network_name.lower() == 'xlayer':
            return 'XLayer'
        if network_name.lower() == 'hyperevm':
            return 'HyperEVM'
        # Общий случай - первая буква заглавная
        return network_name.capitalize()
