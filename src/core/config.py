"""配置加载与自动发现。"""

from __future__ import annotations

import glob as glob_mod
import json
import os
import platform
import sys

from qq_cli.core.db import discover_db_files

_SYSTEM = platform.system().lower()

STATE_DIR = os.path.expanduser("~/.qq-cli")
CONFIG_FILE = os.path.join(STATE_DIR, "config.json")


def _choose_candidate(candidates: list[str]) -> str | None:
    if len(candidates) == 1:
        return candidates[0]
    if len(candidates) > 1:
        if not sys.stdin.isatty():
            return candidates[0]
        print("[!] 检测到多个 NTQQ 数据目录:")
        for idx, candidate in enumerate(candidates, 1):
            print(f"    {idx}. {candidate}")
        print("    0. 跳过")
        try:
            while True:
                choice = input(f"请选择 [0-{len(candidates)}]: ").strip()
                if choice == "0":
                    return None
                if choice.isdigit() and 1 <= int(choice) <= len(candidates):
                    return candidates[int(choice) - 1]
                print("    无效输入")
        except (EOFError, KeyboardInterrupt):
            print()
            return None
    return None


def _sorted_existing(paths: list[str]) -> list[str]:
    uniq: list[str] = []
    seen: set[str] = set()
    for path in paths:
        normalized = os.path.normcase(os.path.normpath(path))
        if os.path.isdir(path) and normalized not in seen:
            seen.add(normalized)
            uniq.append(path)

    def _score(path: str) -> float:
        target = os.path.join(path, "nt_msg.db")
        try:
            return os.path.getmtime(target if os.path.exists(target) else path)
        except OSError:
            return 0

    uniq.sort(key=_score, reverse=True)
    return uniq


def _glob_many(patterns: list[str]) -> list[str]:
    matches: list[str] = []
    for pattern in patterns:
        matches.extend(glob_mod.glob(os.path.expanduser(pattern)))
    return _sorted_existing(matches)


def _auto_detect_db_dir_windows() -> str | None:
    appdata = os.environ.get("APPDATA", "")
    localappdata = os.environ.get("LOCALAPPDATA", "")
    userprofile = os.environ.get("USERPROFILE", "")
    patterns = [
        os.path.join(appdata, "Tencent", "QQ", "nt_qq_*", "nt_db"),
        os.path.join(localappdata, "Tencent", "QQ", "nt_qq_*", "nt_db"),
        os.path.join(userprofile, "Documents", "Tencent Files", "*", "nt_qq", "nt_db"),
    ]
    return _choose_candidate(_glob_many(patterns))


def _auto_detect_db_dir_linux() -> str | None:
    patterns = [
        "~/.config/QQ/nt_qq_*/nt_db",
        "~/.local/share/QQ/nt_qq_*/nt_db",
        "~/.var/app/com.qq.QQ/data/QQ/nt_qq_*/nt_db",
    ]
    return _choose_candidate(_glob_many(patterns))


def _auto_detect_db_dir_macos() -> str | None:
    patterns = [
        "~/Library/Containers/com.tencent.qq/Data/Library/Application Support/QQ/nt_qq_*/nt_db",
        "~/Library/Containers/com.tencent.qq/Data/Documents/contents/Data/Library/Application Support/QQ/nt_qq_*/nt_db",
    ]
    return _choose_candidate(_glob_many(patterns))


def auto_detect_db_dir() -> str | None:
    if _SYSTEM == "windows":
        return _auto_detect_db_dir_windows()
    if _SYSTEM == "linux":
        return _auto_detect_db_dir_linux()
    if _SYSTEM == "darwin":
        return _auto_detect_db_dir_macos()
    return None


def load_config(config_path: str | None = None) -> dict:
    if config_path is None:
        config_path = CONFIG_FILE

    cfg: dict = {}
    if os.path.exists(config_path):
        try:
            with open(config_path, encoding="utf-8") as f:
                cfg = json.load(f)
        except json.JSONDecodeError:
            cfg = {}

    db_dir = cfg.get("db_dir", "")
    if not db_dir:
        detected = auto_detect_db_dir()
        if detected:
            db_dir = detected
            cfg["db_dir"] = detected
        else:
            raise FileNotFoundError(
                "未找到 NTQQ 数据目录。\n"
                "请运行: qq-cli init --db-dir /path/to/nt_db"
            )

    state_dir = os.path.dirname(os.path.abspath(config_path))
    if not os.path.isabs(db_dir):
        db_dir = os.path.join(state_dir, db_dir)
    cfg["db_dir"] = os.path.abspath(db_dir)
    cfg.setdefault("decrypted_dir", os.path.join(state_dir, "decrypted"))
    if not os.path.isabs(cfg["decrypted_dir"]):
        cfg["decrypted_dir"] = os.path.join(state_dir, cfg["decrypted_dir"])

    source_db_dir = cfg["decrypted_dir"] if os.path.exists(os.path.join(cfg["decrypted_dir"], "nt_msg.db")) else cfg["db_dir"]
    db_files = discover_db_files(source_db_dir)
    if "nt_msg" not in db_files:
        raise FileNotFoundError(
            f"未在 {source_db_dir} 中找到 nt_msg.db。\n"
            "请确认这里是 QQ 的 nt_db 目录。"
        )

    cfg["source_db_dir"] = source_db_dir
    cfg["db_files"] = db_files
    return cfg


def write_config(
    db_dir: str,
    config_path: str | None = None,
    decrypted_dir: str | None = None,
    db_key: str | None = None,
) -> str:
    config_path = config_path or CONFIG_FILE
    os.makedirs(os.path.dirname(config_path), exist_ok=True)
    payload = {"db_dir": os.path.abspath(db_dir)}
    if decrypted_dir:
        payload["decrypted_dir"] = os.path.abspath(decrypted_dir)
    if db_key:
        payload["db_key"] = db_key
    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
        f.write("\n")
    return config_path
