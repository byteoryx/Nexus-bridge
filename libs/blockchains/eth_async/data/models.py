import json
from dataclasses import dataclass
from typing import List

import requests
from web3 import Web3
from eth_typing import ChecksumAddress

from libs.blockchains.classes import AutoRepr


class TxStatus:
    Error: bool
    ErrDescription: str | dict

    def __init__(self, status: str, error: str | dict | None) -> None:
        if status == '0':
            self.Error: bool = False
        else:
            self.Error: bool = True

        if error:
            self.ErrDescription: str | dict = error
        else:
            self.ErrDescription: None = None

    def __bool__(self):
        return f'{self.Error}'

    def __repr__(self):
        return f'{self.Error}'


@dataclass
class DefaultABIs:
    Token = [
        {
            'constant': True,
            'inputs': [],
            'name': 'name',
            'outputs': [{'name': '', 'type': 'string'}],
            'payable': False,
            'stateMutability': 'view',
            'type': 'function'
        },
        {
            'constant': True,
            'inputs': [],
            'name': 'symbol',
            'outputs': [{'name': '', 'type': 'string'}],
            'payable': False,
            'stateMutability': 'view',
            'type': 'function'
        },
        {
            'constant': True,
            'inputs': [],
            'name': 'totalSupply',
            'outputs': [{'name': '', 'type': 'uint256'}],
            'payable': False,
            'stateMutability': 'view',
            'type': 'function'
        },
        {
            'constant': True,
            'inputs': [],
            'name': 'decimals',
            'outputs': [{'name': '', 'type': 'uint256'}],
            'payable': False,
            'stateMutability': 'view',
            'type': 'function'
        },
        {
            'constant': True,
            'inputs': [{'name': 'account', 'type': 'address'}],
            'name': 'balanceOf',
            'outputs': [{'name': '', 'type': 'uint256'}],
            'payable': False,
            'stateMutability': 'view',
            'type': 'function'
        },
        {
            'constant': True,
            'inputs': [{'name': 'owner', 'type': 'address'}, {'name': 'spender', 'type': 'address'}],
            'name': 'allowance',
            'outputs': [{'name': 'remaining', 'type': 'uint256'}],
            'payable': False,
            'stateMutability': 'view',
            'type': 'function'
        },
        {
            'constant': False,
            'inputs': [{'name': 'spender', 'type': 'address'}, {'name': 'value', 'type': 'uint256'}],
            'name': 'approve',
            'outputs': [],
            'payable': False,
            'stateMutability': 'nonpayable',
            'type': 'function'
        },
        {
            'constant': False,
            'inputs': [{'name': 'to', 'type': 'address'}, {'name': 'value', 'type': 'uint256'}],
            'name': 'transfer',
            'outputs': [], 'payable': False,
            'stateMutability': 'nonpayable',
            'type': 'function'
        }]

    Wrapped_Native_Token = [
        {
            "constant": False,
            "inputs": [],
            "name": "deposit",
            "outputs": [],
            "payable": True,
            "stateMutability": "payable",
            "type": "function"
        },
        {
            "constant": False,
            "inputs": [{"name": "wad", "type": "uint256"}],
            "name": "withdraw",
            "outputs": [],
            "payable": False,
            "stateMutability": "nonpayable",
            "type": "function"
        }
    ]


