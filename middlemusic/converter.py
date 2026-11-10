from __future__ import annotations

import csv
import io
import re
import shutil
import subprocess
import sys
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

if __package__:
    from .scanner import AUDIO_EXTENSIONS, extract_metadata
    from .spotify import get_track_metadata as get_spotify_metadata
else:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from middlemusic.scanner import AUDIO_EXTENSIONS, extract_metadata
    from middlemusic.spotify import get_track_metadata as get_spotify_metadata

BITRATES = {"128k", "192k", "256k", "320k"}
CSV_FIELDS = (
    "source",
    "title",
    "artist",
    "album",
    "album_artist",
    "genre",
    "track_number",
    "year",
    "spotify_track_id",
)
FIELD_ALIASES = {
    "source": {
        "audio",
        "audio_file",
        "audio_file_path",
        "audio_filename",
        "audio_path",
        "file",
        "file_location",
        "file_name",
        "file_path",
        "filename_with_path",
        "filename",
        "filepath",
        "full_path",
        "local_file",
        "local_filename",
        "local_path",
        "location",
        "music_file",
        "path",
        "relative_path",
        "recording_path",
        "song_file",
        "song_path",
        "source",
        "source_file",
        "source_path",
        "track_file",
        "track_filename",
        "track_path",
    },
    "title": {
        "name",
        "song",
        "song_name",
        "song_title",
        "title",
        "track_name",
        "track_title",
    },
    "artist": {
        "artist",
        "artist_name",
        "artist_names",
        "artist_name_s",
        "artist_s",
        "artists",
        "performer",
        "performers",
        "singer",
        "singers",
        "track_artist",
    },
    "album": {
        "album",
        "album_name",
        "album_title",
        "release",
        "release_name",
        "record",
    },
    "album_artist": {
        "albumartist",
        "album_artist",
        "album_artist_name",
        "album_artist_names",
        "album_artist_name_s",
        "album_artist_s",
    },
    "genre": {"genre", "genres", "style"},
    "track_number": {
        "track_no",
        "track_num",
        "track_number",
        "track_number_total",
        "track_index",
        "tracknumber",
    },
    "year": {"date", "release_date", "release_year", "year", "year_released"},
    "spotify_track_id": {
        "spotify_id",
        "spotify_track_id",
        "spotify_uri",
        "spotify_url",
        "track_id",
        "track_uri",
    },
}
_AUDIO_URL = re.compile(r"^[A-Za-z][A-Za-z0-9+.-]*://")
_TRACK_NUMBER = re.compile(r"^\d+(?:\s*/\s*\d+|\s+of\s+\d+)?$", re.IGNORECASE)


@dataclass
class CsvAnalysis:
    rows: list[dict[str, str]]
    columns: dict[str, str]
    delimiter: str
    has_header: bool


