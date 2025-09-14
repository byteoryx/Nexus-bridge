import os
import sys
from pathlib import Path

if getattr(sys, 'frozen', False):
    ROOT_DIR = Path(sys.executable).parent.absolute()
else:
    ROOT_DIR = Path(__file__).parent.parent.absolute()

ABIS_DIR = os.path.join(ROOT_DIR, 'core', 'abis')
LOG_FILE = os.path.join(ROOT_DIR, 'logs', 'app.log')
ACCOUNTS_DATA_FILE = os.path.join(ROOT_DIR, 'accounts_data.xlsx')
DATABASE = os.path.join(ROOT_DIR, 'core','database.db')
AUXILIARY_DATA_DIR = os.path.join(ROOT_DIR, 'core','auxiliary_data')

CEX_DIR = os.path.join(ROOT_DIR, 'libs', 'cex')

PK_TXT_FILE = os.path.join(ROOT_DIR, 'private_keys.txt')
PROXIES_TXT_FILE = os.path.join(ROOT_DIR, 'proxies.txt')
CEX_DEPOSIT_ADDRESSES_TXT_FILE = os.path.join(ROOT_DIR, 'deposit_addresses.txt')
