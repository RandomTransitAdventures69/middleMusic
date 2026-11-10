from __future__ import annotations

import hashlib
import logging
import os
from pathlib import Path
from typing import Any

from mutagen import File as MutagenFile
from mutagen import MutagenError

from .config import ARTWORK_DIR
from .database import delete_track_by_path, list_track_paths, upsert_track

AUDIO_EXTENSIONS = {".mp3", ".flac", ".aac", ".m4a", ".ogg", ".oga", ".wav", ".opus"}
logger = logging.getLogger(__name__)


def _normalize_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (list, tuple)):
        return str(value[0]) if value else ""
    return str(value)


def _safe_int(value: Any) -> int | None:
    if value is None:
        return None
    if isinstance(value, str):
        raw = value.split("/")[0].strip()
        try:
            return int(raw)
        except ValueError:
            return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _find_artwork(audio: Any, file_path: str) -> str | None:
    try:
        image = None
        tags = getattr(audio, "tags", {}) or {}
        pictures = getattr(audio, "pictures", None)
        if pictures:
            image = pictures[0]
        elif tags.get("APIC"):
            image = tags.get("APIC")[0]
        elif tags.get("covr"):
            image = tags.get("covr")[0]
        if image is not None:
            image_data = getattr(image, "data", image)
            if not isinstance(image_data, bytes) or not image_data:
                return None
            digest = hashlib.sha256(file_path.encode("utf-8")).hexdigest()
            extension = ".jpg"
            mime = getattr(image, "mime", "")
            if isinstance(mime, str) and mime == "image/png":
                extension = ".png"
            art_path = ARTWORK_DIR / f"{digest}{extension}"
            art_path.write_bytes(image_data)
            return str(art_path)
    except (OSError, TypeError, IndexError, AttributeError) as error:
        logger.warning("Could not extract artwork from %s: %s", file_path, error)
    return None


def extract_metadata(file_path: str) -> dict[str, Any] | None:
    try:
        audio = MutagenFile(file_path, easy=False)
    except (
        MutagenError,
        OSError,
        ValueError,
        TypeError,
        IndexError,
        KeyError,
    ) as error:
        logger.warning("Could not read audio metadata from %s: %s", file_path, error)
        return None
    if audio is None:
        return None

    tags = getattr(audio, "tags", None) or {}
    if hasattr(audio, "info"):
        duration = float(getattr(audio.info, "length", 0) or 0)
    else:
        duration = 0.0

    title = _normalize_text(tags.get("TIT2", [None])[0] if tags.get("TIT2") else None)
    if not title:
        title = _normalize_text(
            tags.get("title", [None])[0] if tags.get("title") else None
        )
    title = title or Path(file_path).stem

    artist = _normalize_text(tags.get("TPE1", [None])[0] if tags.get("TPE1") else None)
    if not artist:
        artist = _normalize_text(
            tags.get("artist", [None])[0] if tags.get("artist") else None
        )
    artist = artist or "Unknown Artist"

    album = _normalize_text(tags.get("TALB", [None])[0] if tags.get("TALB") else None)
    if not album:
        album = _normalize_text(
            tags.get("album", [None])[0] if tags.get("album") else None
        )
    album = album or "Unknown Album"

    album_artist = _normalize_text(
        tags.get("TPE2", [None])[0] if tags.get("TPE2") else None
    )
    if not album_artist:
        album_artist = artist

    genre = _normalize_text(tags.get("TCON", [None])[0] if tags.get("TCON") else None)
    if not genre:
        genre = _normalize_text(
            tags.get("genre", [None])[0] if tags.get("genre") else None
        )
    genre = genre or "Unknown"

    year_value = (
        tags.get("TDRC", [None]) or tags.get("year", [None]) or tags.get("TYER", [None])
    )
    year = None
    if year_value:
        first = _normalize_text(year_value[0])
        if first:
            try:
                year = int(first[:4])
            except ValueError:
                year = None

    track_number = None
    track_tag = tags.get("TRCK", [None]) or tags.get("tracknumber", [None])
    if track_tag:
        track_number = _safe_int(_normalize_text(track_tag[0]))

    artwork_path = _find_artwork(audio, file_path)

    return {
        "path": file_path,
        "title": title,
        "artist": artist,
        "album": album,
        "album_artist": album_artist,
        "genre": genre,
        "duration": duration,
        "track_number": track_number,
        "year": year,
        "artwork_path": artwork_path,
    }


def scan_library(root_path: str) -> dict[str, int]:
    root = Path(root_path)
    if not root.exists() or not root.is_dir():
        raise FileNotFoundError(f"Library path does not exist: {root_path}")

    discovered = set()

    def log_walk_error(error: OSError) -> None:
        logger.warning("Could not scan directory %s: %s", error.filename, error)

    for directory, _, files in os.walk(root, onerror=log_walk_error):
        for filename in files:
            if Path(filename).suffix.lower() in AUDIO_EXTENSIONS:
                full_path = str(Path(directory) / filename)
                discovered.add(full_path)

    current_paths = set(list_track_paths())
    seen = set()

    added = 0
    for file_path in sorted(discovered):
        seen.add(file_path)
        metadata = extract_metadata(file_path)
        if not metadata:
            continue
        was_new = upsert_track(metadata)
        if was_new:
            added += 1

    stale_paths = current_paths - seen
    for stale in sorted(stale_paths):
        delete_track_by_path(stale)

    return {
        "tracks": len(seen),
        "added": added,
        "updated": len(seen) - added,
    }
