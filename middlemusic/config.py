import os
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent


def _user_data_directory() -> Path:
    if sys.platform == "win32":
        return Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData/Local")) / "middleMusic"
    if sys.platform == "darwin":
        return Path.home() / "Library/Application Support/middleMusic"
    return Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local/share")) / "middlemusic"


SOURCE_CHECKOUT = (ROOT_DIR / "requirements.txt").is_file() and not getattr(
    sys, "frozen", False
)
DATA_DIR = Path(
    os.environ.get(
        "MIDDLEMUSIC_DATA_DIR",
        ROOT_DIR / "data" if SOURCE_CHECKOUT else _user_data_directory(),
    )
)
LIBRARY_PATH = Path(
    os.environ.get(
        "MIDDLEMUSIC_LIBRARY_PATH",
        ROOT_DIR / "music" if SOURCE_CHECKOUT else Path.home() / "Music",
    )
)

DATA_DIR.mkdir(parents=True, exist_ok=True)
LIBRARY_PATH.mkdir(parents=True, exist_ok=True)

DB_PATH = DATA_DIR / "middlemusic.db"
ARTWORK_DIR = DATA_DIR / "artwork"
ARTWORK_DIR.mkdir(parents=True, exist_ok=True)
