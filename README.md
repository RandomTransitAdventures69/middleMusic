# middleMusic

middleMusic is a lightweight, self-hosted music streaming app designed for easy setup and day-to-day listening.

## Features

- Quick first-run setup wizard
- Music library scanning for MP3, FLAC, AAC, Ogg Vorbis, WAV, and similar formats
- Browse artists, albums, songs, and playlists
- Search your library
- Play/Pause, queue, shuffle, repeat, and volume controls
- Favorites for tracks and albums
- Web-based CSV-to-MP3 conversion with progress and downloadable results
- CLI conversion using the same engine as the web interface
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

## Convert a CSV of local music

Open **Converter** in the web interface to upload a CSV, map its columns, choose an MP3 bitrate, and monitor the job. Paths in the CSV must refer to audio files already on the server, relative to the configured music library. Converted files are saved under `data/converted`.

The same conversion engine is available from the command line:

```bash
python -m middlemusic.cli playlist.csv \
  --library ./music \
  --output ./converted \
  --source-column path \
  --title-column Title \
  --artist-column Artist \
  --album-column Album \
  --bitrate 192k
```

`source` is the default source-column heading. Optional metadata mappings include `album-artist`, `genre`, `track-number`, and `year`. Supported bitrates are 128, 192, 256, and 320 kbps. FFmpeg is bundled through the Python dependency when no system FFmpeg is available. Remote audio URLs and audio downloads are not supported.


## holy fuck copilot is good at coding (compared to kilo code)
