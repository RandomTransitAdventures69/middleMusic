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
- Native Tk desktop converter and CLI using the same conversion engine
- Mobile-friendly job import, monitoring, and downloads in a browser
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

For a desktop session that starts a local server and opens the GUI automatically:

```bash
python -m middlemusic.gui
```

## Configuration

The app stores configuration in the local `data` directory and uses a default music folder at `./music` unless overridden with environment variables:

- `MIDDLEMUSIC_DATA_DIR`
- `MIDDLEMUSIC_LIBRARY_PATH`

## Convert a CSV of local music

Launch the native Tk desktop converter with:

```bash
python -m middlemusic.converter
```

Or run `python middlemusic/converter.py` directly. Choose a CSV, music library, and output folder; the app automatically detects and previews the CSV before you confirm. Then select an MP3 bitrate. It shows conversion progress and per-file errors, and requires a Python installation with Tk support.

The web interface also has a **Converter** page that automatically analyzes and previews an uploaded CSV before conversion. Paths in the CSV must refer to audio files already on the server, relative to the configured music library. The mobile-friendly interface can upload a CSV, track job progress, and download finished files. Audio URLs and audio downloads are not supported.

To look up optional Spotify metadata by track ID or `open.spotify.com/track/...` URL, configure a Spotify developer application and set `SPOTIFY_CLIENT_ID` and `SPOTIFY_CLIENT_SECRET` in the server or CLI environment. The local audio file is still required; Spotify is used only for track metadata.

Example CSV:

```csv
source,title,artist,album
albums/record-one.flac,Record One,Example Artist,Example Album
albums/record-two.wav,Record Two,Example Artist,Example Album
```

The same conversion engine is available from the command line:

```bash
python -m middlemusic.cli playlist.csv \
  --library ./music \
  --output ./converted \
  --bitrate 192k
```

The CSV detector recognizes common names for local file paths, titles, artists, albums, and optional metadata. Missing optional columns are ignored; ambiguous or unsupported formats produce a specific error. Headerless single-column lists of audio files are supported. Supported bitrates are 128, 192, 256, and 320 kbps. FFmpeg is bundled through the Python dependency when no system FFmpeg is available. Remote audio URLs and audio downloads are not supported.


## holy fuck copilot is good at coding (compared to kilo code)
