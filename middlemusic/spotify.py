import base64
import json
import os
import re
import threading
import time
from typing import Dict, Optional
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

_TRACK_ID = re.compile(r"^[A-Za-z0-9]{22}$")
_token_lock = threading.Lock()
_cached_token: Optional[str] = None
_token_expires_at = 0.0


def parse_track_id(reference: str) -> str:
    value = reference.strip()
    parsed = urlparse(value)
    if parsed.scheme:
        if parsed.scheme != "https" or parsed.hostname not in {"open.spotify.com", "www.open.spotify.com"}:
            raise ValueError("Spotify metadata accepts a Spotify track ID or open.spotify.com track URL.")
        parts = parsed.path.strip("/").split("/")
        if len(parts) < 2 or parts[0] != "track":
            raise ValueError("Spotify URL must point to a track.")
        value = parts[1]
    if not _TRACK_ID.fullmatch(value):
        raise ValueError("Spotify track ID is invalid.")
    return value


def _access_token() -> str:
    global _cached_token, _token_expires_at
    with _token_lock:
        if _cached_token and time.monotonic() < _token_expires_at:
            return _cached_token

        client_id = os.environ.get("SPOTIFY_CLIENT_ID", "")
        client_secret = os.environ.get("SPOTIFY_CLIENT_SECRET", "")
        if not client_id or not client_secret:
            raise RuntimeError(
                "Set SPOTIFY_CLIENT_ID and SPOTIFY_CLIENT_SECRET to look up Spotify metadata."
            )
        credentials = base64.b64encode(f"{client_id}:{client_secret}".encode("utf-8")).decode("ascii")
        request = Request(
            "https://accounts.spotify.com/api/token",
            data=b"grant_type=client_credentials",
            headers={
                "Authorization": f"Basic {credentials}",
                "Content-Type": "application/x-www-form-urlencoded",
            },
            method="POST",
        )
        try:
            with urlopen(request, timeout=15) as response:
                token_data = json.loads(response.read())
        except HTTPError as error:
            raise RuntimeError(f"Spotify authentication returned HTTP {error.code}.") from error
        except URLError as error:
            raise RuntimeError(f"Spotify authentication failed: {error.reason}.") from error
        token = token_data.get("access_token")
        if not isinstance(token, str) or not token:
            raise RuntimeError("Spotify did not return an access token.")
        _cached_token = token
        _token_expires_at = time.monotonic() + max(int(token_data.get("expires_in", 3600)) - 60, 0)
        return token


def get_track_metadata(reference: str) -> Dict[str, str]:
    track_id = parse_track_id(reference)
    request = Request(
        f"https://api.spotify.com/v1/tracks/{track_id}",
        headers={"Authorization": f"Bearer {_access_token()}"},
    )
    try:
        with urlopen(request, timeout=15) as response:
            track = json.loads(response.read())
    except HTTPError as error:
        raise RuntimeError(f"Spotify metadata lookup returned HTTP {error.code}.") from error
    except URLError as error:
        raise RuntimeError(f"Spotify metadata lookup failed: {error.reason}.") from error

    album = track.get("album") or {}
    artists = track.get("artists") or []
    album_artists = album.get("artists") or []
    release_date = album.get("release_date") or ""
    metadata = {
        "title": track.get("name") or "",
        "artist": ", ".join(item.get("name", "") for item in artists if item.get("name")),
        "album": album.get("name") or "",
        "album_artist": ", ".join(item.get("name", "") for item in album_artists if item.get("name")),
        "track_number": str(track.get("track_number") or ""),
        "year": release_date[:4],
    }
    return {key: value for key, value in metadata.items() if value}