class Network:
    def __init__(
            self,
            name: str,
            rpc: str | None = None,
            decimals: int | None = None,
            chain_id: int | None = None,
            tx_type: int = 0,
            coin_symbol: str | None = None,
            explorer: str | None = None,
            wrapped_token_address: str | None = None,
    ) -> None:
        self.name: str = name
        self.rpc: str | None = rpc
        self.chain_id: int | None = chain_id
        self.tx_type: int = tx_type
        self.coin_symbol: str | None = coin_symbol
        self.explorer: str | None = explorer
        self.decimals = decimals
        self.wrapped_token_address = Web3.to_checksum_address(wrapped_token_address) if wrapped_token_address else None

        if not self.chain_id:
            try:
                self.chain_id = Web3(Web3.HTTPProvider(self.rpc)).eth.chain_id
            except Exception as err:
                raise

        if not self.coin_symbol or not self.decimals:
            try:
                network = None
                networks_info_response = requests.get('https://chainid.network/chains.json').json()
                for network_ in networks_info_response:
                    if network_['chainId'] == self.chain_id:
                        network = network_
                        break

                if not self.coin_symbol:
                    self.coin_symbol = network['nativeCurrency']['symbol']
                if not self.decimals:
                    self.decimals = int(network['nativeCurrency']['decimals'])

            except Exception as err:
                raise

        if self.coin_symbol:
            self.coin_symbol = self.coin_symbol.upper()

    def __repr__(self):
        return f"{self.name}, Chain ID {self.chain_id}, Coin Symbol {self.coin_symbol}"

    def __str__(self):
        return f"{self.name}"


