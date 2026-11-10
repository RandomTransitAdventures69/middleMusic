import io
import json
import os
import struct
import subprocess
import sys
import tempfile
import time
import unittest
import wave
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch

from mutagen.mp3 import MP3

from middlemusic import create_app, spotify
from middlemusic.converter import analyze_csv, convert_rows, parse_csv


class ConverterTests(unittest.TestCase):
    def test_converter_without_arguments_launches_gui(self):
        project_root = str(Path(__file__).resolve().parents[1])
        converter_script = str(Path(project_root) / "middlemusic" / "converter.py")
        runner = """
import runpy
import sys
from unittest.mock import Mock

sys.path.insert(0, sys.argv[1])
import middlemusic.converter_gui
gui_main = Mock(return_value=None)
middlemusic.converter_gui.main = gui_main
converter_script = sys.argv[2]
sys.argv = [converter_script]
runpy.run_path(converter_script, run_name="__main__")
gui_main.assert_called_once_with()
"""
        with tempfile.TemporaryDirectory() as working_directory:
            result = subprocess.run(
                [
                    sys.executable,
                    "-c",
                    runner,
                    project_root,
                    converter_script,
                ],
                cwd=working_directory,
                capture_output=True,
                text=True,
                check=False,
            )

        self.assertEqual(result.returncode, 0, result.stderr)

    def test_converter_script_runs_as_cli(self):
        converter_script = (
            Path(__file__).resolve().parents[1] / "middlemusic" / "converter.py"
        )
        result = subprocess.run(
            [sys.executable, str(converter_script), "--help"],
            capture_output=True,
            text=True,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("CSV file containing local music paths", result.stdout)

    def test_converter_gui_script_imports_without_package_context(self):
        project_root = Path(__file__).resolve().parents[1]
        gui_script = project_root / "middlemusic" / "converter_gui.py"
        runner = """
import runpy
import sys
runpy.run_path(sys.argv[1], run_name="converter_gui")
"""
        with tempfile.TemporaryDirectory() as working_directory:
            result = subprocess.run(
                [sys.executable, "-c", runner, str(gui_script)],
                cwd=working_directory,
                capture_output=True,
                text=True,
                check=False,
            )

        self.assertEqual(result.returncode, 0, result.stderr)

    def test_auto_detects_common_header_variations(self):
        analysis = analyze_csv(
            b"Audio File;Song Name;Performer;Album Name\n"
            b"album/one.flac;Song One;Artist One;Album One\n"
        )
        rows = analysis.rows

        self.assertEqual(analysis.delimiter, ";")
        self.assertEqual(
            analysis.columns,
            {
                "source": "Audio File",
                "title": "Song Name",
                "artist": "Performer",
                "album": "Album Name",
            },
        )
        self.assertEqual(rows[0]["source"], "album/one.flac")
        self.assertEqual(rows[0]["title"], "Song One")
        self.assertEqual(rows[0]["artist"], "Artist One")

    def test_auto_detects_local_path_column_from_contents(self):
        rows = parse_csv(b"Asset,Song,Performer\nalbum/one.flac,Song One,Artist One\n")

        self.assertEqual(rows[0]["source"], "album/one.flac")
        self.assertEqual(rows[0]["title"], "Song One")
        self.assertEqual(rows[0]["album"], "")

    def test_headerless_single_column_file_list_is_supported(self):
        rows = parse_csv(b"album/one.flac\nalbum/two.mp3\n")

        self.assertEqual(
            [row["source"] for row in rows],
            [
                "album/one.flac",
                "album/two.mp3",
            ],
        )

    def test_ambiguous_audio_path_columns_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "multiple possible audio path columns"):
            parse_csv(
                b"File Path,Audio File,Title\nalbum/one.flac,album/two.mp3,Song One\n"
            )

    def test_audio_path_contents_resolve_duplicate_path_headers(self):
        rows = parse_csv(b"File Path,Audio File,Title\n,album/one.flac,Song One\n")

        self.assertEqual(rows[0]["source"], "album/one.flac")

    def test_populated_metadata_alias_wins_over_empty_alias(self):
        rows = parse_csv(b"File Path,Title,Song Name\nalbum/one.flac,,Song One\n")

        self.assertEqual(rows[0]["title"], "Song One")

    def test_headerless_multicolumn_csv_is_rejected_as_ambiguous(self):
        with self.assertRaisesRegex(ValueError, "columns are ambiguous"):
            parse_csv(b"album/one.flac,Song One,Artist One\n")

    def test_optional_metadata_columns_can_be_absent(self):
        rows = parse_csv(b"file_path\nalbum/one.flac\n")

        self.assertEqual(rows[0]["source"], "album/one.flac")
        self.assertEqual(rows[0]["album"], "")

    def test_ignores_blank_export_columns(self):
        rows = parse_csv(b"file_path,title,,\nalbum/one.flac,Song One,,\n")

        self.assertEqual(rows[0]["source"], "album/one.flac")
        self.assertEqual(rows[0]["title"], "Song One")

    def test_track_column_contents_distinguish_title_from_track_number(self):
        numbered = parse_csv(b"Path,Track\nalbum/one.flac,3/12\n")
        titled = parse_csv(b"Path,Track\nalbum/one.flac,Song One\n")

        self.assertEqual(numbered[0]["track_number"], "3/12")
        self.assertEqual(numbered[0]["title"], "")
        self.assertEqual(titled[0]["title"], "Song One")

    def test_spotify_export_track_uri_and_id_are_auto_detected(self):
        track_id = "1" * 22
        rows = parse_csv(
            (
                "Filename,Track Name,Artist Name(s),Album Name,Track URI,Track ID\n"
                f"album/one.flac,Song One,Artist One,Album One,"
                f"spotify:track:{track_id},{track_id}\n"
            ).encode()
        )

        self.assertEqual(rows[0]["source"], "album/one.flac")
        self.assertEqual(rows[0]["title"], "Song One")
        self.assertEqual(rows[0]["artist"], "Artist One")
        self.assertEqual(rows[0]["spotify_track_id"], track_id)

    def test_remote_audio_csv_is_rejected_with_clear_error(self):
        with self.assertRaisesRegex(ValueError, "Remote audio URLs are not supported"):
            parse_csv(b"source,title\nhttps://example.invalid/audio.mp3,Song\n")

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
        with ExitStack() as stack:
            stack.enter_context(
                patch.dict(
                    os.environ,
                    {"SPOTIFY_CLIENT_ID": "id", "SPOTIFY_CLIENT_SECRET": "secret"},
                )
            )
            stack.enter_context(patch.object(spotify, "_cached_token", None))
            stack.enter_context(patch.object(spotify, "_token_expires_at", 0))
            stack.enter_context(
                patch.object(
                    spotify,
                    "urlopen",
                    side_effect=[token_response, track_response],
                )
            )
            metadata = spotify.get_track_metadata(
                f"https://open.spotify.com/track/{track_id}?si=example"
            )

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

            with ExitStack() as stack:
                stack.enter_context(
                    patch("middlemusic.database.DB_PATH", root / "test.db")
                )
                stack.enter_context(patch("middlemusic.app.DATA_DIR", data_dir))
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
                preview = client.post(
                    "/api/conversions/preview",
                    data={
                        "csv_file": (
                            io.BytesIO(
                                b"path,Title,Artist\nweb-test.wav,Web Test,Test Artist\n"
                            ),
                            "tracks.csv",
                        )
                    },
                    content_type="multipart/form-data",
                )
                self.assertEqual(preview.status_code, 200)
                self.assertEqual(preview.get_json()["total"], 1)
                self.assertEqual(
                    preview.get_json()["detected_columns"]["source"], "path"
                )
                response = client.post(
                    "/api/conversions",
                    data={
                        "csv_file": (
                            io.BytesIO(
                                b"path,Title,Artist\nweb-test.wav,Web Test,Test Artist\n"
                            ),
                            "tracks.csv",
                        ),
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