def _normalize_header(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", value.strip().casefold()).strip("_")


def _field_for_header(header: str, values: list[str]) -> str | None:
    normalized = _normalize_header(header)
    if normalized == "track":
        nonempty_values = [value.strip() for value in values if value.strip()]
        if nonempty_values and all(
            _TRACK_NUMBER.fullmatch(value) for value in nonempty_values
        ):
            return "track_number"
        return "title"
    return next(
        (field for field, aliases in FIELD_ALIASES.items() if normalized in aliases),
        None,
    )


def _looks_like_audio_path(value: str) -> bool:
    value = value.strip()
    return (
        bool(value)
        and not _AUDIO_URL.match(value)
        and Path(value).suffix.lower() in AUDIO_EXTENSIONS
    )


def _normalize_field_value(field: str, value: str) -> str:
    value = value.strip()
    if field != "spotify_track_id":
        return value
    spotify_uri = re.fullmatch(r"spotify:track:([A-Za-z0-9]+)", value)
    if spotify_uri:
        return spotify_uri.group(1)
    spotify_url = re.match(
        r"https?://(?:www\.)?open\.spotify\.com/track/([^/?#]+)",
        value,
        re.IGNORECASE,
    )
    return spotify_url.group(1) if spotify_url else value


def _choose_source_column(
    headers: list[str], records: list[list[str]]
) -> tuple[int, str]:
    explicit = [
        index
        for index, header in enumerate(headers)
        if _field_for_header(header, []) == "source"
    ]
    if len(explicit) == 1:
        return explicit[0], headers[explicit[0]]
    if len(explicit) > 1:
        path_scores = []
        for index in explicit:
            values = [row[index].strip() for row in records if index < len(row)]
            populated = [value for value in values if value]
            score = (
                sum(_looks_like_audio_path(value) for value in populated)
                / len(populated)
                if populated
                else 0
            )
            path_scores.append((score, index, values))
        highest_score = max(score for score, _, _ in path_scores)
        winners = [
            (index, values)
            for score, index, values in path_scores
            if score == highest_score
        ]
        if highest_score >= 0.6 and len(winners) == 1:
            index = winners[0][0]
            return index, headers[index]
        if len({tuple(values) for _, values in winners}) == 1:
            index = winners[0][0]
            return index, headers[index]
        names = ", ".join(repr(headers[index]) for index in explicit)
        raise ValueError(f"CSV has multiple possible audio path columns: {names}.")

    candidates = []
    for index in range(len(headers)):
        values = [row[index].strip() for row in records if index < len(row)]
        populated = [value for value in values if value]
        if populated:
            path_count = sum(_looks_like_audio_path(value) for value in populated)
            if path_count / len(populated) >= 0.6:
                candidates.append(index)
    if len(candidates) == 1:
        index = candidates[0]
        return index, headers[index] or "Detected local file paths"
    if len(candidates) > 1:
        names = ", ".join(repr(headers[index]) for index in candidates)
        raise ValueError(f"CSV has ambiguous audio path columns: {names}.")
    raise ValueError(
        "Could not identify a local audio file path column. Include a column such as "
        "'source', 'path', 'file', or 'filename'; remote audio URLs are not supported."
    )


def analyze_csv(content: bytes) -> CsvAnalysis:
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError as error:
        raise ValueError("CSV file must use UTF-8 encoding.") from error

    sample = text[:8192]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t|")
    except csv.Error:
        dialect = csv.excel

    try:
        records = [
            [cell.strip() for cell in row]
            for row in csv.reader(io.StringIO(text), dialect)
            if any(cell.strip() for cell in row)
        ]
    except csv.Error as error:
        raise ValueError(f"CSV is malformed: {error}") from error
    if not records:
        raise ValueError("CSV is empty.")

    first_row = records[0]
    first_fields = [_field_for_header(header, []) for header in first_row]
    has_header = any(field is not None for field in first_fields)

    if not has_header:
        if first_row and _AUDIO_URL.match(first_row[0]):
            raise ValueError(
                "Remote audio URLs are not supported; the CSV must contain local "
                "music-library file paths."
            )
        if len(first_row) != 1 or not _looks_like_audio_path(first_row[0]):
            raise ValueError(
                "The CSV has no recognizable header row and its columns are "
                "ambiguous. Add headings such as 'path', 'title', and 'artist'."
            )
        headers = ["First column (no header)"]
        data_records = records
        source_index = 0
        columns = {"source": headers[0]}
    else:
        headers = first_row
        data_records = records[1:]
        normalized_headers = [
            normalized
            for header in headers
            if (normalized := _normalize_header(header))
        ]
        if len(set(normalized_headers)) != len(normalized_headers):
            raise ValueError("CSV has duplicate column names; rename them and retry.")

        source_index, source_header = _choose_source_column(headers, data_records)
        columns = {"source": source_header}
        candidates: dict[str, list[int]] = {}
        for index, header in enumerate(headers):
            if index == source_index:
                continue
            values = [row[index] for row in data_records if index < len(row)]
            field = _field_for_header(header, values)
            if field is not None:
                candidates.setdefault(field, []).append(index)

        for field, indexes in candidates.items():
            populated = [
                index
                for index in indexes
                if any(index < len(row) and row[index].strip() for row in data_records)
            ]
            if len(populated) == 1:
                selected = populated[0]
            elif len(populated) > 1:
                value_sets = {
                    tuple(
                        _normalize_field_value(
                            field, row[index] if index < len(row) else ""
                        )
                        for row in data_records
                    )
                    for index in populated
                }
                if len(value_sets) == 1:
                    selected = populated[0]
                else:
                    names = ", ".join(repr(headers[index]) for index in populated)
                    raise ValueError(
                        f"CSV has multiple columns that could contain "
                        f"{field.replace('_', ' ')} data: {names}."
                    )
            else:
                selected = indexes[0]
            columns[field] = headers[selected]

    field_indexes = {
        field: next(
            (index for index, header in enumerate(headers) if header == columns[field]),
            0 if field == "source" and not has_header else -1,
        )
        for field in columns
    }

    rows = []
    for record_index, record in enumerate(data_records):
        line_number = record_index + (2 if has_header else 1)
        if len(record) > len(headers) and any(record[len(headers) :]):
            raise ValueError(f"CSV row {line_number} has more fields than its header.")
        values = record[: len(headers)] + [""] * max(0, len(headers) - len(record))
        source = values[source_index].strip()
        if not source:
            continue
        if _AUDIO_URL.match(source):
            raise ValueError(
                f"CSV row {line_number}: Remote audio URLs are not supported; "
                "only local music-library files are accepted."
            )
        rows.append(
            {
                "line_number": str(line_number),
                **{
                    field: _normalize_field_value(
                        field,
                        values[field_indexes[field]]
                        if field in field_indexes and field_indexes[field] >= 0
                        else "",
                    )
                    for field in CSV_FIELDS[1:]
                },
                "source": source,
            }
        )
    if not rows:
        raise ValueError("CSV contains no rows with a source file.")
    return CsvAnalysis(rows, columns, dialect.delimiter, has_header)


def parse_csv(content: bytes) -> list[dict[str, str]]:
    return analyze_csv(content).rows


def _ffmpeg_executable() -> str:
    executable = shutil.which("ffmpeg")
    if executable:
        return executable
    try:
        import imageio_ffmpeg
    except ImportError as error:
        raise RuntimeError(
            "FFmpeg is unavailable. Reinstall middleMusic dependencies."
        ) from error
    executable = imageio_ffmpeg.get_ffmpeg_exe()
    if Path(executable).is_file() or shutil.which(executable):
        return executable
    raise RuntimeError("Bundled FFmpeg executable is unavailable.")


def _resolve_source(source_value: str, library_root: Path) -> Path:
    if re.match(r"^[A-Za-z][A-Za-z0-9+.-]*://", source_value):
        raise ValueError(
            "Remote audio URLs are not supported; use a local library file."
        )

    root = library_root.resolve(strict=True)
    candidate = Path(source_value)
    if not candidate.is_absolute():
        candidate = root / candidate
    source = candidate.resolve(strict=True)
    source.relative_to(root)
    if not source.is_file():
        raise ValueError("Source is not a file.")
    if source.suffix.lower() not in AUDIO_EXTENSIONS:
        raise ValueError(f"Unsupported audio format: {source.suffix or 'unknown'}.")
    return source


def _safe_filename(value: str) -> str:
    cleaned = re.sub(r'[<>:"/\\|?*]', "_", value)
    cleaned = re.sub(r"[\x00-\x1f]", "_", cleaned).strip(" .")
    return cleaned[:160] or "untitled"


def _output_path(metadata: dict[str, object], source: Path, output_dir: Path) -> Path:
    title = str(metadata.get("title") or source.stem)
    artist = str(metadata.get("artist") or "")
    filename = _safe_filename(f"{artist} - {title}" if artist else title) + ".mp3"
    output = output_dir / filename
    suffix = 2
    while output.exists():
        output = output_dir / f"{Path(filename).stem} ({suffix}).mp3"
        suffix += 1
    return output


def _transcode(
    source: Path,
    output: Path,
    metadata: dict[str, object],
    bitrate: str,
) -> None:
    arguments = [
        _ffmpeg_executable(),
        "-nostdin",
        "-v",
        "error",
        "-y",
        "-i",
        str(source),
        "-map",
        "0:a:0",
        "-vn",
        "-codec:a",
        "libmp3lame",
        "-b:a",
        bitrate,
        "-id3v2_version",
        "3",
    ]
    tag_names = {
        "title": "title",
        "artist": "artist",
        "album": "album",
        "album_artist": "album_artist",
        "genre": "genre",
        "track_number": "track",
        "year": "date",
    }
    for field, tag in tag_names.items():
        value = metadata.get(field)
        if value not in (None, ""):
            arguments.extend(["-metadata", f"{tag}={value}"])
    arguments.append(str(output))
    result = subprocess.run(
        arguments, capture_output=True, text=True, timeout=3600, check=False
    )
    if result.returncode:
        message = result.stderr.strip().splitlines()
        raise RuntimeError(
            message[-1][:500]
            if message
            else "FFmpeg could not convert this audio file."
        )


def convert_rows(
    rows: Iterable[dict[str, str]],
    library_root: Path,
    output_dir: Path,
    bitrate: str = "192k",
    progress: Callable[[int, int, dict[str, str] | None], None] | None = None,
) -> tuple[list[str], list[dict[str, str]]]:
    if bitrate not in BITRATES:
        raise ValueError(f"Bitrate must be one of: {', '.join(sorted(BITRATES))}.")

    items = list(rows)
    output_dir.mkdir(parents=True, exist_ok=True)
    outputs: list[str] = []
    errors: list[dict[str, str]] = []

    for index, row in enumerate(items, start=1):
        result: dict[str, str] | None = None
        output: Path | None = None
        try:
            source = _resolve_source(row.get("source", ""), library_root)
            metadata = extract_metadata(str(source)) or {}
            spotify_reference = row.get("spotify_track_id", "")
            if spotify_reference:
                metadata.update(get_spotify_metadata(spotify_reference))
            for field in CSV_FIELDS[1:]:
                if field != "spotify_track_id" and row.get(field):
                    metadata[field] = row[field]
            metadata.setdefault("title", source.stem)
            output = _output_path(metadata, source, output_dir)
            _transcode(source, output, metadata, bitrate)
            outputs.append(output.name)
            result = {
                "source": row.get("source", ""),
                "output": output.name,
                "status": "completed",
            }
        except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
            if output is not None:
                try:
                    output.unlink(missing_ok=True)
                except OSError as cleanup_error:
                    error = RuntimeError(
                        f"{error} (could not remove partial output: {cleanup_error})"
                    )
            errors.append(
                {
                    "line_number": row.get("line_number", ""),
                    "source": row.get("source", ""),
                    "message": str(error)[:500],
                }
            )
            result = {
                "line_number": row.get("line_number", ""),
                "source": row.get("source", ""),
                "status": "failed",
                "error": str(error)[:500],
            }
        finally:
            if progress:
                progress(index, len(items), result)

    return outputs, errors


if __name__ == "__main__":
    if len(sys.argv) > 1:
        from middlemusic.cli import main
    else:
        from middlemusic.converter_gui import main

        raise SystemExit(main())

    raise SystemExit(main())
