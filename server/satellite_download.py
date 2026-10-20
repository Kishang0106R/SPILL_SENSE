"""Secure, asynchronous-to-the-request downloads of selected ASF scenes."""

import json
import logging
import os
import re
import shutil
import tempfile
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from errno import ENOSPC
from pathlib import Path
from typing import Any, Dict, Optional
from urllib.error import HTTPError, URLError


logger = logging.getLogger(__name__)
SCENE_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,199}$")
DEFAULT_DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "sentinel1"
MAX_DOWNLOAD_JOBS = 200
_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="sentinel1-download")
_jobs: Dict[str, Dict[str, Any]] = {}
_jobs_lock = threading.Lock()


class SatelliteDownloadError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def _data_directory() -> Path:
    configured = os.getenv("SENTINEL1_DATA_DIR")
    return Path(configured).expanduser().resolve() if configured else DEFAULT_DATA_DIR


def _iso_utc(value: Optional[datetime]) -> Optional[str]:
    if value is None:
        return None
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("acquisition_time must include a timezone.")
    return value.astimezone(timezone.utc).isoformat()


def _validate_scene_id(scene_id: str) -> str:
    if not SCENE_ID_PATTERN.fullmatch(scene_id):
        raise ValueError("scene_id contains unsupported characters.")
    return scene_id


def _snapshot(job_id: str) -> Optional[Dict[str, Any]]:
    with _jobs_lock:
        job = _jobs.get(job_id)
        return dict(job) if job else None


def get_download_status(job_id: str) -> Optional[Dict[str, Any]]:
    return _snapshot(job_id)


def start_scene_download(
    scene_id: str,
    acquisition_time: Optional[datetime] = None,
) -> Dict[str, Any]:
    scene_id = _validate_scene_id(scene_id)
    acquisition_utc = _iso_utc(acquisition_time)
    job_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    job = {
        "job_id": job_id,
        "scene_id": scene_id,
        "source": "Alaska Satellite Facility (ASF) DAAC",
        "acquisition_time": acquisition_utc,
        "status": "queued",
        "error_code": None,
        "message": "Download queued.",
        "files": [],
        "preparation_status": "not_prepared",
        "created_at": now,
        "updated_at": now,
    }

    with _jobs_lock:
        finished_ids = [
            key for key, value in _jobs.items()
            if value["status"] in {"completed", "failed"}
        ]
        for completed_id in finished_ids[:-MAX_DOWNLOAD_JOBS]:
            del _jobs[completed_id]
        _jobs[job_id] = job

    _executor.submit(_run_download_job, job_id)
    return dict(job)


def _update_job(job_id: str, **changes: Any) -> None:
    with _jobs_lock:
        job = _jobs.get(job_id)
        if job is not None:
            job.update(changes)
            job["updated_at"] = datetime.now(timezone.utc).isoformat()


def _classify_external_error(exc: Exception) -> SatelliteDownloadError:
    status = getattr(exc, "status_code", None) or getattr(exc, "code", None)
    if isinstance(exc, HTTPError):
        status = exc.code
    class_name = type(exc).__name__.lower()
    message = str(exc).lower()
    if status in {401, 403} or "auth" in class_name or "unauthorized" in message:
        return SatelliteDownloadError(
            "authentication_failed",
            "Earthdata authentication failed. Check the server credentials and ASF access permissions.",
        )
    if isinstance(exc, (URLError, TimeoutError)) or "timeout" in class_name.lower():
        return SatelliteDownloadError(
            "network_error",
            "The ASF download could not be completed because of a network error or timeout.",
        )
    return SatelliteDownloadError(
        "download_failed",
        "ASF could not resolve or download this scene. Confirm the scene ID and retry.",
    )


