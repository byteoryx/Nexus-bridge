from __future__ import annotations

from typing import TYPE_CHECKING
import random

from web3 import AsyncWeb3
from web3.eth import AsyncEth
from eth_account.signers.local import LocalAccount
from aiohttp import ClientSession
from web3.middleware import ExtraDataToPOAMiddleware

from core.logger import get_logger
from core.init_settings import settings
from .data.models import Networks, Network
from .wallet import Wallet
from .contracts import Contracts
from .transactions import Transactions
from ..omnichain_functions import get_next_rpc_from_network_config

if TYPE_CHECKING:
    from core.settings_models import NetworkConfig


class NetworkClient:
    """
    Client for a specific EVM network
    Handles network-specific Web3 instance and operations
    """
    network_config: NetworkConfig
    network: Network
    w3_account: LocalAccount | None
    w3: AsyncWeb3
    wallet: Wallet
    contracts: Contracts
    transactions: Transactions

    def __init__(
            self,
            network_config: NetworkConfig,
            headers: dict,
            proxy: str | None = None,
            w3_account: LocalAccount | None = None,
            log_context: dict | None = None,
            debug = settings.logging.debug_logging,
    ) -> None:

        self.network = Networks.get_network_by_name(network_config.name)
        self.network_config = network_config
        self.w3_account = w3_account
        self.proxy = proxy
        self.headers = headers
        
        self.wallet = Wallet(self, log_context)
        self.contracts = Contracts(self)
        self.transactions = Transactions(self, log_context)

        if log_context:
            self.logger = get_logger(class_name=f"EthClient: {self.network.name}", **log_context)
        else:
            self.logger = get_logger(class_name=f"EthClient: {self.network.name}")

        self.rpc_config = get_next_rpc_from_network_config(self.network_config, self.logger)

        self.total_max_retries = 0
        for rpc in self.network_config.rpcs:
            self.total_max_retries += rpc.max_retries
        self._setup_w3(proxy=self.proxy, rpc=self.rpc_config.url)
        
        self.__debug = debug


    def _setup_w3(self, proxy: str, rpc: str):
        self.w3 = AsyncWeb3(
            provider=AsyncWeb3.AsyncHTTPProvider(
                endpoint_uri=rpc,
                request_kwargs={'proxy': proxy, 'headers': self.headers, 'timeout': settings.general.timeout}
            ),
            modules={'eth': (AsyncEth,)},
            middleware=[]
        )
        if any(name in self.network.name for name in ('Polygon', 'BSC')):
            self.w3.middleware_onion.inject(ExtraDataToPOAMiddleware, layer=0)


    async def change_rpc(self):
        self.logger.warning(f"Changing {self.network_config.name} RPC {self.rpc_config}")
        self.rpc_config = get_next_rpc_from_network_config(self.network_config, self.logger, change=True)
        await self.recreate_provider(new_rpc=self.rpc_config.url)
        self.logger.success(f"Changed {self.network_config.name} RPC to {self.rpc_config}")
    
    async def recreate_provider(self, new_rpc: str = None, new_proxy: str = None):
        if self.w3 and self.w3.provider:
            await self.w3.provider.disconnect()
        
        self._setup_w3(
            proxy=new_proxy if new_proxy is not None else self.proxy,
            rpc=new_rpc if new_rpc is not None else self.rpc_config.url
        )

    async def old_increase_rpc_retry_count(self):
        self.network_config.rpcs[self.network_config.current_rpc_index].retry_count += 1
        if self.__debug:
            self.logger.debug(f"Current RPC index {self.network_config.current_rpc_index}")
            self.logger.debug(f"Current RPC retry count: {self.network_config.rpcs[self.network_config.current_rpc_index].retry_count}")
            self.logger.debug(f"Current MAX retries: {self.network_config.rpcs[self.network_config.current_rpc_index].max_retries}")

        if (self.network_config.rpcs[self.network_config.current_rpc_index].retry_count >=
            self.network_config.rpcs[self.network_config.current_rpc_index].max_retries):
            await self.change_rpc()

    async def increase_rpc_retry_count(self):
        if self.__debug:
            self.logger.debug(f"Current RPC index {self.network_config.current_rpc_index}")
            self.logger.debug(f"Current RPC retry count: {self.rpc_config.retry_count}")
            self.logger.debug(f"Current MAX retries: {self.rpc_config.max_retries}")
        self.rpc_config.retry_count += 1
        if self.rpc_config.retry_count >= self.rpc_config.max_retries:
            await self.change_rpc()

    async def change_proxy(self, proxy: str):
        """Change proxy for this network's Web3 instance"""
        self.proxy = proxy
        if self.proxy and 'http' not in self.proxy:
            self.proxy = f'http://{self.proxy}'
        await self.recreate_provider(new_proxy=self.proxy)


