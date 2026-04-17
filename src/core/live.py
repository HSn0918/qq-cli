"""Experimental live access helpers backed by on-demand SQLCipher export."""

from __future__ import annotations

import os
import shutil
import tempfile
from collections.abc import Iterator, Mapping

from qq_cli.core.db import discover_db_files
from qq_cli.core.decrypt import decrypt_db_dir, require_sqlcipher


def _reset_dir(path: str) -> None:
    if os.path.isdir(path):
        shutil.rmtree(path)
    os.makedirs(path, exist_ok=True)


def _copy_db_with_sidecars(src_path: str, snapshot_dir: str) -> None:
    os.makedirs(snapshot_dir, exist_ok=True)
    shutil.copy2(src_path, os.path.join(snapshot_dir, os.path.basename(src_path)))
    for suffix in ("-wal", "-shm"):
        sidecar = src_path + suffix
        if os.path.exists(sidecar):
            shutil.copy2(sidecar, os.path.join(snapshot_dir, os.path.basename(src_path) + suffix))


class LiveDBFiles(Mapping[str, str]):
    """Lazily decrypt raw NTQQ databases into a temporary workspace."""

    def __init__(self, raw_db_dir: str, key: str):
        self.raw_db_dir = os.path.abspath(raw_db_dir)
        self.key = key
        self.raw_db_files = discover_db_files(self.raw_db_dir)
        if "nt_msg" not in self.raw_db_files:
            raise FileNotFoundError(f"未在 {self.raw_db_dir} 中找到 nt_msg.db。")

        require_sqlcipher()

        self._workspace = tempfile.TemporaryDirectory(prefix="qq-cli-live-")
        self._decrypted_dir = os.path.join(self._workspace.name, "decrypted")
        self._snapshots_dir = os.path.join(self._workspace.name, "snapshots")
        os.makedirs(self._decrypted_dir, exist_ok=True)
        os.makedirs(self._snapshots_dir, exist_ok=True)
        self._cache: dict[str, str] = {}

    def __getitem__(self, name: str) -> str:
        if name not in self.raw_db_files:
            raise KeyError(name)
        cached = self._cache.get(name)
        if cached and os.path.exists(cached):
            return cached
        output = self._materialize(name)
        self._cache[name] = output
        return output

    def __iter__(self) -> Iterator[str]:
        return iter(self.raw_db_files)

    def __len__(self) -> int:
        return len(self.raw_db_files)

    def get(self, name: str, default=None) -> str | None:
        if name not in self.raw_db_files:
            return default
        return self[name]

    def close(self) -> None:
        self._workspace.cleanup()

    def _materialize(self, name: str) -> str:
        raw_path = self.raw_db_files[name]
        snapshot_dir = os.path.join(self._snapshots_dir, name)
        _reset_dir(snapshot_dir)
        _copy_db_with_sidecars(raw_path, snapshot_dir)

        result = decrypt_db_dir(snapshot_dir, self._decrypted_dir, self.key, names=[name])
        if result["decrypted"]:
            return result["decrypted"][0]["output"]

        failures = "\n".join(f"  {item['name']}: {item['error']}" for item in result["failures"])
        raise RuntimeError(
            f"live 模式解密 {name} 失败。\n"
            f"{failures or '未返回额外错误信息'}"
        )