def _download_product(scene_id: str, destination: Path) -> None:
    username = os.getenv("EARTHDATA_USERNAME", "").strip()
    password = os.getenv("EARTHDATA_PASSWORD", "")
    if not username or not password:
        raise SatelliteDownloadError(
            "authentication_required",
            "Set EARTHDATA_USERNAME and EARTHDATA_PASSWORD in the backend environment.",
        )

    try:
        import asf_search as asf
    except ImportError as exc:
        raise SatelliteDownloadError(
            "dependency_missing",
            "ASF download support is unavailable. Install the project requirements.",
        ) from exc

    try:
        session = asf.ASFSession().auth_with_creds(username, password)
        products = asf.granule_search([scene_id])
        if not products:
            raise SatelliteDownloadError(
                "scene_not_found",
                "ASF returned no product for this scene ID.",
            )
        products.download(path=str(destination), session=session)
    except SatelliteDownloadError:
        raise
    except Exception as exc:
        raise _classify_external_error(exc) from exc


def _collect_downloaded_files(directory: Path, data_root: Path) -> list[Dict[str, Any]]:
    files = []
    for path in directory.rglob("*"):
        if path.is_symlink():
            raise SatelliteDownloadError(
                "unsafe_product",
                "Downloaded product contains an unexpected symbolic link.",
            )
        if not path.is_file():
            continue
        resolved_path = path.resolve()
        try:
            relative = resolved_path.relative_to(data_root.resolve())
        except ValueError as exc:
            raise SatelliteDownloadError(
                "unsafe_product",
                "Downloaded product escaped the configured data directory.",
            ) from exc
        if path.name != "metadata.json":
            files.append({
                "name": path.name,
                "relative_path": str(relative),
                "size_bytes": path.stat().st_size,
            })
    return files


def _run_download_job(job_id: str) -> None:
    job = _snapshot(job_id)
    if job is None:
        return

    data_root = _data_directory()
    stage_directory: Optional[Path] = None
    _update_job(job_id, status="downloading", message="Resolving the selected scene with ASF.")
    try:
        data_root.mkdir(parents=True, exist_ok=True)
        scene_directory = data_root / job["scene_id"]
        if scene_directory.exists():
            raise SatelliteDownloadError(
                "destination_exists",
                "A download directory already exists for this scene. Inspect it before retrying.",
            )

        stage_directory = Path(tempfile.mkdtemp(
            prefix=f".{job['scene_id']}.{job_id}.",
            suffix=".partial",
            dir=data_root,
        ))
        _update_job(job_id, message="Downloading the ASF product; raw imagery is not prepared for detection.")
        _download_product(job["scene_id"], stage_directory)
        files = _collect_downloaded_files(stage_directory, data_root)
        if not files:
            raise SatelliteDownloadError(
                "empty_product",
                "ASF completed without placing product files in the download directory.",
            )

        metadata = {
            "source": job["source"],
            "scene_id": job["scene_id"],
            "acquisition_time": job["acquisition_time"],
            "downloaded_at": datetime.now(timezone.utc).isoformat(),
            "files": files,
            "preparation_status": "not_prepared",
        }
        metadata_path = stage_directory / "metadata.json"
        metadata_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
        os.replace(stage_directory, scene_directory)
        stage_directory = None
        files = [
            {**item, "relative_path": str(Path(job["scene_id"]) / item["relative_path"].split(job["job_id"])[-1].split(".partial")[-1])}
            for item in files
        ]
        final_files = _collect_downloaded_files(scene_directory, data_root)
        _update_job(
            job_id,
            status="completed",
            error_code=None,
            message="Product downloaded. It remains raw/unprepared and is not yet valid detector input.",
            files=final_files,
            preparation_status="not_prepared",
            completed_at=datetime.now(timezone.utc).isoformat(),
        )
    except SatelliteDownloadError as exc:
        _update_job(
            job_id,
            status="failed",
            error_code=exc.code,
            message=str(exc),
            completed_at=datetime.now(timezone.utc).isoformat(),
        )
    except OSError as exc:
        code = "disk_full" if exc.errno == ENOSPC else "disk_error"
        message = (
            "Insufficient disk space for the Sentinel-1 product."
            if code == "disk_full"
            else "The Sentinel-1 product could not be written to the configured data directory."
        )
        _update_job(
            job_id,
            status="failed",
            error_code=code,
            message=message,
            completed_at=datetime.now(timezone.utc).isoformat(),
        )
    finally:
        if stage_directory is not None and stage_directory.exists():
            try:
                shutil.rmtree(stage_directory)
            except OSError:
                logger.warning("Could not clean partial Sentinel-1 download for job %s", job_id)
