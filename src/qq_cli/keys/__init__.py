"""Platform-specific NTQQ runtime key extraction."""

from __future__ import annotations

import platform


def extract_runtime_key(db_dir: str, snapshot_dir: str, app_path: str | None = None, timeout: int = 120) -> dict:
    system = platform.system().lower()
    if system == "darwin":
        from .scanner_macos import extract_runtime_key as _extract

        return _extract(db_dir=db_dir, snapshot_dir=snapshot_dir, app_path=app_path, timeout=timeout)
    raise RuntimeError(f"暂不支持的平台: {platform.system()}")