class Networks:
    Ethereum = Network(
        name='Ethereum',
        chain_id=1,
        tx_type=2,
        coin_symbol='ETH',
        decimals=18,
        explorer='https://etherscan.io/',
        wrapped_token_address="0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2"
    )

    Arbitrum = Network(
        name='Arbitrum',
        chain_id=42161,
        tx_type=2,
        coin_symbol='ETH',
        decimals=18,
        explorer='https://arbiscan.io/',
        wrapped_token_address="0x82af49447d8a07e3bd95bd0d56f35241523fbab1"
    )

    Optimism = Network(
        name='Optimism',
        chain_id=10,
        tx_type=2,
        coin_symbol='ETH',
        decimals=18,
        explorer='https://optimistic.etherscan.io/',
        wrapped_token_address="0x4200000000000000000000000000000000000006"
    )

    Base = Network(
        name='Base',
        chain_id=8453,
        tx_type=2,
        coin_symbol='ETH',
        decimals=18,
        explorer='https://basescan.org/',
        wrapped_token_address="0x4200000000000000000000000000000000000006",
    )

    Linea = Network(
        name='Linea',
        chain_id=59144,
        tx_type=2,
        coin_symbol='ETH',
        decimals=18,
        explorer='https://lineascan.build/',
        wrapped_token_address="0xe5D7C2a44FfDDf6b295A15c148167daaAf5Cf34f",
    )

    Blast = Network(
        name='Blast',
        chain_id=81457,
        tx_type=2,
        coin_symbol='ETH',
        decimals=18,
        explorer='https://blastscan.io/',
        wrapped_token_address="0x4300000000000000000000000000000000000004",
    )

    Zksync = Network(
        name='Zksync',
        chain_id=324,
        tx_type=2,
        coin_symbol='ETH',
        decimals=18,
        explorer='https://explorer.zksync.io/',
        wrapped_token_address="0x5aea5775959fbc2557cc8789bc1bf90a239d9a91",
    )

    BSC = Network(
        name='BSC',
        chain_id=56,
        tx_type=0,
        coin_symbol='BNB',
        decimals=18,
        explorer='https://bscscan.com/',
        wrapped_token_address="0xBB4CdB9CBd36B01bD1cBaEBF2De08d9173bc095c"
    )

    Polygon = Network(
        name='Polygon',
        chain_id=137,
        tx_type=2,
        coin_symbol='POL',
        decimals=18,
        explorer='https://polygonscan.com/',
        wrapped_token_address="0x0d500B1d8E8eF31E21C99d1Db9A6444d3ADf1270"
    )

    Gnosis = Network(
        name='Gnosis',
        chain_id=100,
        tx_type=2,
        coin_symbol='XDAI',
        decimals=18,
        explorer='https://gnosisscan.io/',
        wrapped_token_address="0xe91d153e0b41518a2ce8dd3d7944fa863463a97d",
    )

    Scroll = Network(
        name='Scroll',
        chain_id=534352,
        tx_type=2,
        coin_symbol='ETH',
        decimals=18,
        explorer='https://scrollscan.com/',
        wrapped_token_address="0xfa6a407c4c49ea1d46569c1a4bcf71c3437be54c",
    )

    Celo = Network(
        name='Celo',
        chain_id=42220,
        tx_type=2,
        coin_symbol='CELO',
        decimals=18,
        explorer='https://celoscan.io/',
        wrapped_token_address="0xd221812de1bd094f35587ee8e174b07b6167d9af",
    )

    opBNB = Network(
        name='opBNB',
        chain_id=204,
        tx_type=2,
        coin_symbol='BNB',
        decimals=18,
        explorer='https://opbnbscan.com/',
        wrapped_token_address="0x4200000000000000000000000000000000000006",
    )

    ZetaChain = Network(
        name='ZetaChain',
        chain_id=7000,
        tx_type=2,
        coin_symbol='ZETA',
        decimals=18,
        explorer='https://explorer.zetachain.com/',
        wrapped_token_address=None,
    )

    Degen = Network(
        name='Degen',
        chain_id=666666666,
        tx_type=2,
        coin_symbol='DEGEN',
        decimals=18,
        explorer='https://explorer.degen.tips/',
        wrapped_token_address="0xf058eb3c946f0eaeca3e6662300cb01165c64ede",
    )

    XLayer = Network(
        name='XLayer',
        chain_id=196,
        tx_type=2,
        coin_symbol='OKB',
        decimals=18,
        explorer='https://www.okx.com/ru/web3/explorer/xlayer/',
        wrapped_token_address="0x5a77f1443d16ee5761d310e38b62f77f726bc71c",
    )

    Cyber = Network(
        name='Cyber',
        chain_id=7560,
        tx_type=2,
        coin_symbol='ETH',
        decimals=18,
        explorer='https://cyberscan.co/',
        wrapped_token_address="0xa3c6ef565ab5cf989b1fb1ada2e89473ec06299f",
    )

    Plume = Network(
        name='Plume',
        chain_id=98865,
        tx_type=2,
        coin_symbol='ETH',
        decimals=18,
        explorer='https://explorer.plumenetwork.xyz/',
        wrapped_token_address="0x0e672d885B16DB5a33b329d3F941fBe1C43797EB",
    )

    Ink = Network(
        name='Ink',
        chain_id=57073,
        tx_type=2,
        coin_symbol='ETH',
        decimals=18,
        explorer='https://explorer.inkonchain.com/',
        wrapped_token_address="0x4200000000000000000000000000000000000006",
    )

    Mode = Network(
        name='Mode',
        chain_id=34443,
        tx_type=2,
        coin_symbol='ETH',
        decimals=18,
        explorer='https://modescan.io/',
        wrapped_token_address="0x4200000000000000000000000000000000000006",
    )

    Unichain = Network(
        name='Unichain',
        chain_id=130,
        tx_type=2,
        coin_symbol='ETH',
        decimals=18,
        explorer='https://unichain.blockscout.com/',
        wrapped_token_address="0x4200000000000000000000000000000000000006",
    )

    Lisk = Network(
        name='Lisk',
        chain_id=1135,
        tx_type=2,
        coin_symbol='ETH',
        decimals=18,
        explorer='https://blockscout.lisk.com/',
        wrapped_token_address="0x4200000000000000000000000000000000000006",
    )

    Soneium = Network(
        name='Soneium',
        chain_id=1868,
        tx_type=2,
        coin_symbol='ETH',
        decimals=18,
        explorer='https://soneium.blockscout.com/',
        wrapped_token_address="0x4200000000000000000000000000000000000006",
    )

    Avalanche = Network(
        name='Avalanche',
        chain_id=43114,
        tx_type=2,
        coin_symbol='AVAX',
        decimals=18,
        explorer='https://www.snowtrace.io/',
        wrapped_token_address="0xB31f66AA3C1e785363F0875A1B74E27b85FD66c7",
    )

    PolygonZKEVM = Network(
        name='PolygonZKEVM',
        chain_id=1101,
        tx_type=2,
        coin_symbol='ETH',
        decimals=18,
        explorer='https://zkevm.polygonscan.com/',
        wrapped_token_address="0x4F9A0e7FD2Bf6067db6994CF12E4495Df938E6e9",
    )

    Fantom = Network(
        name='Fantom',
        chain_id=250,
        tx_type=2,
        coin_symbol='FTM',
        decimals=18,
        explorer='https://explorer.fantom.network/',
        wrapped_token_address="0x21be370d5312f44cb42ce377bc9b8a0cef1a4c83",
    )

    Moonriver = Network(
        name='Moonriver',
        chain_id=1285,
        tx_type=2,
        coin_symbol='MOVR',
        decimals=18,
        explorer='https://moonriver.moonscan.io/',
        wrapped_token_address="0x98878B06940aE243284CA214f92Bb71a2b032B8A",
    )

    Moonbeam = Network(
        name='Moonbeam',
        chain_id=1284,
        tx_type=2,
        coin_symbol='GLMR',
        decimals=18,
        explorer='https://moonscan.io/',
        wrapped_token_address="0xAcc15dC74880C9944775448304B263D191c6077F",
    )

    Fuse = Network(
        name='Fuse',
        chain_id=122,
        tx_type=2,
        coin_symbol='FUSE',
        decimals=18,
        explorer='https://explorer.fuse.io/',
        wrapped_token_address="0x0BE9e53fd7EDaC9F859882AfdDa116645287C629",
    )

    Boba = Network(
        name='Boba',
        chain_id=288,
        tx_type=2,
        coin_symbol='ETH',
        decimals=18,
        explorer='https://bobascan.com/',
        wrapped_token_address="0xDeadDeAddeAddEAddeadDEaDDEAdDeaDDeAD0000",
    )

    Metis = Network(
        name='Metis',
        chain_id=1088,
        tx_type=2,
        coin_symbol='METIS',
        decimals=18,
        explorer='https://explorer.metis.io/',
        wrapped_token_address="0x75cb093E4D61d2A2e65D8e0BBb01DE8d89b53481",
    )

    Aurora = Network(
        name='Aurora',
        chain_id=1313161554,
        tx_type=2,
        coin_symbol='ETH',
        decimals=18,
        explorer='https://explorer.mainnet.aurora.dev/',
        wrapped_token_address="0xC9BdeEd33CD01541e1eeD10f90519d2C06Fe3feB",
    )

    Sei = Network(
        name='Sei',
        chain_id=1329,
        tx_type=2,
        coin_symbol='SEI',
        decimals=18,
        explorer='https://www.seiscan.app/',
        wrapped_token_address="",
    )

    ImmutableZKEVM = Network(
        name='ImmutableZKEVM',
        chain_id=13371,
        tx_type=2,
        coin_symbol='IMX',
        decimals=18,
        explorer='https://explorer.immutable.com/',
        wrapped_token_address="0x3A0C2Ba54D6CBd3121F01b96dFd20e99D1696C9D",
    )

    Sonic = Network(
        name='Sonic',
        chain_id=146,
        tx_type=2,
        coin_symbol='S',
        decimals=18,
        explorer='https://sonicscan.org/',
        wrapped_token_address="0x039e2fB66102314Ce7b64Ce5Ce3E5183bc94aD38",
    )

    Gravity = Network(
        name='Gravity',
        chain_id=1625,
        tx_type=2,
        coin_symbol='G',
        decimals=18,
        explorer='https://explorer.gravity.xyz/',
        wrapped_token_address="0xBB859E225ac8Fb6BE1C7e38D87b767e95Fef0EbD",
    )

    Taiko = Network(
        name='Taiko',
        chain_id=167000,
        tx_type=2,
        coin_symbol='ETH',
        decimals=18,
        explorer='https://taikoscan.io/',
        wrapped_token_address="0xA51894664A773981C6C112C43ce576f315d5b1B6",
    )

    Swellchain = Network(
        name='Swellchain',
        chain_id=1923,
        tx_type=2,
        coin_symbol='ETH',
        decimals=18,
        explorer='https://swellchainscan.io/',
        wrapped_token_address="0x4200000000000000000000000000000000000006",
    )

    Corn = Network(
        name='Corn',
        chain_id=21000000,
        tx_type=2,
        coin_symbol='BTCN',
        decimals=18,
        explorer='https://cornscan.io/',
        wrapped_token_address="0xda5dDd7270381A7C2717aD10D1c0ecB19e3CDFb2",
    )

    Cronos = Network(
        name='Cronos',
        chain_id=25,
        tx_type=2,
        coin_symbol='CRO',
        decimals=18,
        explorer='https://cronoscan.com/',
        wrapped_token_address="0x5C7F8A570d578ED84E63fdFA7b1eE72dEae1AE23",
    )

    Abstract = Network(
        name='Abstract',
        chain_id=2741,
        tx_type=2,
        coin_symbol='ETH',
        decimals=18,
        explorer='https://abscan.org/',
        wrapped_token_address="0x3439153EB7AF838Ad19d56E1571FBD09333C2809",
    )

    Rootstock = Network(
        name='Rootstock',
        chain_id=30,
        tx_type=2,
        coin_symbol='RBTC',
        decimals=18,
        explorer='https://explorer.rootstock.io/',
        wrapped_token_address="0x1945d8AEDC005c900c796e31CcE040363A6658d2",
    )

    Apechain = Network(
        name='Apechain',
        chain_id=33139,
        tx_type=2,
        coin_symbol='APE',
        decimals=18,
        explorer='https://apescan.io/',
        wrapped_token_address="0x48b62137EdfA95a428D35C09E44256a739F6B557",
    )

    WorldChain = Network(
        name='WorldChain',
        chain_id=480,
        tx_type=2,
        coin_symbol='ETH',
        decimals=18,
        explorer='https://worldscan.org/',
        wrapped_token_address="0x4200000000000000000000000000000000000006",
    )

    XDC = Network(
        name='XDC',
        chain_id=50,
        tx_type=2,
        coin_symbol='XDC',
        decimals=18,
        explorer='https://xdcscan.com/',
        wrapped_token_address="0x951857744785E80e2De051c32EE7b25f9c458C42",
    )

    Mantle = Network(
        name='Mantle',
        chain_id=5000,
        tx_type=2,
        coin_symbol='MNT',
        decimals=18,
        explorer='https://mantlescan.xyz/',
        wrapped_token_address="0x78c1b0C915c4FAA5FffA6CAbf0219DA63d7f4cb8",
    )

    Superposition = Network(
        name='Superposition',
        chain_id=55244,
        tx_type=2,
        coin_symbol='ETH',
        decimals=18,
        explorer='https://xdcscan.com/',
        wrapped_token_address="0x1fB719f10b56d7a85DCD32f27f897375fB21cfdd",
    )

    BOB = Network(
        name='BOB',
        chain_id=60808,
        tx_type=2,
        coin_symbol='ETH',
        decimals=18,
        explorer='https://explorer.gobob.xyz/',
        wrapped_token_address="0x4200000000000000000000000000000000000006",
    )

    Lens = Network(
        name='Lens',
        chain_id=232,
        tx_type=2,
        coin_symbol='GHO',
        decimals=18,
        explorer='https://explorer.lens.xyz/',
        wrapped_token_address="0x6bDc36E20D267Ff0dd6097799f82e78907105e2F",
    )

    Berachain = Network(
        name='Berachain',
        chain_id=80094,
        tx_type=2,
        coin_symbol='BERA',
        decimals=18,
        explorer='https://berascan.com/',
        wrapped_token_address="0x6969696969696969696969696969696969696969",
    )

    Kaia = Network(
        name='Kaia',
        chain_id=8217,
        tx_type=2,
        coin_symbol='KAIA',
        decimals=18,
        explorer='https://kaiascan.io/',
        wrapped_token_address="0x19aac5f612f524b754ca7e7c41cbfa2e981a4432",
    )

    HyperEVM = Network(
        name='HyperEVM',
        chain_id=999,
        tx_type=2,
        coin_symbol='HYPE',
        decimals=18,
        explorer='https://hypurrscan.io/',
        wrapped_token_address="0x5555555555555555555555555555555555555555",
    )


    @classmethod
    def __iter__(cls):
        """Возвращает итератор по всем доступным сетям"""
        for attr_name in dir(cls):
            if not attr_name.startswith('_'):  # пропускаем приватные атрибуты
                attr = getattr(cls, attr_name)
                if isinstance(attr, Network):  # проверяем, что атрибут является сетью
                    yield attr

    @classmethod
    def list(cls) -> list[Network]:
        """Возвращает список всех доступных сетей"""
        return list(cls.__iter__())

    @classmethod
    def names(cls) -> List[str]:
        """Возвращает список имен всех доступных сетей"""
        return [network.name for network in cls.list()]

    @classmethod
    def get_network_by_name(cls, network_name: str) -> Network | None:
        network_name = network_name.replace('_', ' ') # todo: добавить регулярные выражения для универсальности
        for network in cls.list():
            if network.name.lower() == network_name.lower():
                return network


