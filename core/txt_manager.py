from dataclasses import dataclass

from core.init_settings import settings
from libs.blockchains.eth_async.ethclient import EthClient
from core.logger import get_logger
from libs.requests.session import get_ua_parameters
from utils.utils import randfloat


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

    max_hyperlane_fees: float | None = None
    cex_deposit_address: str | None = None

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

        if self.cex_deposit_address:
            self.cex_deposit_address = self.cex_deposit_address.strip()

class TxtManager:
    def __init__(self):
        self.spare_proxies: set[str] = set()  # Множество запасных прокси
        self.logger = get_logger(class_name=self.__class__.__name__)

    def load_accounts(self, private_key_path: str = "private_keys.txt", proxies_path: str = "proxies.txt",
                      cex_deposit_addresses_path: str = "deposit_addresses.txt"):
        pks = []
        proxies = []
        proxies_set = set()
        used_proxies = set()

        accounts = []
        deposit_addresses = []

        with open(private_key_path, "r") as f:
            lines = f.readlines()
            for line in lines:
                pks.append(line.strip())

        with open(proxies_path, "r") as f:
            lines = f.readlines()
            for line in lines:
                proxies.append(line.strip())
                proxies_set.add(line.strip())

        with open(cex_deposit_addresses_path, "r") as f:
            lines = f.readlines()
            for line in lines:
                deposit_addresses.append(line.strip())

        if len(deposit_addresses) != len(pks):
            self.logger.warning(f"Deposit addresses {len(deposit_addresses)} and private keys {len(pks)}"
                                f" are not the same length")
            to_continue = input("Do you want to continue (y/n)?\n")
            if to_continue == "n" or to_continue == "N" or to_continue == "no":
                exit(1)

        for i, pk in enumerate(pks):
            try:
                deposit_address = deposit_addresses[i]
            except IndexError:
                self.logger.warning(f"Deposit address for account {i} not found")
                deposit_address = None

            account = AccountData(
                name="acc" + str(i+1),
                evm_private_key=pk,
                proxy=proxies[i] if proxies else None,
                max_hyperlane_fees=randfloat(*settings.general.max_hyperlane_fees, step=0.000001),
                cex_deposit_address=deposit_address
            )

            accounts.append(account)

            used_proxies.add(proxies[i]) if proxies else None

        # Находим неиспользованные прокси
        self.spare_proxies = proxies_set - used_proxies

        self.logger.info(f"Successfully loaded {len(accounts)} accounts from {private_key_path} and {proxies_path}")
        self.logger.info(f"Found {len(self.spare_proxies)} spare proxies")

        return accounts, list(self.spare_proxies)
