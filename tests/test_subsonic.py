import hashlib
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.parse import urlencode

from middlemusic import create_app
from middlemusic.database import upsert_track


class SubsonicApiTests(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name)
        self.library = self.root / "music"
        self.library.mkdir()
        self.db_patcher = patch("middlemusic.database.DB_PATH", self.root / "test.db")
        self.db_patcher.start()
        self.client = create_app().test_client()
        self.password = "a-strong-password"
        self.client.post(
            "/api/setup",
            json={
                "username": "listener",
                "password": self.password,
                "library_path": str(self.library),
                "server_name": "Test",
            },
        )
        self.audio_path = self.library / "song.wav"
        self.audio_path.write_bytes(b"RIFF" + b"\x00" * 36 + b"data" + b"\x00" * 8)
        upsert_track(
            {
                "path": str(self.audio_path),
                "title": "Nagila",
                "artist": "Example Artist",
                "album": "Example Album",
                "album_artist": "Example Artist",
                "genre": "Folk",
                "duration": 12,
                "track_number": 1,
                "year": 2024,
            }
        )
        self.track_id = "1"

    def tearDown(self):
        self.db_patcher.stop()
        self.temporary_directory.cleanup()

    def request_api(self, method, **params):
        salt = "test-salt"
        token = hashlib.md5(f"{self.password}{salt}".encode()).hexdigest()
        query = {
            "u": "listener",
            "t": token,
            "s": salt,
            "v": "1.16.1",
            "c": "test",
            "f": "json",
            **params,
        }
        return self.client.get(f"/rest/{method}.view?{urlencode(query)}")

    def test_ping_accepts_subsonic_token_authentication(self):
        response = self.request_api("ping")
        self.assertEqual(response.status_code, 200)
        payload = response.get_json()["subsonic-response"]
        self.assertEqual(payload["status"], "ok")
        self.assertTrue(payload["openSubsonic"])

    def test_music_browsing_streaming_and_favorites(self):
        albums = self.request_api("getAlbumList2", type="alphabeticalByName")
        album = albums.get_json()["subsonic-response"]["albumList2"]["album"][0]
        directory = self.request_api("getMusicDirectory", id=album["id"])
        song = directory.get_json()["subsonic-response"]["directory"]["child"][0]
        self.assertEqual(song["title"], "Nagila")

        streamed = self.request_api("stream", id=self.track_id)
        self.assertEqual(streamed.status_code, 200)
        self.assertIn(b"RIFF", streamed.data)

        self.assertEqual(self.request_api("star", id=self.track_id).status_code, 200)
        starred = self.request_api("getStarred2")
        self.assertEqual(
            starred.get_json()["subsonic-response"]["starred2"]["song"][0]["id"],
            self.track_id,
        )
        self.assertEqual(self.request_api("unstar", id=self.track_id).status_code, 200)

    def test_api_returns_clear_errors_for_auth_and_bad_ids(self):
        denied = self.client.get("/rest/ping.view?u=listener&t=bad&s=salt&f=json")
        self.assertEqual(
            denied.get_json()["subsonic-response"]["error"]["code"], 10
        )
        invalid = self.request_api("getMusicDirectory", id="not-a-directory")
        self.assertEqual(
            invalid.get_json()["subsonic-response"]["status"], "failed"
        )


if __name__ == "__main__":
    unittest.main()
