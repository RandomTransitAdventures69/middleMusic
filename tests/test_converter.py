import io
import json
import os
import struct
import tempfile
import time
import unittest
import wave
from pathlib import Path
from unittest.mock import patch

from mutagen.mp3 import MP3

from middlemusic import create_app, spotify
from middlemusic.converter import convert_rows, parse_csv


class ConverterTests(unittest.TestCase):
    def test_csv_column_mapping(self):
        rows = parse_csv(
            b"File,Song,Performer\nalbum/one.flac,Song One,Artist One\n",
            {"source": "File", "title": "Song", "artist": "Performer"},
        )
        self.assertEqual(rows[0]["source"], "album/one.flac")
        self.assertEqual(rows[0]["title"], "Song One")
        self.assertEqual(rows[0]["artist"], "Artist One")

    def test_converts_local_wav_and_tags_output(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            library = root / "library"
            library.mkdir()
            source = library / "tone.wav"
            with wave.open(str(source), "wb") as audio_file:
                audio_file.setnchannels(1)
                audio_file.setsampwidth(2)
                audio_file.setframerate(22050)
                audio_file.writeframes(struct.pack("<h", 0) * 22050)

            rows = [
                {
                    "line_number": "2",
                    "source": "tone.wav",
                    "title": "Test Tone",
                    "artist": "middleMusic",
                    "album": "Converter Test",
                }
            ]
            outputs, errors = convert_rows(rows, library, root / "output", "128k")

            self.assertEqual(errors, [])
            self.assertEqual(len(outputs), 1)
            result = MP3(root / "output" / outputs[0])
            self.assertEqual(str(result.tags["TIT2"]), "Test Tone")
            self.assertEqual(str(result.tags["TPE1"]), "middleMusic")

    def test_rejects_remote_sources(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            outputs, errors = convert_rows(
                [{"source": "https://example.invalid/audio.mp3", "line_number": "2"}],
                root,
                root / "output",
            )
            self.assertEqual(outputs, [])
            self.assertIn("Remote audio URLs are not supported", errors[0]["message"])

    def test_rejects_paths_outside_the_library(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            library = root / "library"
            library.mkdir()
            outside_file = root / "outside.wav"
            outside_file.touch()
            outputs, errors = convert_rows(
                [{"source": "../outside.wav", "line_number": "2"}],
                library,
                root / "output",
            )
            self.assertEqual(outputs, [])
            self.assertEqual(len(errors), 1)
            self.assertEqual(errors[0]["line_number"], "2")

    def test_spotify_metadata_lookup_uses_track_metadata_only(self):
        track_id = "1" * 22
        token_response = io.BytesIO(b'{"access_token":"test-token","expires_in":3600}')
        track_response = io.BytesIO(
            json.dumps(
                {
                    "name": "Song",
                    "artists": [{"name": "Artist"}],
                    "track_number": 4,
                    "album": {
                        "name": "Album",
                        "release_date": "2020-05-01",
                        "artists": [{"name": "Album Artist"}],
                    },
                }
            ).encode()
        )
        with (
            patch.dict(os.environ, {"SPOTIFY_CLIENT_ID": "id", "SPOTIFY_CLIENT_SECRET": "secret"}),
            patch.object(spotify, "_cached_token", None),
            patch.object(spotify, "_token_expires_at", 0),
            patch.object(spotify, "urlopen", side_effect=[token_response, track_response]),
        ):
            metadata = spotify.get_track_metadata(f"https://open.spotify.com/track/{track_id}?si=example")

        self.assertEqual(metadata["title"], "Song")
        self.assertEqual(metadata["artist"], "Artist")
        self.assertEqual(metadata["album"], "Album")
        self.assertEqual(metadata["year"], "2020")

    def test_authenticated_web_conversion_job(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            library = root / "library"
            library.mkdir()
            data_dir = root / "data"
            data_dir.mkdir()
            source = library / "web-test.wav"
            with wave.open(str(source), "wb") as audio_file:
                audio_file.setnchannels(1)
                audio_file.setsampwidth(2)
                audio_file.setframerate(22050)
                audio_file.writeframes(struct.pack("<h", 0) * 22050)

            with (
                patch("middlemusic.database.DB_PATH", root / "test.db"),
                patch("middlemusic.app.DATA_DIR", data_dir),
            ):
                client = create_app().test_client()
                setup = client.post(
                    "/api/setup",
                    json={
                        "username": "admin",
                        "password": "a-strong-password",
                        "library_path": str(library),
                        "server_name": "Converter Test",
                    },
                )
                self.assertEqual(setup.status_code, 200)
                response = client.post(
                    "/api/conversions",
                    data={
                        "csv_file": (io.BytesIO(b"path,Title,Artist\nweb-test.wav,Web Test,Test Artist\n"), "tracks.csv"),
                        "mapping": json.dumps({"source": "path", "title": "Title", "artist": "Artist"}),
                        "bitrate": "128k",
                        "output_directory": "Web Tests",
                    },
                    content_type="multipart/form-data",
                )
                self.assertEqual(response.status_code, 202)
                job_id = response.get_json()["job"]["id"]

                deadline = time.monotonic() + 10
                job = None
                while time.monotonic() < deadline:
                    job = client.get(f"/api/conversions/{job_id}").get_json()["job"]
                    if job["status"] not in {"queued", "running"}:
                        break
                    time.sleep(0.05)

                self.assertEqual(job["status"], "completed")
                self.assertEqual(len(job["outputs"]), 1)
                download = client.get(job["outputs"][0]["url"])
                self.assertEqual(download.status_code, 200)
                download.close()


if __name__ == "__main__":
    unittest.main()
