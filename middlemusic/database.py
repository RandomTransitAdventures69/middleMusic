from __future__ import annotations

import json
import sqlite3
from typing import Any

from .config import DB_PATH


def get_connection() -> sqlite3.Connection:
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def init_db() -> None:
    connection = get_connection()
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            subsonic_password TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS tracks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            path TEXT UNIQUE NOT NULL,
            title TEXT NOT NULL,
            artist TEXT,
            album TEXT,
            album_artist TEXT,
            genre TEXT,
            duration REAL,
            track_number INTEGER,
            year INTEGER,
            artwork_path TEXT,
            added_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS playlists (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            user_id INTEGER NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS playlist_tracks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            playlist_id INTEGER NOT NULL,
            track_id INTEGER NOT NULL,
            position INTEGER NOT NULL,
            UNIQUE (playlist_id, position)
        );

        CREATE TABLE IF NOT EXISTS favorites (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            media_type TEXT NOT NULL,
            media_key TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE (user_id, media_type, media_key)
        );

        CREATE TABLE IF NOT EXISTS conversion_jobs (
            id TEXT PRIMARY KEY,
            user_id INTEGER NOT NULL,
            status TEXT NOT NULL,
            total INTEGER NOT NULL,
            completed INTEGER NOT NULL DEFAULT 0,
            output_dir TEXT NOT NULL,
            outputs_json TEXT NOT NULL DEFAULT '[]',
            errors_json TEXT NOT NULL DEFAULT '[]',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        """
    )
    user_columns = {
        row["name"] for row in connection.execute("PRAGMA table_info(users)")
    }
    if "subsonic_password" not in user_columns:
        connection.execute("ALTER TABLE users ADD COLUMN subsonic_password TEXT")
    connection.commit()
    connection.close()


def get_setting(key: str, default: str | None = None) -> str | None:
    connection = get_connection()
    row = connection.execute(
        "SELECT value FROM settings WHERE key = ?", (key,)
    ).fetchone()
    connection.close()
    if row is None:
        return default
    return row["value"]


def set_setting(key: str, value: str) -> None:
    connection = get_connection()
    connection.execute(
        "INSERT INTO settings(key, value) VALUES(?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (key, value),
    )
    connection.commit()
    connection.close()


def list_users() -> list[sqlite3.Row]:
    connection = get_connection()
    rows = connection.execute("SELECT * FROM users ORDER BY username").fetchall()
    connection.close()
    return rows


def get_user_by_username(username: str) -> sqlite3.Row | None:
    connection = get_connection()
    row = connection.execute(
        "SELECT * FROM users WHERE username = ?", (username,)
    ).fetchone()
    connection.close()
    return row


def create_user(
    username: str, password_hash: str, subsonic_password: str | None = None
) -> sqlite3.Row:
    connection = get_connection()
    cursor = connection.execute(
        "INSERT INTO users(username, password_hash, subsonic_password) VALUES(?, ?, ?)",
        (username, password_hash, subsonic_password),
    )
    connection.commit()
    row = connection.execute(
        "SELECT * FROM users WHERE id = ?", (cursor.lastrowid,)
    ).fetchone()
    connection.close()
    return row


def set_subsonic_password(username: str, encrypted_password: str) -> None:
    connection = get_connection()
    connection.execute(
        "UPDATE users SET subsonic_password = ? WHERE username = ?",
        (encrypted_password, username),
    )
    connection.commit()
    connection.close()


def count_rows(table_name: str) -> int:
    connection = get_connection()
    result = connection.execute(
        f"SELECT COUNT(*) AS count FROM {table_name}"
    ).fetchone()
    connection.close()
    return int(result["count"])


def upsert_track(metadata: dict[str, Any]) -> bool:
    connection = get_connection()
    fetch = connection.execute(
        "SELECT id FROM tracks WHERE path = ?",
        (metadata["path"],),
    ).fetchone()
    if fetch is None:
        connection.execute(
            """
            INSERT INTO tracks(path, title, artist, album, album_artist, genre, duration, track_number, year, artwork_path)
            VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                metadata["path"],
                metadata["title"],
                metadata.get("artist") or "Unknown Artist",
                metadata.get("album") or "Unknown Album",
                metadata.get("album_artist")
                or metadata.get("artist")
                or "Unknown Artist",
                metadata.get("genre") or "Unknown",
                metadata.get("duration") or 0,
                metadata.get("track_number"),
                metadata.get("year"),
                metadata.get("artwork_path"),
            ),
        )
        connection.commit()
        connection.close()
        return True

    connection.execute(
        """
        UPDATE tracks SET title = ?, artist = ?, album = ?, album_artist = ?, genre = ?, duration = ?, track_number = ?, year = ?, artwork_path = ?
        WHERE path = ?
        """,
        (
            metadata["title"],
            metadata.get("artist") or "Unknown Artist",
            metadata.get("album") or "Unknown Album",
            metadata.get("album_artist") or metadata.get("artist") or "Unknown Artist",
            metadata.get("genre") or "Unknown",
            metadata.get("duration") or 0,
            metadata.get("track_number"),
            metadata.get("year"),
            metadata.get("artwork_path"),
            metadata["path"],
        ),
    )
    connection.commit()
    connection.close()
    return False


