import os
import sys
from pathlib import Path

from core.settings_models import Settings
from utils.utils import read_toml

if getattr(sys, 'frozen', False):
    ROOT_DIR = Path(sys.executable).parent.absolute()
else:
    ROOT_DIR = Path(__file__).parent.parent.absolute()

SETTINGS_FILE = os.path.join(ROOT_DIR, 'settings.toml')
settings = Settings.load_from_toml(read_toml(path=SETTINGS_FILE))
