from __future__ import annotations

import base64
import binascii
import json
import logging
import mimetypes
import random
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

from flask import Response, current_app, jsonify, request, send_file
from werkzeug.security import check_password_hash

from .config import ARTWORK_DIR, LIBRARY_PATH
from .database import (
    add_track_to_playlist,
    create_playlist,
    get_favorites,
    get_playlists_for_user,
    get_setting,
    get_track_by_id,
    get_tracks,
    get_user_by_username,
    set_subsonic_password,
    toggle_favorite,
)
from .subsonic_auth import decrypt_password, encrypt_password, verify_token

logger = logging.getLogger(__name__)
API_VERSION = "1.16.1"
SERVER_VERSION = "0.2.0"
_BASE_RESPONSE = {
    "version": API_VERSION,
    "type": "middleMusic",
    "serverVersion": SERVER_VERSION,
    "openSubsonic": True,
}


class SubsonicError(Exception):
    def __init__(self, message: str, code: int = 0):
        super().__init__(message)
        self.code = code


def _encode_directory_id(kind: str, value: Any) -> str:
    payload = json.dumps([kind, value], separators=(",", ":")).encode("utf-8")
    return f"{kind[0]}-{base64.urlsafe_b64encode(payload).decode('ascii').rstrip('=')}"


def _decode_directory_id(value: str) -> tuple[str, Any]:
    try:
        prefix, encoded = value.split("-", 1)
        payload = base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4))
        kind, data = json.loads(payload)
        if prefix != kind[0] or kind not in {"artist", "album"}:
            raise ValueError
        if kind == "artist" and not isinstance(data, str):
            raise ValueError
        if kind == "album" and (
            not isinstance(data, list)
            or len(data) != 2
            or not all(isinstance(item, str) for item in data)
        ):
            raise ValueError
        return kind, data
    except (ValueError, TypeError, json.JSONDecodeError, binascii.Error) as error:
        raise SubsonicError("The requested music directory was not found.", 70) from error


def _authenticate() -> dict[str, Any]:
    params = request.values
    username = params.get("u", "").strip()
    user = get_user_by_username(username) if username else None
    if user is None:
        raise SubsonicError("Authentication failed.", 10)

    password = None
    supplied_password = params.get("p")
    if supplied_password:
        try:
            if supplied_password.startswith("enc:"):
                password = bytes.fromhex(supplied_password[4:]).decode("utf-8")
            else:
                password = supplied_password
        except (ValueError, UnicodeDecodeError):
            password = None
        if password and check_password_hash(user["password_hash"], password):
            if not user["subsonic_password"]:
                set_subsonic_password(
                    username,
                    encrypt_password(password, current_app.config["SECRET_KEY"]),
                )
            return dict(user)

    token = params.get("t", "")
    salt = params.get("s", "")
    if token and salt and user["subsonic_password"]:
        stored_password = decrypt_password(
            user["subsonic_password"], current_app.config["SECRET_KEY"]
        )
        if stored_password and verify_token(stored_password, token, salt):
            return dict(user)
    raise SubsonicError("Authentication failed.", 10)


def _xml_value(parent: ET.Element, name: str, value: Any) -> None:
    if value is None:
        return
    if isinstance(value, list):
        for item in value:
            _xml_value(parent, name, item)
        return
    if isinstance(value, dict):
        attributes = {
            key: _xml_scalar(item)
            for key, item in value.items()
            if not isinstance(item, (dict, list)) and item is not None
        }
        child = ET.SubElement(parent, name, attributes)
        for key, item in value.items():
            if isinstance(item, (dict, list)):
                _xml_value(child, key, item)
        return
    ET.SubElement(parent, name).text = _xml_scalar(value)


