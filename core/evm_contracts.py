from libs.blockchains.classes import Singleton
from libs.blockchains.eth_async.data.models import RawContract, DefaultABIs, TransferAddress
from utils.utils import join_path, read_json
from core import config


class EVMContracts(Singleton):
    jumper_diamond_proxy_abi = read_json(path=join_path((config.ABIS_DIR, 'jumper_diamond_proxy.json')))
    open_usdt_abi = read_json(path=join_path((config.ABIS_DIR, 'open_usdt.json')))

    USDC_Base = RawContract(
        title='USDC Base',
        address='0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913',
        abi=DefaultABIs.Token,
        decimals=6
    )

    USDC_Arbitrum = RawContract(
        title='USDC Arbitrum',
        address='0xaf88d065e77c8cc2239327c5edb3a432268e5831',
        abi=DefaultABIs.Token,
        decimals=6
    )

    USDC_Optimism = RawContract(
        title='USDC Optimism',
        address='0x0b2c639c533813f4aa9d7837caf62653d097ff85',
        abi=DefaultABIs.Token,
        decimals=6
    )

    GasZip_Direct = TransferAddress(
        title='GasZip Direct',
        address='0x391E7C679d29bD940d63be94AD22A25d25b5A604',
    )

    # Both Arb and Op
    Sepolia_Ether = RawContract(
        title='seth',
        address='0xe71bdfe1df69284f00ee185cf0d95d0c7680c0d4',
        abi=DefaultABIs.Token,
        decimals=18
    )

    BaseOpenUSDT = RawContract(
        title='BaseOpenUSDT',
        address='0x26af973A5b256F9B9bc0B1A3c566de1566568a87',
        abi=open_usdt_abi,
    )

    BaseOpenUSDTtoOptimism = RawContract(
        title='BaseOpenUSDTtoOptimism',
        address='0x955132016f9b6376b1392aa7bff50538d21ababc',
        abi=open_usdt_abi,
    )

    OptimismOpenUSDT = RawContract(
        title='OptimismOpenUSDT',
        address='0x741B077c69FA219CEdb11364706a3880A792423e',
        abi=open_usdt_abi,
    )

    ArbitrumOpenUSDT = RawContract(
        title='ArbitrumOpenUSDT',
        address='0x2cb0e5abe11346679749063d3fbfc1f390e6e70a',
        abi=open_usdt_abi,
    )

    Optimism_USDCe = RawContract(
        title='Optimism USDCe',
        address='0x7F5c764cBc14f9669B88837ca1490cCa17c31607',
        abi=DefaultABIs.Token,
        decimals=6
    )

    Unichain_USDC = RawContract(
        title='Unichain USDC',
        address='0x078D782b760474a361dDA0AF3839290b0EF57AD6',
        abi=DefaultABIs.Token,
        decimals=6
    )

    Ink_USDCe = RawContract(
        title='Ink USDCe',
        address='0xF1815bd50389c46847f0Bda824eC8da914045D14',
        abi=DefaultABIs.Token,
        decimals=6
    )

    Soneium_USDCe = RawContract(
        title='Soneium USDCe',
        address='0xbA9986D2381edf1DA03B0B9c1f8b00dc4AacC369',
        abi=DefaultABIs.Token,
        decimals=6
    )

    Lisk_USDCe = RawContract(
        title='Lisk USDCe',
        address='0xF242275d3a6527d877f2c927a82D9b057609cc71',
        abi=DefaultABIs.Token,
        decimals=6
    )

    Mode_USDC = RawContract(
        title='Mode USDC',
        address='0xd988097fb8612cc24eeC14542bC03424c656005f',
        abi=DefaultABIs.Token,
        decimals=6
    )

    Base_USDC = RawContract(
        title='Base USDC',
        address='0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913',
        abi=DefaultABIs.Token,
        decimals=6
    )
