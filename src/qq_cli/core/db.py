"""SQLite helpers."""

from __future__ import annotations

import os
import sqlite3

import click


KNOWN_DB_FILES = {
    "nt_msg": "nt_msg.db",
    "profile_info": "profile_info.db",
    "group_info": "group_info.db",
    "emoji": "emoji.db",
    "collection": "collection.db",
    "files_in_chat": "files_in_chat.db",
    "rich_media": "rich_media.db",
}


class EncryptedNTQQDatabaseError(click.ClickException):
    """Raised when a DB file has the NTQQ custom header / SQLCipher format."""


def is_ntqq_encrypted_file(path: str) -> bool:
    try:
        with open(path, "rb") as f:
            header = f.read(64)
    except OSError:
        return False
    return header.startswith(b"SQLite header 3\x00") and b"QQ_NT DB" in header


def discover_db_files(db_dir: str) -> dict[str, str]:
    db_files: dict[str, str] = {}
    for name, filename in KNOWN_DB_FILES.items():
        path = os.path.join(db_dir, filename)
        if os.path.exists(path):
            db_files[name] = path
    return db_files


def connect(path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("PRAGMA schema_version").fetchone()
    except sqlite3.DatabaseError as exc:
        conn.close()
        if is_ntqq_encrypted_file(path):
            raise EncryptedNTQQDatabaseError(
                f"{path} 是 NTQQ 加密数据库，不能直接用 sqlite3 读取。\n"
                "请先运行 qq-cli init 自动抓取运行时 key 并导出明文数据库，"
                "或手动执行 qq-cli decrypt --key <pKey>。"
            ) from exc
        raise
    return conn


def quote_ident(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'


def table_exists(conn: sqlite3.Connection, table: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
        (table,),
    ).fetchone()
    return row is not None


def table_columns(conn: sqlite3.Connection, table: str) -> set[str]:
    return {str(row[1]) for row in conn.execute(f"PRAGMA table_info({quote_ident(table)})")}


def value_or_none(row: sqlite3.Row | dict, key: str):
    if row is None:
        return None
    if isinstance(row, sqlite3.Row):
        return row[key] if key in row.keys() else None
    return row.get(key)
