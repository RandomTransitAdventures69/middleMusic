import csv
import io
import re
import shutil
import subprocess
from pathlib import Path
from typing import Callable, Dict, Iterable, List, Optional, Tuple

from .scanner import AUDIO_EXTENSIONS, extract_metadata

BITRATES = {"128k", "192k", "256k", "320k"}
MAPPED_FIELDS = (
    "source",
    "title",
    "artist",
    "album",
    "album_artist",
    "genre",
    "track_number",
    "year",
)


def parse_csv(content: bytes, mapping: Dict[str, str]) -> List[Dict[str, str]]:
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError as error:
        raise ValueError("CSV file must use UTF-8 encoding.") from error

    reader = csv.DictReader(io.StringIO(text))
    headers = reader.fieldnames or []
    source_column = (mapping.get("source") or "source").strip()
    if source_column not in headers:
        raise ValueError(f"CSV has no source column named '{source_column}'.")

    selected_columns = {"source": source_column}
    for field in MAPPED_FIELDS[1:]:
        column = (mapping.get(field) or "").strip()
        if column and column not in headers:
            raise ValueError(f"CSV has no {field.replace('_', ' ')} column named '{column}'.")
        selected_columns[field] = column

    rows = []
    for line_number, row in enumerate(reader, start=2):
        source = (row.get(source_column) or "").strip()
        if not source:
            continue
        rows.append(
            {
                "line_number": str(line_number),
                **{
                    field: (row.get(column) or "").strip() if column else ""
                    for field, column in selected_columns.items()
                },
            }
        )
    if not rows:
        raise ValueError("CSV contains no rows with a source file.")
    return rows


def _ffmpeg_executable() -> str:
    executable = shutil.which("ffmpeg")
    if executable:
        return executable
    try:
        import imageio_ffmpeg
    except ImportError as error:
        raise RuntimeError("FFmpeg is unavailable. Reinstall middleMusic dependencies.") from error
    return imageio_ffmpeg.get_ffmpeg_exe()


def _resolve_source(source_value: str, library_root: Path) -> Path:
    if re.match(r"^[A-Za-z][A-Za-z0-9+.-]*://", source_value):
        raise ValueError("Remote audio URLs are not supported; use a local library file.")

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
    cleaned = re.sub(r'[<>:"/\\\\|?*\\x00-\\x1f]', "_", value).strip(" .")
    return cleaned[:160] or "untitled"


def _output_path(metadata: Dict[str, object], source: Path, output_dir: Path) -> Path:
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
    metadata: Dict[str, object],
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
    result = subprocess.run(arguments, capture_output=True, text=True, timeout=3600, check=False)
    if result.returncode:
        message = result.stderr.strip().splitlines()
        raise RuntimeError(message[-1][:500] if message else "FFmpeg could not convert this audio file.")


def convert_rows(
    rows: Iterable[Dict[str, str]],
    library_root: Path,
    output_dir: Path,
    bitrate: str = "192k",
    progress: Optional[Callable[[int, int, Optional[Dict[str, str]]], None]] = None,
) -> Tuple[List[str], List[Dict[str, str]]]:
    if bitrate not in BITRATES:
        raise ValueError(f"Bitrate must be one of: {', '.join(sorted(BITRATES))}.")

    items = list(rows)
    output_dir.mkdir(parents=True, exist_ok=True)
    outputs: List[str] = []
    errors: List[Dict[str, str]] = []

    for index, row in enumerate(items, start=1):
        result: Optional[Dict[str, str]] = None
        output: Optional[Path] = None
        try:
            source = _resolve_source(row.get("source", ""), library_root)
            metadata = extract_metadata(str(source)) or {}
            for field in MAPPED_FIELDS[1:]:
                if row.get(field):
                    metadata[field] = row[field]
            metadata.setdefault("title", source.stem)
            output = _output_path(metadata, source, output_dir)
            _transcode(source, output, metadata, bitrate)
            outputs.append(output.name)
            result = {"source": row.get("source", ""), "output": output.name, "status": "completed"}
        except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
            if output is not None:
                try:
                    output.unlink(missing_ok=True)
                except OSError as cleanup_error:
                    error = RuntimeError(f"{error} (could not remove partial output: {cleanup_error})")
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
