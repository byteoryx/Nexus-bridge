from dataclasses import dataclass, field, fields
from typing import Iterator

from libs.blockchains.classes import Singleton, AutoRepr


@dataclass
class RPCSettings:
    url: str
    max_retries: int
    retry_count: int = 0

    def __post_init__(self):
        self.url = self.url.strip()

    def __str__(self):
        return f"url {self.url}, max retries: {self.max_retries}, current retry count: {self.retry_count}"


@dataclass
class NetworkConfig:
    """Конфигурация конкретной сети"""
    name: str
    rpcs: list[RPCSettings] = field(default_factory=list)
    current_rpc_index: int = -1

    @property
    def url(self) -> str:
        """Получить текущий URL"""
        if not self.rpcs:
            raise ValueError("No RPCs configured for this network")
        return self.rpcs[self.current_rpc_index].url

    @property
    def retry_count(self) -> int:
        """Получить текущий retry_count"""
        if not self.rpcs:
            raise ValueError("No RPCs configured for this network")
        return self.rpcs[self.current_rpc_index].retry_count

    @property
    def max_retries(self) -> int:
        """Получить текущий retry_count"""
        if not self.rpcs:
            raise ValueError("No RPCs configured for this network")
        return self.rpcs[self.current_rpc_index].max_retries

    def add_rpc(self, rpc_settings: RPCSettings) -> None:
        """Добавить новый RPC"""
        self.rpcs.append(rpc_settings)

    def __iter__(self) -> Iterator[RPCSettings]:
        return iter(self.rpcs)

    def __len__(self) -> int:
        return len(self.rpcs)


@dataclass
class NetworksModule:
    """Модуль настроек сетей"""
    Ethereum: NetworkConfig = field(default_factory=lambda: NetworkConfig(name='Ethereum'))
    Arbitrum: NetworkConfig = field(default_factory=lambda: NetworkConfig(name='Arbitrum'))
    Optimism: NetworkConfig = field(default_factory=lambda: NetworkConfig(name='Optimism'))
    Base: NetworkConfig = field(default_factory=lambda: NetworkConfig(name='Base'))


    def add_rpc_to_network(self, network: str, rpc_settings: RPCSettings) -> None:
        """Добавить RPC к сети"""
        if hasattr(self, network):
            network_config = getattr(self, network)
            network_config.add_rpc(rpc_settings)
        else:
            print(f"Error: Unknown network: {network}")
            raise ValueError(f"Unknown network: {network}")

    def list(self):
        return [getattr(self,  field_.name) for field_ in fields(self)]


@dataclass
class TelegramSettings:
    """Настройки telegram"""
    send_notifications: bool = False
    bot_key: str | None = None
    chat_id: str | None = None

    def __post_init__(self):
        if self.bot_key:
            self.bot_key = self.bot_key.strip()
        if self.chat_id:
            self.chat_id = self.chat_id.strip()

        # Проверяем, что если включены уведомления, то указаны bot_key и chat_id
        if self.send_notifications:
            if not self.bot_key or not self.chat_id:
                raise ValueError("Bot key and chat ID are required when notifications are enabled")


@dataclass
class LoggingSettings:
    """Настройки логирования"""
    rotation: str = "10 MB"
    retention: str = "1 week"
    debug_logging: bool = True
    log_to_file: bool = True
    show_full_address: bool = True

    def __post_init__(self):
        self.rotation = self.rotation.strip()
        self.retention = self.retention.strip()


@dataclass
class DelaysSettings:
    """Настройки delays"""
    accounts_delay: list[int] = field(default_factory=list)
    action_delay: list[int] = field(default_factory=list)
    flow_delay: list[int] = field(default_factory=list)
    start_time: str = field(default_factory=str)
    number_or_replays: int = field(default_factory=int)

    def __post_init__(self):
        if len(self.accounts_delay) > 2 or len(self.action_delay) > 2 or len(self.flow_delay) > 2:
            raise ValueError("Wrong length for delays")

        self.start_hour = int(self.start_time.split(":")[0])
        self.start_minute = int(self.start_time.split(":")[1])
        if 0 > self.start_hour > 23 or 0 > self.start_minute > 59:
            raise ValueError("Wrong start time parameters")


@dataclass
class FlowSettings:
    wallets_per_flow: int = 5


@dataclass
class GeneralSettings:
    number_of_retries: int = 3
    retry_delay: int = 5
    timeout: int = 30
    SHUFFLE_ACCOUNTS: bool = False
    SHUFFLE_ACTIONS: bool = False


@dataclass
class GasSettings:
    maximum_gwei_dict: dict
    gas_control: bool = True
    gas_retry_delay: float = 30
    gas_price_multiplier: float = 1.2
    gas_limit_multiplier: float = 1.3


@dataclass
class OKXSettings:
    api_key: str
    api_secret_key: str
    passphrase: str

@dataclass
class BitgetSettings:
    api_key: str
    api_secret_key: str
    passphrase: str

@dataclass
class MexcSettings:
    api_key: str
    api_secret_key: str
    passphrase: str


@dataclass
class CEXSettings:
    okx: OKXSettings
    bitget: BitgetSettings
    mexc: MexcSettings


@dataclass
class Settings(Singleton, AutoRepr):
    """Основной класс настроек"""
    # Модули настроек
    networks: NetworksModule
    logging: LoggingSettings
    telegram: TelegramSettings
    general: GeneralSettings
    flow: FlowSettings
    delays: DelaysSettings
    gas: GasSettings
    cex: CEXSettings

    @classmethod
    def load_from_toml(cls, toml_data) -> 'Settings':
        logging = LoggingSettings(**toml_data.get('logger', {}))
        telegram = TelegramSettings(**toml_data.get('telegram', {}))
        general = GeneralSettings(**toml_data.get('general', {}))
        flow = FlowSettings(**toml_data.get('flow', {}))
        delays = DelaysSettings(**toml_data.get('delays', {}))
        gas = GasSettings(**toml_data.get('gas', {}))

        cex_data = toml_data.get('CEX', {})
        okx = OKXSettings(**cex_data.get('okx', {}))
        bitget = BitgetSettings(**cex_data.get('bitget', {}))
        mexc = MexcSettings(**cex_data.get('mexc', {}))

        cex = CEXSettings(okx, bitget, mexc)

        networks = NetworksModule()

        settings_ = cls(
            networks=networks,
            logging=logging,
            telegram=telegram,
            general=general,
            flow=flow,
            delays=delays,
            gas=gas,
            cex=cex,
        )

        # Загружаем сети
        if 'networks_rpc' in toml_data:
            for network_name, rpc_list in toml_data['networks_rpc'].items():
                for rpc_data in rpc_list:
                    rpc_settings = RPCSettings(**rpc_data)
                    networks.add_rpc_to_network(network_name, rpc_settings)

        return settings_
