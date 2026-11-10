import unittest
from pathlib import Path
import tempfile
from unittest.mock import patch

from middlemusic.database import init_db, get_setting, set_setting, count_rows
from middlemusic.config import DATA_DIR
from middlemusic import create_app


class BasicAppTests(unittest.TestCase):
    def test_db_initializes_and_settings_round_trip(self):
        init_db()
        set_setting("server_name", "Test Music")
        self.assertEqual(get_setting("server_name"), "Test Music")
        self.assertGreaterEqual(count_rows("settings"), 1)

    def test_data_directory_exists(self):
        self.assertTrue(Path(DATA_DIR).exists())

    def test_public_health_and_protected_library(self):
        client = create_app().test_client()
        self.assertEqual(client.get("/api/health").status_code, 200)
        self.assertEqual(client.get("/api/tracks").status_code, 401)

    def test_setup_creates_authenticated_admin(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            library = root / "music"
            library.mkdir()
            with patch("middlemusic.database.DB_PATH", root / "test.db"):
                client = create_app().test_client()
                response = client.post(
                    "/api/setup",
                    json={
                        "username": "admin",
                        "password": "a-strong-password",
                        "library_path": str(library),
                        "server_name": "Test server",
                    },
                )
                self.assertEqual(response.status_code, 200)
                stats = client.get("/api/library/stats").get_json()
                self.assertEqual(stats["server_name"], "Test server")
                self.assertEqual(client.post("/api/library/scan").status_code, 200)


if __name__ == "__main__":
    unittest.main()
