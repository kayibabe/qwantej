"""Stable content fingerprint for the code that produces forecast probabilities."""

from functools import lru_cache
from hashlib import sha256
from pathlib import Path


@lru_cache(maxsize=1)
def forecast_build_id() -> str:
    """Identify the scorer source mounted into this runtime, including dirty edits."""
    services_dir = Path(__file__).resolve().parent
    model_dir = services_dir / "models"
    source_files = [Path(__file__).resolve(), services_dir / "model_runner.py"]
    source_files.extend(sorted(model_dir.rglob("*.py")))

    digest = sha256()
    for source_file in source_files:
        digest.update(source_file.relative_to(services_dir.parent.parent).as_posix().encode())
        digest.update(b"\0")
        digest.update(source_file.read_bytes())
        digest.update(b"\0")
    return f"qwantej-scorer-sha256-v1:{digest.hexdigest()}"
