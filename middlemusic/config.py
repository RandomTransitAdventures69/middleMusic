import os
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.environ.get("MIDDLEMUSIC_DATA_DIR", ROOT_DIR / "data"))
LIBRARY_PATH = Path(os.environ.get("MIDDLEMUSIC_LIBRARY_PATH", ROOT_DIR / "music"))

DATA_DIR.mkdir(parents=True, exist_ok=True)
LIBRARY_PATH.mkdir(parents=True, exist_ok=True)

DB_PATH = DATA_DIR / "middlemusic.db"
ARTWORK_DIR = DATA_DIR / "artwork"
ARTWORK_DIR.mkdir(parents=True, exist_ok=True)
