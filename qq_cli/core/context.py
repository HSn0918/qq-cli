"""Application context."""

from __future__ import annotations

from .config import load_config
from .contacts import load_buddies, load_groups
from .messages import load_recent_sessions


class AppContext:
    def __init__(self, config_path: str | None = None):
        self.cfg = load_config(config_path)
        self.db_dir = self.cfg["source_db_dir"]
        self.raw_db_dir = self.cfg["db_dir"]
        self.decrypted_dir = self.cfg["decrypted_dir"]
        self.db_files = self.cfg["db_files"]
        self._buddies = None
        self._groups = None
        self._recent_cache: dict[int, list[dict]] = {}

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