class EthClient:
    """
    Multi-network client for EVM networks
    Can be used with context manager
    Example:
        async with EthClient(evm_private_key) as client:
            balance = await client.ethereum.wallet.balance()
    """
    w3_account: LocalAccount | None
    ethereum: NetworkClient
    arbitrum: NetworkClient
    optimism: NetworkClient
    polygon: NetworkClient
    avalanche: NetworkClient
    bsc: NetworkClient
    base: NetworkClient
    zksync: NetworkClient
    celo: NetworkClient
    opbnb: NetworkClient
    scroll: NetworkClient
    degen: NetworkClient
    zetachain: NetworkClient
    cyber: NetworkClient
    blast: NetworkClient
    linea: NetworkClient
    ink: NetworkClient
    mode: NetworkClient
    lisk: NetworkClient
    unichain: NetworkClient
    soneium: NetworkClient

    polygonzkevm: NetworkClient
    fantom: NetworkClient
    moonriver: NetworkClient
    moonbeam: NetworkClient
    fuse: NetworkClient
    boba: NetworkClient
    metis: NetworkClient
    aurora: NetworkClient
    sei: NetworkClient
    immutablezkevm: NetworkClient
    sonic: NetworkClient
    gravity: NetworkClient
    taiko: NetworkClient
    swellchain: NetworkClient
    corn: NetworkClient
    cronos: NetworkClient
    abstract: NetworkClient
    rootstock: NetworkClient
    apechain: NetworkClient
    worldchain: NetworkClient
    xdc: NetworkClient
    mantle: NetworkClient
    superposition: NetworkClient
    bob: NetworkClient
    lens: NetworkClient
    berachain: NetworkClient
    kaia: NetworkClient
    hyperevm: NetworkClient

    def __init__(
            self,
            private_key: str | None = None,
            networks: list[NetworkConfig] | None = None,
            proxy: str | None = None,
            log_context: dict | None = None
    ) -> None:

        # if networks is None:
        #     only_one_client = True
        #     networks = [settings.networks.Ethereum]  # Default to Ethereum if no networks specified

        self.headers = {'accept': '*/*', 'accept-language': 'en-US,en;q=0.9', 'content-type': 'application/json'}

        self.proxy = proxy
        if self.proxy and 'http' not in self.proxy:
            self.proxy = f'http://{self.proxy}'

        # Create account if private key is not provided
        if private_key:
            self.w3_account = AsyncWeb3().eth.account.from_key(private_key=private_key)
        elif private_key is None:
            self.w3_account = AsyncWeb3().eth.account.create(extra_entropy=str(random.randint(1, 999_999_999)))

        self.log_context = log_context
        if log_context:
            self.logger = get_logger(class_name=f"EthClient", **log_context)
        else:
            self.logger = get_logger(class_name=f"EthClient")

        if networks:
            self._setup_networks_clients(networks)

        self._sessions = {}  # Храним сессии отдельно

        self.ens = None

    def _setup_networks_clients(self, networks: list[NetworkConfig]) -> None:
        """Initialize network clients and set them as attributes for IDE autocompletion"""
        self._network_clients = {}
        for network_config in networks:
            network_name = network_config.name.lower()
            if any(n in network_name for n in ("aptos", "sui", "solana")):
                continue

            network_client = NetworkClient(
                network_config=network_config,
                headers=self.headers,
                proxy=self.proxy,
                w3_account=self.w3_account,
                log_context=self.log_context,
            )
            self._network_clients[network_name] = network_client
            # Set as attribute for IDE autocompletion
            setattr(self, network_name, network_client)

    def __getattr__(self, name: str) -> NetworkClient:
        """Allow accessing networks as attributes (e.g., eth_client.ethereum)"""
        if name.lower() in self._network_clients:
            return self._network_clients[name.lower()]
        raise AttributeError(f"Network '{name}' not found")

    async def __aenter__(self):
        for network_name, network_client in self._network_clients.items():
            custom_session = ClientSession()
            self._sessions[network_name] = custom_session  # Сохраняем сессию
            await network_client.w3.provider.cache_async_session(custom_session)
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        try:
            for network_client in self._network_clients.values():
                await network_client.w3.provider.disconnect()
            
            for session in self._sessions.values():
                if not session.closed:
                    await session.close()
        except Exception as e:
            self.logger.error(f"Error during closing sessions: {e}")

    async def close(self):
        """Close all connections"""
        await self.__aexit__(None, None, None)

    async def change_proxy(self, proxy: str):
        """
        Change proxy for all network clients
        :param proxy: New proxy evm_address
        """
        self.proxy = proxy
        if self.proxy and 'http' not in self.proxy:
            self.proxy = f'http://{self.proxy}'
        
        # Update proxy for all network clients
        for network_client in self._network_clients.values():
            await network_client.change_proxy(self.proxy)

    async def get_ens(self):
        self.ens = await self.ethereum.w3.ens.name(self.w3_account.address)
        return self.ens
