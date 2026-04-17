"""NTQQ SQLCipher decryption helpers."""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile

from .db import KNOWN_DB_FILES, discover_db_files, is_ntqq_encrypted_file


class SQLCipherNotFoundError(RuntimeError):
    """Raised when sqlcipher is required but unavailable."""


def sqlcipher_path() -> str | None:
    return shutil.which("sqlcipher")


def require_sqlcipher() -> str:
    path = sqlcipher_path()
    if path:
        return path
    raise SQLCipherNotFoundError(
        "未找到 sqlcipher。\n"
        "请先安装 sqlcipher，再运行 qq-cli decrypt。\n"
        "macOS(Homebrew): brew install sqlcipher"
    )


def strip_ntqq_header(src_path: str, dst_path: str) -> str:
    with open(src_path, "rb") as src, open(dst_path, "wb") as dst:
        data = src.read()
        if is_ntqq_encrypted_file(src_path) and len(data) >= 1024:
            dst.write(data[1024:])
        else:
            dst.write(data)
    return dst_path


def _copy_sidecars(src_path: str, clean_path: str) -> None:
    for suffix in ("-wal", "-shm"):
        src = src_path + suffix
        if os.path.exists(src):
            shutil.copy2(src, clean_path + suffix)


def _sql_quote(value: str) -> str:
    return value.replace("'", "''")


def build_sqlcipher_export_script(key: str, out_path: str) -> str:
    safe_key = _sql_quote(key)
    safe_out = _sql_quote(out_path)
    return "\n".join(
        [
            f"PRAGMA key = '{safe_key}';",
            "PRAGMA cipher_page_size = 4096;",
            "PRAGMA kdf_iter = 4000;",
            "PRAGMA cipher_hmac_algorithm = HMAC_SHA1;",
            "PRAGMA cipher_default_kdf_algorithm = PBKDF2_HMAC_SHA512;",
            f"ATTACH DATABASE '{safe_out}' AS plaintext KEY '';",
            "SELECT sqlcipher_export('plaintext');",
            "DETACH DATABASE plaintext;",
            ".quit",
            "",
        ]
    )


def export_plaintext_db(clean_path: str, out_path: str, key: str) -> None:
    sqlcipher = require_sqlcipher()
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    if os.path.exists(out_path):
        os.remove(out_path)
    for suffix in ("-wal", "-shm"):
        maybe = out_path + suffix
        if os.path.exists(maybe):
            os.remove(maybe)

    script = build_sqlcipher_export_script(key, out_path)
    proc = subprocess.run(
        [sqlcipher, clean_path],
        input=script,
        text=True,
        capture_output=True,
    )
    if proc.returncode != 0:
        stderr = proc.stderr.strip() or proc.stdout.strip() or "sqlcipher export failed"
        raise RuntimeError(f"解密失败: {clean_path}\n{stderr}")


def decrypt_db_file(src_path: str, out_path: str, key: str, temp_dir: str | None = None) -> dict:
    working_dir = temp_dir or tempfile.mkdtemp(prefix="qq-cli-decrypt-")
    clean_path = os.path.join(working_dir, os.path.basename(src_path) + ".clean")
    strip_ntqq_header(src_path, clean_path)
    _copy_sidecars(src_path, clean_path)
    export_plaintext_db(clean_path, out_path, key)
    return {"source": src_path, "output": out_path}


def decrypt_db_dir(db_dir: str, out_dir: str, key: str, names: list[str] | None = None) -> dict:
    db_files = discover_db_files(db_dir)
    if not db_files:
        raise FileNotFoundError(f"未在 {db_dir} 中找到已知 NTQQ 数据库")

    selected = names or list(KNOWN_DB_FILES.keys())
    selected_files = [(name, db_files[name]) for name in selected if name in db_files]
    if not selected_files:
        raise FileNotFoundError("没有可解密的目标数据库")

    os.makedirs(out_dir, exist_ok=True)
    results: list[dict] = []
    failures: list[dict] = []
    with tempfile.TemporaryDirectory(prefix="qq-cli-decrypt-work-") as work_dir:
        for name, src_path in selected_files:
            out_path = os.path.join(out_dir, os.path.basename(src_path))
            try:
                result = decrypt_db_file(src_path, out_path, key=key, temp_dir=work_dir)
                result["name"] = name
                results.append(result)
            except Exception as exc:
                failures.append({"name": name, "source": src_path, "error": str(exc)})

    return {
        "db_dir": db_dir,
        "out_dir": out_dir,
        "decrypted": results,
        "failures": failures,
    }