def _xml_scalar(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def _response(data: dict[str, Any] | None = None, error: SubsonicError | None = None):
    result = {
        "status": "failed" if error else "ok",
        **_BASE_RESPONSE,
    }
    if error:
        result["error"] = {"code": error.code, "message": str(error)}
    elif data:
        result.update(data)

    if request.values.get("f", "xml").lower() == "json":
        return jsonify({"subsonic-response": result})

    root = ET.Element(
        "subsonic-response",
        {
            key: _xml_scalar(value)
            for key, value in result.items()
            if not isinstance(value, (dict, list))
        },
    )
    for key, value in result.items():
        if isinstance(value, (dict, list)):
            _xml_value(root, key, value)
    return Response(
        ET.tostring(root, encoding="utf-8", xml_declaration=True),
        content_type="application/xml; charset=utf-8",
    )


def _integer(name: str, default: int, maximum: int = 5000) -> int:
    value = request.values.get(name)
    if value is None:
        return default
    try:
        parsed = int(value)
    except ValueError as error:
        raise SubsonicError(f"Parameter '{name}' must be an integer.", 10) from error
    if parsed < 0:
        raise SubsonicError(f"Parameter '{name}' must not be negative.", 10)
    return min(parsed, maximum)


def _all_tracks() -> list[dict[str, Any]]:
    return [dict(track) for track in get_tracks(limit=10000)]


def _group_albums(tracks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    albums: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for track in tracks:
        key = (track.get("album_artist") or track.get("artist") or "", track["album"])
        albums.setdefault(key, []).append(track)
    return [
        {
            "artist": artist,
            "name": album,
            "tracks": items,
            "id": _encode_directory_id("album", [artist, album]),
        }
        for (artist, album), items in albums.items()
    ]


def _track_object(track: dict[str, Any], parent: str | None = None) -> dict[str, Any]:
    path = Path(track["path"])
    try:
        size = path.stat().st_size
    except OSError:
        size = 0
    result = {
        "id": str(track["id"]),
        "title": track["title"],
        "isDir": False,
        "isVideo": False,
        "album": track.get("album"),
        "artist": track.get("artist"),
        "albumArtist": track.get("album_artist"),
        "track": track.get("track_number"),
        "year": track.get("year"),
        "genre": track.get("genre"),
        "coverArt": str(track["id"]) if track.get("artwork_path") else None,
        "size": size,
        "contentType": mimetypes.guess_type(path.name)[0] or "application/octet-stream",
        "suffix": path.suffix.lstrip(".").lower(),
        "duration": int(track.get("duration") or 0),
        "type": "music",
    }
    if parent:
        result["parent"] = parent
    return result


def _artist_object(name: str, tracks: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "id": _encode_directory_id("artist", name),
        "name": name,
        "albumCount": len(
            {
                (track.get("album_artist") or track.get("artist"), track["album"])
                for track in tracks
            }
        ),
    }


def _album_object(album: dict[str, Any]) -> dict[str, Any]:
    tracks = album["tracks"]
    first = tracks[0]
    return {
        "id": album["id"],
        "name": album["name"],
        "artist": album["artist"],
        "artistId": _encode_directory_id("artist", album["artist"]),
        "songCount": len(tracks),
        "duration": int(sum(track.get("duration") or 0 for track in tracks)),
        "year": first.get("year"),
        "genre": first.get("genre"),
        "coverArt": str(first["id"]) if first.get("artwork_path") else None,
        "created": first.get("added_at"),
    }


def _library_path(track: dict[str, Any]) -> Path:
    library = Path(get_setting("library_path") or LIBRARY_PATH).resolve()
    path = Path(track["path"]).resolve()
    try:
        path.relative_to(library)
    except ValueError as error:
        raise SubsonicError("The requested file is outside the music library.", 70) from error
    if not path.is_file():
        raise SubsonicError("The requested file is not available.", 70)
    return path


def _track_by_parameter(name: str = "id") -> dict[str, Any]:
    track_id = _integer(name, -1, maximum=2**31 - 1)
    if track_id < 1:
        raise SubsonicError("A valid song ID is required.", 10)
    track = get_track_by_id(track_id)
    if track is None:
        raise SubsonicError("The requested song was not found.", 70)
    return dict(track)


def _directory(identifier: str) -> dict[str, Any]:
    tracks = _all_tracks()
    if identifier == "root":
        artists = {}
        for track in tracks:
            name = track.get("artist") or "Unknown Artist"
            artists.setdefault(name, []).append(track)
        children = [
            {
                **_artist_object(name, items),
                "parent": "root",
                "isDir": True,
                "childCount": len(items),
            }
            for name, items in sorted(artists.items(), key=lambda item: item[0].casefold())
        ]
        return {"id": "root", "name": "Music", "isDir": True, "child": children}

    kind, value = _decode_directory_id(identifier)
    if kind == "artist":
        matching = [
            track
            for track in tracks
            if (track.get("artist") or "") == value
        ]
        albums = _group_albums(matching)
        children = [
            {
                **_album_object(album),
                "parent": identifier,
                "isDir": True,
                "childCount": len(album["tracks"]),
            }
            for album in albums
        ]
        return {
            "id": identifier,
            "name": value,
            "isDir": True,
            "child": children,
        }

    artist, album_name = value
    matching = [
        track
        for track in tracks
        if (track.get("album_artist") or track.get("artist") or "") == artist
        and track["album"] == album_name
    ]
    if not matching:
        raise SubsonicError("The requested album was not found.", 70)
    return {
        "id": identifier,
        "name": album_name,
        "isDir": True,
        "child": [_track_object(track, identifier) for track in matching],
    }


def _handle(method: str, user: dict[str, Any]):
    if method in {"ping", "getLicense"}:
        if method == "getLicense":
            return {"license": {"valid": True, "email": "", "licenseExpires": "2099-12-31T23:59:59"}}
        return {}
    if method == "getMusicFolders":
        return {"musicFolders": {"musicFolder": [{"id": 1, "name": "Music"}]}}
    if method == "getIndexes":
        artists = {}
        for track in _all_tracks():
            name = track.get("artist") or "Unknown Artist"
            initial = name[0].upper() if name else "#"
            if not initial.isalpha():
                initial = "#"
            artists.setdefault(initial, {}).setdefault(name, []).append(track)
        return {
            "indexes": {
                "lastModified": 0,
                "ignoredArticles": "",
                "index": [
                    {
                        "name": initial,
                        "artist": [
                            _artist_object(name, items)
                            for name, items in sorted(
                                grouped.items(), key=lambda item: item[0].casefold()
                            )
                        ],
                    }
                    for initial, grouped in sorted(artists.items())
                ],
            }
        }
    if method == "getMusicDirectory":
        identifier = request.values.get("id", "")
        if not identifier:
            raise SubsonicError("A music directory ID is required.", 10)
        return {"directory": _directory(identifier)}
    if method == "getArtists":
        indexes = _handle("getIndexes", user)["indexes"]
        return {"artists": indexes}
    if method == "getArtist":
        identifier = request.values.get("id", "")
        kind, name = _decode_directory_id(identifier)
        if kind != "artist":
            raise SubsonicError("The requested artist was not found.", 70)
        tracks = [
            track
            for track in _all_tracks()
            if (track.get("artist") or "") == name
        ]
        if not tracks:
            raise SubsonicError("The requested artist was not found.", 70)
        return {
            "artist": {
                **_artist_object(name, tracks),
                "album": [
                    _album_object(album)
                    for album in _group_albums(tracks)
                ],
            }
        }
    if method in {"getAlbumList", "getAlbumList2"}:
        albums = _group_albums(_all_tracks())
        list_type = request.values.get("type", "alphabeticalByName")
        if list_type == "random":
            random.shuffle(albums)
        elif list_type == "newest":
            albums.sort(
                key=lambda album: max(
                    track.get("added_at") or "" for track in album["tracks"]
                ),
                reverse=True,
            )
        elif list_type in {
            "alphabeticalByName",
            "alphabeticalByArtist",
            "byName",
            "byArtist",
        }:
            albums.sort(
                key=lambda album: (
                    album["name"].casefold(),
                    album["artist"].casefold(),
                )
                if list_type in {"alphabeticalByName", "byName"}
                else (album["artist"].casefold(), album["name"].casefold())
            )
        else:
            raise SubsonicError(f"Album list type '{list_type}' is unsupported.", 10)
        offset = _integer("offset", 0)
        size = _integer("size", 10)
        selected = [_album_object(album) for album in albums[offset : offset + size]]
        key = "albumList2" if method == "getAlbumList2" else "albumList"
        return {key: {"album": selected}}
    if method == "getAlbum":
        identifier = request.values.get("id", "")
        kind, value = _decode_directory_id(identifier)
        if kind != "album":
            raise SubsonicError("The requested album was not found.", 70)
        directory = _directory(identifier)
        return {"album": directory | {"song": directory["child"]}}
    if method == "getSong":
        return {"song": _track_object(_track_by_parameter())}
    if method == "search3":
        query = request.values.get("query", "").strip()
        if not query:
            raise SubsonicError("A search query is required.", 10)
        tracks = [dict(track) for track in get_tracks(limit=10000, query=query)]
        offset = _integer("songOffset", 0)
        count = _integer("songCount", 20)
        return {
            "searchResult3": {
                "artist": [],
                "album": [],
                "song": [
                    _track_object(track)
                    for track in tracks[offset : offset + count]
                ],
            }
        }
    if method == "getRandomSongs":
        tracks = _all_tracks()
        random.shuffle(tracks)
        size = _integer("size", 10)
        return {"randomSongs": {"song": [_track_object(track) for track in tracks[:size]]}}
    if method == "getGenres":
        genres = {}
        for track in _all_tracks():
            name = track.get("genre") or ""
            if name:
                genres[name] = genres.get(name, 0) + 1
        return {
            "genres": {
                "genre": [
                    {"value": name, "songCount": count}
                    for name, count in sorted(genres.items())
                ]
            }
        }
    if method == "getStarred2":
        favorites = get_favorites(user["id"])
        favorite_ids = {int(value) for value in favorites["tracks"]}
        tracks = [track for track in _all_tracks() if track["id"] in favorite_ids]
        album_names = set(favorites["albums"])
        albums = [
            album
            for album in _group_albums(_all_tracks())
            if album["name"] in album_names
        ]
        return {
            "starred2": {
                "song": [_track_object(track) for track in tracks],
                "album": [_album_object(album) for album in albums],
            }
        }
    if method in {"star", "unstar"}:
        active = method == "star"
        for track_id in request.values.getlist("id"):
            track = get_track_by_id(_parse_id(track_id))
            if track is None:
                raise SubsonicError("The requested song was not found.", 70)
            _set_favorite(user["id"], "track", str(track["id"]), active)
        for album_id in request.values.getlist("albumId"):
            kind, value = _decode_directory_id(album_id)
            if kind != "album":
                raise SubsonicError("The requested album was not found.", 70)
            _set_favorite(user["id"], "album", value[1], active)
        return {}
    if method == "getPlaylists":
        return {
            "playlists": {
                "playlist": [
                    _playlist_object(playlist)
                    for playlist in get_playlists_for_user(user["id"])
                ]
            }
        }
    if method == "getPlaylist":
        playlist_id = _parse_id(request.values.get("id", ""))
        playlist = next(
            (
                item
                for item in get_playlists_for_user(user["id"])
                if item["id"] == playlist_id
            ),
            None,
        )
        if playlist is None:
            raise SubsonicError("The requested playlist was not found.", 70)
        return {"playlist": _playlist_object(playlist)}
    if method == "createPlaylist":
        name = request.values.get("name", "").strip()
        if not name or len(name) > 120:
            raise SubsonicError("A playlist name between 1 and 120 characters is required.", 10)
        playlist = create_playlist(name, user["id"])
        for song_id in request.values.getlist("songId"):
            if get_track_by_id(_parse_id(song_id)) is None:
                raise SubsonicError("A requested song was not found.", 70)
            add_track_to_playlist(playlist["id"], _parse_id(song_id))
        refreshed = next(
            item
            for item in get_playlists_for_user(user["id"])
            if item["id"] == playlist["id"]
        )
        return {"playlist": _playlist_object(refreshed)}
    if method in {"stream", "download"}:
        track = _track_by_parameter()
        path = _library_path(track)
        return send_file(
            path,
            as_attachment=method == "download",
            conditional=True,
            download_name=path.name,
        )
    if method == "getCoverArt":
        track = _track_by_parameter()
        artwork = track.get("artwork_path")
        if not artwork or not Path(artwork).is_file():
            raise SubsonicError("Cover art was not found.", 70)
        try:
            artwork_path = Path(artwork).resolve(strict=True)
            artwork_path.relative_to(ARTWORK_DIR.resolve())
        except (OSError, ValueError) as error:
            raise SubsonicError("Cover art was not found.", 70) from error
        return send_file(artwork_path, conditional=True)
    raise SubsonicError(f"Unknown Subsonic method '{method}'.", 0)


def _parse_id(value: str) -> int:
    try:
        identifier = int(value)
    except (TypeError, ValueError) as error:
        raise SubsonicError("A valid ID is required.", 10) from error
    if identifier < 1:
        raise SubsonicError("A valid ID is required.", 10)
    return identifier


def _set_favorite(user_id: int, media_type: str, media_key: str, active: bool) -> None:
    favorites = get_favorites(user_id)
    existing = (
        media_key in favorites["tracks"]
        if media_type == "track"
        else media_key in favorites["albums"]
    )
    if existing != active:
        toggle_favorite(user_id, media_type, media_key)


def _playlist_object(playlist: dict[str, Any]) -> dict[str, Any]:
    entries = [dict(track) for track in playlist.get("tracks", [])]
    return {
        "id": str(playlist["id"]),
        "name": playlist["name"],
        "owner": playlist.get("username", ""),
        "public": False,
        "songCount": len(entries),
        "duration": int(sum(track.get("duration") or 0 for track in entries)),
        "entry": [_track_object(track, str(playlist["id"])) for track in entries],
    }


def register_subsonic_api(app) -> None:
    @app.route("/rest/<method>.view", methods=["GET", "POST"])
    def subsonic_endpoint(method: str):
        try:
            user = _authenticate()
            result = _handle(method, user)
            if isinstance(result, Response):
                return result
            return _response(result)
        except SubsonicError as error:
            return _response(error=error)
        except Exception:
            logger.exception("Unexpected Subsonic API failure for %s", method)
            return _response(error=SubsonicError("Internal server error.", 0))
