from __future__ import annotations

import hashlib
import json
import secrets
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit, urlunsplit
from urllib.request import urlopen


class SubsonicService:
    def __init__(self, server_url: str, username: str, password: str):
        parts = urlsplit(server_url.strip())
        if parts.scheme not in {"http", "https"} or not parts.netloc:
            raise ValueError("Enter a valid server URL, including http:// or https://.")
        path = parts.path.rstrip("/")
        path = path.removesuffix("/rest")
        self.api_root = urlunsplit((parts.scheme, parts.netloc, path, "", ""))
        self.username = username
        self.password = password

    def _auth_params(self) -> dict[str, str]:
        salt = secrets.token_hex(12)
        token = hashlib.md5(f"{self.password}{salt}".encode()).hexdigest()
        return {
            "u": self.username,
            "t": token,
            "s": salt,
            "v": "1.16.1",
            "c": "middleMusic",
            "f": "json",
        }

    def request(self, method: str, **params):
        query = self._auth_params()
        query.update({key: str(value) for key, value in params.items() if value is not None})
        url = f"{self.api_root}/rest/{method}.view?{urlencode(query)}"
        try:
            with urlopen(url, timeout=15) as response:
                body = json.loads(response.read().decode("utf-8"))
        except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as error:
            raise RuntimeError(f"Could not contact the music server: {error}") from error
        result = body.get("subsonic-response", {})
        if result.get("status") != "ok":
            error = result.get("error", {})
            raise RuntimeError(error.get("message", "The server rejected the request."))
        return result

    def stream_url(self, track_id: str) -> str:
        params = self._auth_params()
        params["id"] = track_id
        return f"{self.api_root}/rest/stream.view?{urlencode(params)}"