def list_track_paths() -> list[str]:
    connection = get_connection()
    rows = connection.execute("SELECT path FROM tracks ORDER BY path").fetchall()
    connection.close()
    return [row["path"] for row in rows]


def delete_track_by_path(path: str) -> None:
    connection = get_connection()
    connection.execute("DELETE FROM tracks WHERE path = ?", (path,))
    connection.commit()
    connection.close()


def get_tracks(limit: int = 200, query: str = "") -> list[sqlite3.Row]:
    connection = get_connection()
    sql = "SELECT * FROM tracks"
    params: list[Any] = []
    if query:
        sql += " WHERE lower(title || ' ' || artist || ' ' || album || ' ' || genre) LIKE lower(?)"
        params.append(f"%{query}%")
    sql += " ORDER BY title LIMIT ?"
    params.append(limit)
    rows = connection.execute(sql, params).fetchall()
    connection.close()
    return rows


def get_track_by_id(track_id: int) -> sqlite3.Row | None:
    connection = get_connection()
    row = connection.execute(
        "SELECT * FROM tracks WHERE id = ?", (track_id,)
    ).fetchone()
    connection.close()
    return row


def get_artists() -> list[sqlite3.Row]:
    connection = get_connection()
    rows = connection.execute(
        "SELECT artist, COUNT(id) AS track_count FROM tracks GROUP BY artist ORDER BY artist"
    ).fetchall()
    connection.close()
    return rows


def get_albums() -> list[sqlite3.Row]:
    connection = get_connection()
    rows = connection.execute(
        "SELECT album, album_artist AS artist, COUNT(id) AS track_count FROM tracks GROUP BY album, album_artist ORDER BY album"
    ).fetchall()
    connection.close()
    return rows


def get_playlists_for_user(user_id: int) -> list[sqlite3.Row]:
    connection = get_connection()
    playlists = connection.execute(
        "SELECT * FROM playlists WHERE user_id = ? ORDER BY created_at DESC",
        (user_id,),
    ).fetchall()
    result = []
    for playlist in playlists:
        tracks = connection.execute(
            """
            SELECT tracks.*
            FROM playlist_tracks
            JOIN tracks ON tracks.id = playlist_tracks.track_id
            WHERE playlist_tracks.playlist_id = ?
            ORDER BY playlist_tracks.position
            """,
            (playlist["id"],),
        ).fetchall()
        result.append({**dict(playlist), "tracks": [dict(track) for track in tracks]})
    connection.close()
    return result


def create_playlist(name: str, user_id: int) -> sqlite3.Row:
    connection = get_connection()
    cursor = connection.execute(
        "INSERT INTO playlists(name, user_id) VALUES(?, ?)",
        (name, user_id),
    )
    connection.commit()
    row = connection.execute(
        "SELECT * FROM playlists WHERE id = ?", (cursor.lastrowid,)
    ).fetchone()
    connection.close()
    return row


