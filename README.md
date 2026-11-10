# middleMusic

middleMusic is a lightweight, self-hosted music streaming app designed for easy setup and day-to-day listening.

## Features

- Quick first-run setup wizard
- Music library scanning for MP3, FLAC, AAC, Ogg Vorbis, WAV, and similar formats
- Browse artists, albums, songs, and playlists
- Search your library
- Play/Pause, queue, shuffle, repeat, and volume controls
- Favorites for tracks and albums
- SQLite-based local storage

## Quick Start

1. Install dependencies:
   ```bash
   python -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   ```
2. Start the server:
   ```bash
   python main.py
   ```
3. Open http://localhost:8080 and complete the setup wizard.
4. Select your music directory and create your admin account.

## Configuration

The app stores configuration in the local `data` directory and uses a default music folder at `./music` unless overridden with environment variables:

- `MIDDLEMUSIC_DATA_DIR`
- `MIDDLEMUSIC_LIBRARY_PATH`

## Development

```bash
python -m unittest discover -s tests
```

## Roadmap

This version is intentionally focused on a complete, usable MVP: setup flow, library scanning, playback, favorites, playlists, and responsive UI.
