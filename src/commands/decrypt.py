"""Decrypt NTQQ databases into plaintext SQLite files."""

from __future__ import annotations

import os

import click

from qq_cli.core.config import CONFIG_FILE, auto_detect_db_dir, load_config
from qq_cli.core.decrypt import SQLCipherNotFoundError, decrypt_db_dir
from qq_cli.output.formatter import output


def _resolve_key(key: str | None, key_env: str | None, cfg: dict | None = None) -> str:
    if key:
        return key
    if key_env:
        value = os.environ.get(key_env)
        if value:
            return value
    if cfg:
        value = cfg.get("db_key")
        if value:
            return str(value)
    raise click.ClickException("缺少数据库密钥，请使用 --key 或 --key-env 提供 pKey")


@click.command("decrypt")
@click.option("--db-dir", default=None, help="原始 NTQQ nt_db 目录；默认从配置或自动探测读取")
@click.option("--out-dir", default=None, help="导出明文数据库目录")
@click.option("--key", default=None, help="运行时抓取到的 NTQQ pKey")
@click.option("--key-env", default="QQ_CLI_KEY", help="从环境变量读取 pKey，默认 QQ_CLI_KEY")
@click.option("--db", "db_names", multiple=True, help="只解密指定数据库名，如 nt_msg/profile_info/group_info")
@click.option("--format", "fmt", default="text", type=click.Choice(["json", "text"]), help="输出格式")
@click.pass_context
def decrypt(ctx, db_dir, out_dir, key, key_env, db_names, fmt):
    """按 QQDecrypt 文档导出 NTQQ 明文数据库。"""
    root = ctx.find_root()
    config_path = root.params.get("config_path") or CONFIG_FILE

    cfg = {}
    if os.path.exists(config_path):
        try:
            cfg = load_config(config_path)
        except Exception:
            cfg = {}

    db_dir = db_dir or cfg.get("db_dir") or auto_detect_db_dir()
    if not db_dir:
        raise click.ClickException("未找到 NTQQ 数据目录，请使用 --db-dir 指定")

    out_dir = out_dir or cfg.get("decrypted_dir") or os.path.join(os.path.dirname(os.path.abspath(config_path)), "decrypted")
    secret = _resolve_key(key, key_env, cfg=cfg)

    try:
        result = decrypt_db_dir(db_dir, out_dir, secret, names=list(db_names) or None)
    except SQLCipherNotFoundError as exc:
        raise click.ClickException(str(exc)) from exc

    if fmt == "json":
        output(result, "json")
        return

    lines = [f"raw_db_dir: {result['db_dir']}", f"out_dir: {result['out_dir']}"]
    if result["decrypted"]:
        lines.append("已导出:")
        lines.extend([f"  {item['name']}: {item['output']}" for item in result["decrypted"]])
    if result["failures"]:
        lines.append("失败:")
        lines.extend([f"  {item['name']}: {item['error']}" for item in result["failures"]])
    output("\n".join(lines), "text")
