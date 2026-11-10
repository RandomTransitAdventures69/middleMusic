import struct
import tempfile
import unittest
import wave
from pathlib import Path

from mutagen.mp3 import MP3

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


if __name__ == "__main__":
    unittest.main()
