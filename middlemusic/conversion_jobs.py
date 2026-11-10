from pathlib import Path
from threading import Thread

from .converter import convert_rows
from .database import create_conversion_job, update_conversion_job


def _process(
    job_id: str,
    rows: list[dict[str, str]],
    library_root: Path,
    output_dir: Path,
    bitrate: str,
) -> None:
    outputs: list[str] = []
    errors: list[dict[str, str]] = []
    update_conversion_job(job_id, "running", 0, outputs, errors)

    def report_progress(completed: int, total: int, result: dict[str, str]) -> None:
        if result["status"] == "completed":
            outputs.append(result["output"])
        else:
            errors.append(
                {
                    "line_number": result.get("line_number", ""),
                    "source": result.get("source", ""),
                    "message": result.get("error", "Conversion failed."),
                }
            )
        update_conversion_job(job_id, "running", completed, outputs, errors)

    try:
        outputs, errors = convert_rows(rows, library_root, output_dir, bitrate, report_progress)
        status = "completed" if not errors else ("completed_with_errors" if outputs else "failed")
        update_conversion_job(job_id, status, len(rows), outputs, errors)
    except Exception as error:
        errors.append({"line_number": "", "source": "", "message": str(error)[:500]})
        update_conversion_job(job_id, "failed", len(outputs) + len(errors), outputs, errors)


def start_conversion_job(
    job_id: str,
    user_id: int,
    rows: list[dict[str, str]],
    library_root: Path,
    output_dir: Path,
    bitrate: str,
) -> None:
    create_conversion_job(job_id, user_id, len(rows), str(output_dir))
    thread = Thread(
        target=_process,
        args=(job_id, rows, library_root, output_dir, bitrate),
        daemon=True,
        name=f"conversion-{job_id}",
    )
    thread.start()