def add_track_to_playlist(playlist_id: int, track_id: int) -> None:
    connection = get_connection()
    position = connection.execute(
        "SELECT COALESCE(MAX(position), -1) + 1 FROM playlist_tracks WHERE playlist_id = ?",
        (playlist_id,),
    ).fetchone()[0]
    connection.execute(
        "INSERT INTO playlist_tracks(playlist_id, track_id, position) VALUES(?, ?, ?)",
        (playlist_id, track_id, position),
    )
    connection.commit()
    connection.close()


def toggle_favorite(user_id: int, media_type: str, media_key: str) -> bool:
    connection = get_connection()
    row = connection.execute(
        "SELECT id FROM favorites WHERE user_id = ? AND media_type = ? AND media_key = ?",
        (user_id, media_type, media_key),
    ).fetchone()
    if row is not None:
        connection.execute(
            "DELETE FROM favorites WHERE id = ?",
            (row["id"],),
        )
        connection.commit()
        connection.close()
        return False
    connection.execute(
        "INSERT INTO favorites(user_id, media_type, media_key) VALUES(?, ?, ?)",
        (user_id, media_type, media_key),
    )
    connection.commit()
    connection.close()
    return True


def get_favorites(user_id: int) -> dict[str, list[str]]:
    connection = get_connection()
    favorites = connection.execute(
        "SELECT media_type, media_key FROM favorites WHERE user_id = ? ORDER BY media_type, media_key",
        (user_id,),
    ).fetchall()
    result = {"tracks": [], "albums": []}
    for item in favorites:
        if item["media_type"] == "track":
            result["tracks"].append(str(item["media_key"]))
        elif item["media_type"] == "album":
            result["albums"].append(str(item["media_key"]))
    connection.close()
    return result


def get_recent_tracks(limit: int = 8) -> list[sqlite3.Row]:
    connection = get_connection()
    rows = connection.execute(
        "SELECT * FROM tracks ORDER BY added_at DESC LIMIT ?",
        (limit,),
    ).fetchall()
    connection.close()
    return rows


def get_random_albums(limit: int = 6) -> list[sqlite3.Row]:
    connection = get_connection()
    rows = connection.execute(
        "SELECT album, album_artist AS artist, COUNT(id) AS track_count, MIN(artwork_path) AS artwork_path FROM tracks GROUP BY album, album_artist ORDER BY RANDOM() LIMIT ?",
        (limit,),
    ).fetchall()
    connection.close()
    return rows


def create_conversion_job(
    job_id: str, user_id: int, total: int, output_dir: str
) -> None:
    connection = get_connection()
    connection.execute(
        "INSERT INTO conversion_jobs(id, user_id, status, total, output_dir) VALUES(?, ?, 'queued', ?, ?)",
        (job_id, user_id, total, output_dir),
    )
    connection.commit()
    connection.close()


def update_conversion_job(
    job_id: str,
    status: str,
    completed: int,
    outputs: list[str],
    errors: list[dict[str, str]],
) -> None:
    connection = get_connection()
    connection.execute(
        """
        UPDATE conversion_jobs
        SET status = ?, completed = ?, outputs_json = ?, errors_json = ?, updated_at = CURRENT_TIMESTAMP
        WHERE id = ?
        """,
        (status, completed, json.dumps(outputs), json.dumps(errors), job_id),
    )
    connection.commit()
    connection.close()


def _conversion_job(row: sqlite3.Row) -> dict[str, Any]:
    result = dict(row)
    result["outputs"] = json.loads(result.pop("outputs_json"))
    result["errors"] = json.loads(result.pop("errors_json"))
    return result


def get_conversion_job(job_id: str, user_id: int) -> dict[str, Any] | None:
    connection = get_connection()
    row = connection.execute(
        "SELECT * FROM conversion_jobs WHERE id = ? AND user_id = ?",
        (job_id, user_id),
    ).fetchone()
    connection.close()
    return _conversion_job(row) if row else None


def list_conversion_jobs(user_id: int, limit: int = 20) -> list[dict[str, Any]]:
    connection = get_connection()
    rows = connection.execute(
        "SELECT * FROM conversion_jobs WHERE user_id = ? ORDER BY created_at DESC LIMIT ?",
        (user_id, limit),
    ).fetchall()
    connection.close()
    return [_conversion_job(row) for row in rows]
