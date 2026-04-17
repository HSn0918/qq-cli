"""Application context."""

from __future__ import annotations

import os

from qq_cli.core.config import CONFIG_FILE, load_config
from qq_cli.core.contacts import load_buddies, load_groups
from qq_cli.core.db import discover_db_files
from qq_cli.core.live import LiveDBFiles
from qq_cli.core.messages import load_recent_sessions


class AppContext:
    def __init__(self, config_path: str | None = None, mode: str = "auto", decrypted_dir: str | None = None):
        self.cfg = self._load_cfg(config_path, decrypted_dir)
        self.raw_db_dir = self.cfg.get("db_dir", "")
        self.decrypted_dir = self.cfg["decrypted_dir"]
        self.mode = mode
        self._live_db_files: LiveDBFiles | None = None

        if decrypted_dir:
            self.mode = "decrypted"
            self.db_dir = self.decrypted_dir
            self.db_files = self.cfg["db_files"]
        elif mode == "live":
            live_key = self._resolve_live_key()
            self.db_dir = self.raw_db_dir
            self._live_db_files = LiveDBFiles(self.raw_db_dir, live_key)
            self.db_files = self._live_db_files
        else:
            self.db_dir = self.cfg["source_db_dir"]
            self.db_files = self.cfg["db_files"]

        self._buddies = None
        self._groups = None
        self._recent_cache: dict[int, list[dict]] = {}

    def _load_cfg(self, config_path: str | None, decrypted_dir: str | None) -> dict:
        if not decrypted_dir:
            return load_config(config_path)

        override_dir = os.path.abspath(os.path.expanduser(decrypted_dir))
        db_files = discover_db_files(override_dir)
        if "nt_msg" not in db_files:
            raise FileNotFoundError(
                f"未在 {override_dir} 中找到 nt_msg.db。\n"
                "请确认这里是已导出的明文数据库目录。"
            )

        cfg_path = os.path.abspath(config_path or CONFIG_FILE)
        cfg: dict = {
            "db_dir": "",
            "decrypted_dir": override_dir,
            "source_db_dir": override_dir,
            "db_files": db_files,
        }
        if os.path.exists(cfg_path):
            try:
                loaded = load_config(cfg_path)
            except FileNotFoundError:
                loaded = {}
            cfg.update({k: v for k, v in loaded.items() if k not in {"decrypted_dir", "source_db_dir", "db_files"}})
            cfg["decrypted_dir"] = override_dir
            cfg["source_db_dir"] = override_dir
            cfg["db_files"] = db_files
        return cfg

    def _resolve_live_key(self) -> str:
        value = os.environ.get("QQ_CLI_KEY")
        if value:
            return value
        cfg_value = self.cfg.get("db_key")
        if cfg_value:
            return str(cfg_value)
        raise RuntimeError(
            "live 模式缺少数据库密钥。\n"
            "请先运行 qq-cli init，或设置环境变量 QQ_CLI_KEY。"
        )

    @property
    def buddies(self) -> list[dict]:
        if self._buddies is None:
            self._buddies = load_buddies(self.db_files)
        return self._buddies

    @property
    def groups(self) -> list[dict]:
        if self._groups is None:
            self._groups = load_groups(self.db_files)
        return self._groups

    def recent_sessions(self, limit: int = 200) -> list[dict]:
        if limit not in self._recent_cache:
            self._recent_cache[limit] = load_recent_sessions(self.db_files, self.buddies, self.groups, limit)
        return self._recent_cache[limit]

    def close(self) -> None:
        if self._live_db_files is not None:
            self._live_db_files.close()
