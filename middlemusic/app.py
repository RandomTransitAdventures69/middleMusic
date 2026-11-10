import json
import os
import re
import secrets
import uuid
from pathlib import Path
from urllib.parse import quote

from flask import Flask, abort, jsonify, request, send_file, session
from werkzeug.security import check_password_hash, generate_password_hash

from .config import ARTWORK_DIR, DATA_DIR, LIBRARY_PATH
from .conversion_jobs import start_conversion_job
from .converter import BITRATES, parse_csv
from .database import (
    add_track_to_playlist,
    count_rows,
    create_playlist,
    create_user,
    get_albums,
    get_artists,
    get_conversion_job,
    get_favorites,
    get_playlists_for_user,
    get_random_albums,
    get_recent_tracks,
    get_setting,
    get_track_by_id,
    get_tracks,
    get_user_by_username,
    init_db,
    list_conversion_jobs,
    set_setting,
    toggle_favorite,
)
from .scanner import scan_library


def create_app():
    app = Flask(__name__, static_folder="../static", template_folder="../templates")
    app.config["MAX_CONTENT_LENGTH"] = 5 * 1024 * 1024
    secret_key_path = DATA_DIR / "session-secret"
    secret_key = os.environ.get("SECRET_KEY")
    if not secret_key:
        if not secret_key_path.exists():
            secret_key_path.write_text(secrets.token_hex(32), encoding="utf-8")
        secret_key = secret_key_path.read_text(encoding="utf-8").strip()
    app.config["SECRET_KEY"] = secret_key
    app.config["JSON_SORT_KEYS"] = False
    init_db()

    def requires_login():
        if session.get("user_id") is None:
            return abort(401, description="Authentication required")

    def serialize_track(track):
        item = dict(track)
        artwork_path = item.pop("artwork_path", None)
        item.pop("path", None)
        item["artwork_url"] = f"/api/artwork/{item['id']}" if artwork_path else None
        return item

    def serialize_conversion_job(job):
        return {
            "id": job["id"],
            "status": job["status"],
            "total": job["total"],
            "completed": job["completed"],
            "progress": round(job["completed"] / job["total"] * 100) if job["total"] else 0,
            "outputs": [
                {
                    "name": name,
                    "url": f"/api/conversions/{job['id']}/files/{quote(name)}",
                }
                for name in job["outputs"]
            ],
            "errors": job["errors"],
            "created_at": job["created_at"],
            "updated_at": job["updated_at"],
        }

    @app.get("/")
    def index():
        return app.send_static_file("index.html")

    @app.get("/api/health")
    def health():
        return jsonify({"status": "ok", "version": "0.1.0"})

    @app.get("/api/setup/status")
    def setup_status():
        user_count = count_rows("users")
        return jsonify(
            {
                "requires_setup": user_count == 0,
                "library_path": get_setting("library_path") or str(LIBRARY_PATH),
                "server_name": get_setting("server_name") or "middleMusic",
            }
        )

    @app.post("/api/setup")
    def setup():
        payload = request.get_json(silent=True) or {}
        username = payload.get("username", "")
        password = payload.get("password", "")
        library_path = payload.get("library_path", str(LIBRARY_PATH))
        server_name = payload.get("server_name", "middleMusic")
        if not all(isinstance(value, str) for value in (username, password, library_path, server_name)):
            return jsonify({"error": "Setup values must be text."}), 400
        username = username.strip()
        library_path = library_path.strip()
        server_name = server_name.strip() or "middleMusic"

        if count_rows("users") > 0:
            return jsonify({"error": "Setup already completed."}), 400
        if not username or len(password) < 8:
            return jsonify({"error": "Create a username and a password at least 8 characters long."}), 400
        if len(username) > 80 or len(server_name) > 120:
            return jsonify({"error": "Username or server name is too long."}), 400
        if not library_path or not Path(library_path).is_dir():
            return jsonify({"error": "That music folder does not exist or is not a folder."}), 400

        user = create_user(username, generate_password_hash(password))
        set_setting("library_path", library_path)
        set_setting("server_name", server_name)
        session["user_id"] = user["id"]
        session["username"] = user["username"]

        return jsonify({"success": True, "user": {"id": user["id"], "username": user["username"]}})

    @app.get("/api/session")
    def session_state():
        user_id = session.get("user_id")
        if user_id is None:
            return jsonify({"logged_in": False})
        return jsonify({"logged_in": True, "user": {"id": user_id, "username": session.get("username")}})

    @app.post("/api/login")
    def login():
        payload = request.get_json(silent=True) or {}
        username = payload.get("username", "")
        password = payload.get("password", "")
        if not isinstance(username, str) or not isinstance(password, str):
            return jsonify({"error": "Username and password must be text."}), 400
        username = username.strip()

        user = get_user_by_username(username)
        if user is None or not check_password_hash(user["password_hash"], password):
            return jsonify({"error": "Invalid username or password."}), 401

        session["user_id"] = user["id"]
        session["username"] = user["username"]
        return jsonify({"success": True, "user": {"id": user["id"], "username": user["username"]}})

    @app.post("/api/logout")
    def logout():
        session.clear()
        return jsonify({"success": True})

    @app.get("/api/library/stats")
    def library_stats():
        requires_login()
        return jsonify(
            {
                "library_path": get_setting("library_path") or str(LIBRARY_PATH),
                "tracks": count_rows("tracks"),
                "artists": len(get_artists()),
                "albums": len(get_albums()),
                "server_name": get_setting("server_name") or "middleMusic",
            }
        )

    @app.post("/api/library/scan")
    def scan_library_route():
        requires_login()
        library_path = get_setting("library_path") or str(LIBRARY_PATH)
        try:
            stats = scan_library(library_path)
        except FileNotFoundError as error:
            return jsonify({"error": str(error)}), 400
        return jsonify({"success": True, "stats": stats})

    @app.get("/api/artists")
    def artists():
        requires_login()
        return jsonify({"artists": [dict(item) for item in get_artists()]})

    @app.get("/api/albums")
    def albums():
        requires_login()
        return jsonify({"albums": [dict(item) for item in get_albums()]})

    @app.get("/api/tracks")
    def tracks():
        requires_login()
        query = (request.args.get("q") or "").strip()
        items = get_tracks(limit=200, query=query)
        return jsonify({"tracks": [serialize_track(item) for item in items]})

    @app.get("/api/search")
    def search():
        requires_login()
        query = (request.args.get("q") or "").strip()
        return jsonify({"tracks": [serialize_track(item) for item in get_tracks(limit=200, query=query)]})

    @app.get("/api/home")
    def home():
        requires_login()
        return jsonify(
            {
                "recently_played": [],
                "recently_added": [serialize_track(track) for track in get_recent_tracks(limit=8)],
                "favorite_albums": [dict(item) for item in get_random_albums(limit=6)],
            }
        )

    @app.get("/api/favorites")
    def favorites():
        requires_login()
        favorites = get_favorites(session["user_id"])
        track_ids = [int(item) for item in favorites["tracks"]]
        album_names = favorites["albums"]
        tracks = []
        if track_ids:
            for item in get_tracks(limit=200):
                if item["id"] in track_ids:
                    tracks.append(serialize_track(item))
        return jsonify({"tracks": tracks, "albums": album_names})

    @app.post("/api/favorites/toggle")
    def toggle_favorite_endpoint():
        requires_login()
        payload = request.get_json(silent=True) or {}
        media_type = payload.get("media_type")
        media_key = payload.get("media_key")
        if media_type not in {"track", "album"} or media_key is None:
            return jsonify({"error": "Choose a track or album to favorite."}), 400
        active = toggle_favorite(session["user_id"], media_type, str(media_key))
        return jsonify({"success": True, "active": active})

    @app.get("/api/playlists")
    def playlists():
        requires_login()
        items = get_playlists_for_user(session["user_id"])
        for playlist in items:
            playlist["tracks"] = [serialize_track(track) for track in playlist["tracks"]]
        return jsonify({"playlists": items})

    @app.post("/api/playlists")
    def create_playlist_endpoint():
        requires_login()
        payload = request.get_json(silent=True) or {}
        name = payload.get("name", "")
        if not isinstance(name, str):
            return jsonify({"error": "Playlist name must be text."}), 400
        name = name.strip()
        if not name:
            return jsonify({"error": "Playlist name is required."}), 400
        if len(name) > 120:
            return jsonify({"error": "Playlist name is too long."}), 400
        playlist = create_playlist(name, session["user_id"])
        return jsonify({"success": True, "playlist": dict(playlist)})

    @app.post("/api/playlists/<int:playlist_id>/tracks")
    def add_track_to_playlist_endpoint(playlist_id: int):
        requires_login()
        payload = request.get_json(silent=True) or {}
        track_id = payload.get("track_id")
        if not isinstance(track_id, int) or get_track_by_id(track_id) is None:
            return jsonify({"error": "Choose a valid track."}), 400
        user_playlists = get_playlists_for_user(session["user_id"])
        if not any(item["id"] == playlist_id for item in user_playlists):
            abort(404)
        add_track_to_playlist(playlist_id, track_id)
        return jsonify({"success": True})

    @app.post("/api/conversions")
    def submit_conversion():
        requires_login()
        csv_file = request.files.get("csv_file")
        if csv_file is None or not csv_file.filename:
            return jsonify({"error": "Choose a CSV file to convert."}), 400
        content = csv_file.read(app.config["MAX_CONTENT_LENGTH"] + 1)
        if len(content) > app.config["MAX_CONTENT_LENGTH"]:
            return jsonify({"error": "CSV files must be 5 MB or smaller."}), 413
        try:
            mapping = json.loads(request.form.get("mapping", "{}"))
            if not isinstance(mapping, dict) or not all(
                isinstance(key, str) and isinstance(value, str) for key, value in mapping.items()
            ):
                raise ValueError("Column mapping must contain text values.")
            rows = parse_csv(content, mapping)
        except (json.JSONDecodeError, ValueError) as error:
            return jsonify({"error": str(error)}), 400
        if len(rows) > 2000:
            return jsonify({"error": "A conversion job can contain at most 2,000 files."}), 400

        bitrate = request.form.get("bitrate", "192k")
        if bitrate not in BITRATES:
            return jsonify({"error": "Choose a supported MP3 bitrate."}), 400

        folder_name = request.form.get("output_directory", "Converted Files").strip()
        if not folder_name:
            folder_name = "Converted Files"
        if len(folder_name) > 80 or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9 _.()-]*", folder_name):
            return jsonify({"error": "Output folder may contain only letters, numbers, spaces, and -_.()."}), 400

        library_root = Path(get_setting("library_path") or LIBRARY_PATH)
        if not library_root.is_dir():
            return jsonify({"error": "The configured music library folder is unavailable."}), 400
        job_id = uuid.uuid4().hex
        output_root = (DATA_DIR / "converted").resolve()
        output_dir = (output_root / folder_name / job_id).resolve()
        try:
            output_dir.relative_to(output_root)
        except ValueError:
            return jsonify({"error": "Invalid output folder."}), 400

        start_conversion_job(job_id, session["user_id"], rows, library_root, output_dir, bitrate)
        return jsonify({"success": True, "job": {"id": job_id, "status": "queued"}}), 202

    @app.get("/api/conversions")
    def conversions():
        requires_login()
        return jsonify(
            {
                "jobs": [
                    serialize_conversion_job(job)
                    for job in list_conversion_jobs(session["user_id"])
                ]
            }
        )

    @app.get("/api/conversions/<job_id>")
    def conversion_status(job_id: str):
        requires_login()
        job = get_conversion_job(job_id, session["user_id"])
        if job is None:
            abort(404)
        return jsonify({"job": serialize_conversion_job(job)})

    @app.get("/api/conversions/<job_id>/files/<path:filename>")
    def download_conversion_output(job_id: str, filename: str):
        requires_login()
        job = get_conversion_job(job_id, session["user_id"])
        if job is None or filename not in job["outputs"] or Path(filename).name != filename:
            abort(404)
        converted_root = (DATA_DIR / "converted").resolve()
        try:
            output_path = (Path(job["output_dir"]) / filename).resolve(strict=True)
            output_path.relative_to(converted_root)
        except (OSError, ValueError):
            abort(404)
        if not output_path.is_file():
            abort(404)
        return send_file(output_path, as_attachment=True, download_name=filename)

    @app.get("/api/stream/<int:track_id>")
    def stream_track(track_id: int):
        requires_login()
        track = get_track_by_id(track_id)
        if track is None:
            abort(404)
        file_path = Path(track["path"])
        library_root = Path(get_setting("library_path") or LIBRARY_PATH).resolve()
        try:
            file_path = file_path.resolve(strict=True)
            file_path.relative_to(library_root)
        except (OSError, ValueError):
            abort(404)
        if not file_path.is_file():
            abort(404)
        return send_file(file_path, as_attachment=False, conditional=True)

    @app.get("/api/artwork/<int:track_id>")
    def artwork(track_id: int):
        requires_login()
        track = get_track_by_id(track_id)
        if track is None or not track["artwork_path"]:
            abort(404)
        artwork_path = Path(track["artwork_path"])
        try:
            artwork_path = artwork_path.resolve(strict=True)
            artwork_path.relative_to(ARTWORK_DIR.resolve())
        except (OSError, ValueError):
            abort(404)
        if not artwork_path.is_file():
            abort(404)
        return send_file(artwork_path, conditional=True, max_age=3600)

    @app.route("/settings")
    def settings_redirect():
        return app.send_static_file("index.html")

    @app.route("/artists")
    def artists_redirect():
        return app.send_static_file("index.html")

    @app.route("/albums")
    def albums_redirect():
        return app.send_static_file("index.html")

    @app.route("/songs")
    def songs_redirect():
        return app.send_static_file("index.html")

    @app.route("/playlists")
    def playlists_redirect():
        return app.send_static_file("index.html")

    @app.route("/favorites")
    def favorites_redirect():
        return app.send_static_file("index.html")

    @app.route("/search")
    def search_redirect():
        return app.send_static_file("index.html")

    @app.route("/conversions")
    def conversions_redirect():
        return app.send_static_file("index.html")

    return app