class RawContract(AutoRepr):
    """
    An instance of a raw contract.

    Attributes:
        title str: a contract title.
        address (ChecksumAddress): a contract evm_address.
        abi list[dict[str, Any]] | str: an ABI of the contract.

    """
    title: str
    address: ChecksumAddress
    abi: list[dict[str, ...]]
    decimals: int
    is_native_token: bool

    def __init__(self, address: str, abi: list[dict[str, ...]] | str | None = None,
                 title: str = '', decimals: int = 18, is_native_token: bool = False) -> None:
        """
        Initialize the class.

        Args:
            title (str): a contract title.
            address (str): a contract evm_address.
            abi (Union[List[Dict[str, Any]], str]): an ABI of the contract.
            decimals (int): token decimals, by default 18
        """
        self.title = title
        self.address = Web3.to_checksum_address(address)
        self.abi = json.loads(abi) if isinstance(abi, str) else abi
        self.decimals = decimals
        self.is_native_token = is_native_token

    def __eq__(self, other) -> bool:
        if self.address == other.address and self.abi == other.abi:
            return True
        return False

    def __str__(self):
        return self.title

class TransferAddress(AutoRepr):
    """
    EVM-address to transfer funds to
    Attributes:
        title str: an address title.
        address (ChecksumAddress): a contract address.
    """
    title: str
    address: ChecksumAddress

    def __init__(self, address: str, title: str = '') -> None:
        self.title = title
        self.address = Web3.to_checksum_address(address)

    def __eq__(self, other) -> bool:
        if self.address == other.address:
            return True
        return False

    def __str__(self):
        return self.title

@dataclass
class CommonValues:
    """
    An instance with common values used in transactions.
    """
    ZeroAddress = '0x0000000000000000000000000000000000000000'
    Null: str = '0x0000000000000000000000000000000000000000000000000000000000000000'
    InfinityStr: str = '0xffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff'
    InfinityInt: int = int('0xffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff', 16)


class TxArgs(AutoRepr):
    """
    An instance for named transaction arguments.
    """

    def __init__(self, **kwargs) -> None:
        """
        Initialize the class.

        Args:
            **kwargs: named arguments of a contract transaction.

        """
        self.__dict__.update(kwargs)

    def list(self) -> list[...]:
        """
        Get list of transaction arguments.

        Returns:
            List[Any]: list of transaction arguments.

        """
        return list(self.__dict__.values())

    def tuple(self) -> tuple[str, ...]:
        """
        Get tuple of transaction arguments.

        Returns:
            Tuple[Any]: tuple of transaction arguments.

        """
        return tuple(self.__dict__.values())