def main() -> int:
    try:
        from PySide6.QtCore import QUrl
        from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
        from PySide6.QtWidgets import (
            QApplication,
            QFormLayout,
            QHBoxLayout,
            QHeaderView,
            QLineEdit,
            QMainWindow,
            QMessageBox,
            QPushButton,
            QTableWidget,
            QTableWidgetItem,
            QVBoxLayout,
            QWidget,
        )
    except ImportError as error:
        raise SystemExit(
            "The desktop client requires PySide6. Install it with: "
            "pip install 'middlemusic[client]'"
        ) from error

    class MusicWindow(QMainWindow):
        def __init__(self):
            super().__init__()
            self.setWindowTitle("middleMusic")
            self.resize(1100, 720)
            self.service = None
            self.tracks = []
            self.audio_output = QAudioOutput(self)
            self.player = QMediaPlayer(self)
            self.player.setAudioOutput(self.audio_output)

            root = QWidget()
            layout = QVBoxLayout(root)
            login = QFormLayout()
            self.server = QLineEdit("http://localhost:8080")
            self.username = QLineEdit()
            self.password = QLineEdit()
            self.password.setEchoMode(QLineEdit.EchoMode.Password)
            login.addRow("Server", self.server)
            login.addRow("Username", self.username)
            login.addRow("Password", self.password)
            layout.addLayout(login)

            controls = QHBoxLayout()
            self.connect_button = QPushButton("Connect")
            self.connect_button.clicked.connect(self.connect_server)
            controls.addWidget(self.connect_button)
            self.search = QLineEdit()
            self.search.setPlaceholderText("Search songs")
            self.search.returnPressed.connect(self.search_songs)
            controls.addWidget(self.search, 1)
            search_button = QPushButton("Search")
            search_button.clicked.connect(self.search_songs)
            controls.addWidget(search_button)
            layout.addLayout(controls)

            self.table = QTableWidget(0, 4)
            self.table.setHorizontalHeaderLabels(["Title", "Artist", "Album", "Year"])
            self.table.horizontalHeader().setSectionResizeMode(
                0, QHeaderView.ResizeMode.Stretch
            )
            self.table.horizontalHeader().setSectionResizeMode(
                1, QHeaderView.ResizeMode.ResizeToContents
            )
            self.table.horizontalHeader().setSectionResizeMode(
                2, QHeaderView.ResizeMode.ResizeToContents
            )
            self.table.cellDoubleClicked.connect(self.play_selected)
            layout.addWidget(self.table, 1)

            playback = QHBoxLayout()
            play_button = QPushButton("Play selected")
            play_button.clicked.connect(self.play_selected)
            playback.addWidget(play_button)
            favorite_button = QPushButton("Toggle favorite")
            favorite_button.clicked.connect(self.toggle_favorite)
            playback.addWidget(favorite_button)
            playlist_button = QPushButton("Create playlist with selected song")
            playlist_button.clicked.connect(self.create_playlist)
            playback.addWidget(playlist_button)
            self.now_playing = QLineEdit()
            self.now_playing.setReadOnly(True)
            self.now_playing.setPlaceholderText("Nothing playing")
            playback.addWidget(self.now_playing, 1)
            layout.addLayout(playback)
            self.setCentralWidget(root)
            self.statusBar().showMessage("Connect to your middleMusic server.")

        def report_error(self, error):
            QMessageBox.critical(self, "middleMusic", str(error))

        def connect_server(self):
            try:
                self.service = SubsonicService(
                    self.server.text(), self.username.text().strip(), self.password.text()
                )
                self.service.request("ping")
                self.load_albums()
                self.statusBar().showMessage("Connected.")
            except (ValueError, RuntimeError) as error:
                self.service = None
                self.report_error(error)

        def load_albums(self):
            result = self.service.request("getAlbumList2", type="alphabeticalByName", size=500)
            albums = result.get("albumList2", {}).get("album", [])
            tracks = []
            for album in albums:
                details = self.service.request("getMusicDirectory", id=album["id"])
                tracks.extend(details.get("directory", {}).get("child", []))
            self.show_tracks(tracks)

        def search_songs(self):
            if not self.service:
                self.statusBar().showMessage("Connect to a server first.")
                return
            try:
                query = self.search.text().strip()
                result = self.service.request(
                    "search3", query=query, songCount=500, songOffset=0
                )
                self.show_tracks(result.get("searchResult3", {}).get("song", []))
            except RuntimeError as error:
                self.report_error(error)

        def show_tracks(self, tracks):
            self.tracks = tracks
            self.table.setRowCount(len(tracks))
            for row, track in enumerate(tracks):
                values = [
                    track.get("title", ""),
                    track.get("artist", ""),
                    track.get("album", ""),
                    str(track.get("year") or ""),
                ]
                for column, value in enumerate(values):
                    self.table.setItem(row, column, QTableWidgetItem(value))
            self.statusBar().showMessage(f"{len(tracks)} songs")

        def selected_track(self):
            row = self.table.currentRow()
            return self.tracks[row] if 0 <= row < len(self.tracks) else None

        def play_selected(self, *_):
            track = self.selected_track()
            if not self.service or not track:
                return
            self.player.setSource(QUrl(self.service.stream_url(track["id"])))
            self.player.play()
            album_details = " - ".join(
                part for part in (track.get("artist"), track.get("album")) if part
            )
            self.now_playing.setText(
                f"{track.get('title', 'Unknown title')} — {album_details}"
            )

        def toggle_favorite(self):
            track = self.selected_track()
            if not self.service or not track:
                return
            try:
                self.service.request("star", id=track["id"])
                self.statusBar().showMessage(f"Added {track.get('title', 'song')} to favorites.")
            except RuntimeError as error:
                self.report_error(error)

        def create_playlist(self):
            track = self.selected_track()
            if not self.service or not track:
                return
            name, accepted = QInputDialog.getText(self, "New playlist", "Playlist name")
            if not accepted:
                return
            try:
                self.service.request(
                    "createPlaylist", name=name.strip(), songId=track["id"]
                )
                self.statusBar().showMessage("Playlist created.")
            except RuntimeError as error:
                self.report_error(error)

    from PySide6.QtWidgets import QInputDialog

    application = QApplication.instance() or QApplication([])
    window = MusicWindow()
    window.show()
    return application.exec()


if __name__ == "__main__":
    raise SystemExit(main())
