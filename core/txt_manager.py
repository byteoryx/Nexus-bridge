from dataclasses import dataclass

from libs.blockchains.eth_async.ethclient import EthClient
from core.logger import get_logger
from libs.requests.session import get_ua_parameters


@dataclass
class AccountData:
    """Класс для хранения данных кошелька"""
    name: str
    evm_private_key: str
    proxy: str
    evm_address: str | None = None

    user_agent: str | None = None
    os_user_agent: str | None = None
    chrome_version: str | None = None

    def __post_init__(self):
        # Убираем пробелы и переносы строк
        self.name = self.name.strip()
        if not self.evm_private_key:
            eth_client = EthClient()
            self.evm_private_key = eth_client.w3_account.key.hex()

        self.evm_private_key = self.evm_private_key.strip()
        if self.proxy:
            self.proxy = self.proxy.strip()

        # Проверяем private key
        if not self.evm_private_key.startswith('0x'):
            self.evm_private_key = f'0x{self.evm_private_key}'

        ua, os_ua, chrome_version = get_ua_parameters()
        self.user_agent = ua
        self.os_user_agent = os_ua
        self.chrome_version = chrome_version

        if self.evm_private_key:
            eth_client = EthClient(private_key=self.evm_private_key)
            self.evm_address = eth_client.w3_account.address

class TxtManager:
    def __init__(self):
        self.spare_proxies: set[str] = set()  # Множество запасных прокси
        self.logger = get_logger(class_name=self.__class__.__name__)

    def load_accounts(self, private_key_path: str = "private_keys.txt", proxies_path: str = "proxies.txt"):
        pks = []
        proxies = []
        proxies_set = set()
        used_proxies = set()

        accounts = []

        with open(private_key_path, "r") as f:
            lines = f.readlines()
            for line in lines:
                print(line)
                pks.append(line.strip())

        with open(proxies_path, "r") as f:
            lines = f.readlines()
            for line in lines:
                proxies.append(line.strip())
                proxies_set.add(line.strip())

        for i, pk in enumerate(pks):
            account = AccountData(
                name="acc" + str(i+1),
                evm_private_key=pk,
                proxy=proxies[i] if proxies else None,
            )

            accounts.append(account)

            used_proxies.add(proxies[i]) if proxies else None

        # Находим неиспользованные прокси
        self.spare_proxies = proxies_set - used_proxies

        self.logger.info(f"Successfully loaded {len(accounts)} accounts from {private_key_path} and {proxies_path}")
        self.logger.info(f"Found {len(self.spare_proxies)} spare proxies")

        return accounts, list(self.spare_proxies)
