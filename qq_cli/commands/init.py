"""Initialize qq-cli configuration and decrypt NTQQ databases."""

from __future__ import annotations

import os
import tempfile

import click

from ..core.config import CONFIG_FILE, auto_detect_db_dir, write_config
from ..core.db import discover_db_files
from ..core.decrypt import SQLCipherNotFoundError, decrypt_db_dir
from ..keys import extract_runtime_key


@click.command("init")
@click.option("--db-dir", default=None, help="显式指定 NTQQ 的 nt_db 目录")
@click.option("--decrypted-dir", default=None, help="明文数据库导出目录")
@click.option("--app-path", default=None, help="显式指定 QQ.app 路径")
@click.option("--timeout", default=120, show_default=True, type=int, help="等待 QQ 启动并命中用户库的超时时间（秒）")
@click.option("--force", is_flag=True, help="覆盖已存在的配置文件")
@click.pass_context
def init(ctx, db_dir, decrypted_dir, app_path, timeout, force):
    """初始化 qq-cli：自动抓取运行时 key 并解密 NTQQ 数据库。"""
    root = ctx.find_root()
    config_path = root.params.get("config_path") or CONFIG_FILE
    if os.path.exists(config_path) and not force:
        click.echo(f"配置已存在: {config_path}\n如需覆盖请追加 --force")
        return

    db_dir = db_dir or auto_detect_db_dir()
    if not db_dir:
        raise click.ClickException("未找到 NTQQ 数据目录，请使用 --db-dir 显式指定")

    db_files = discover_db_files(db_dir)
    if "nt_msg" not in db_files:
        raise click.ClickException(f"{db_dir} 不是有效的 nt_db 目录：缺少 nt_msg.db")

    out_dir = decrypted_dir or os.path.join(os.path.dirname(os.path.abspath(config_path)), "decrypted")

    click.echo(f"raw_db_dir: {os.path.abspath(db_dir)}")
    click.echo("启动 QQ 并抓取运行时数据库 key ...")
    with tempfile.TemporaryDirectory(prefix="qq-cli-init-snapshot-") as snapshot_dir:
        try:
            key_info = extract_runtime_key(
                db_dir=db_dir,
                snapshot_dir=snapshot_dir,
                app_path=app_path,
                timeout=timeout,
            )
        except RuntimeError as exc:
            raise click.ClickException(str(exc)) from exc

        click.echo(f"抓取方式: {key_info.get('method', 'unknown')}")
        click.echo(f"命中数据库: {key_info['db_path']}")
        click.echo(f"抓取到 key(len={key_info['key_len']}): {key_info['key']}")
        click.echo(f"开始导出明文数据库 -> {os.path.abspath(out_dir)}")

        try:
            decrypt_result = decrypt_db_dir(snapshot_dir, out_dir, key_info["key"])
        except SQLCipherNotFoundError as exc:
            raise click.ClickException(str(exc)) from exc

        if not any(item["name"] == "nt_msg" for item in decrypt_result["decrypted"]) and key_info.get("method") == "c_scan":
            click.echo("C 快速扫描得到的 key 未通过解密验证，回退 LLDB 启动期抓取 ...")
            try:
                key_info = extract_runtime_key(
                    db_dir=db_dir,
                    snapshot_dir=snapshot_dir,
                    app_path=app_path,
                    timeout=timeout,
                    strategy="lldb",
                )
            except RuntimeError as exc:
                raise click.ClickException(str(exc)) from exc

            click.echo(f"抓取方式: {key_info.get('method', 'unknown')}")
            click.echo(f"命中数据库: {key_info['db_path']}")
            click.echo(f"抓取到 key(len={key_info['key_len']}): {key_info['key']}")
            click.echo(f"开始导出明文数据库 -> {os.path.abspath(out_dir)}")
            try:
                decrypt_result = decrypt_db_dir(snapshot_dir, out_dir, key_info["key"])
            except SQLCipherNotFoundError as exc:
                raise click.ClickException(str(exc)) from exc

    if not any(item["name"] == "nt_msg" for item in decrypt_result["decrypted"]):
        failures = "\n".join(f"  {item['name']}: {item['error']}" for item in decrypt_result["failures"])
        raise click.ClickException("nt_msg.db 解密失败。\n" + (failures or "未返回额外错误信息"))

    write_config(
        db_dir,
        config_path=config_path,
        decrypted_dir=out_dir,
        db_key=key_info["key"],
    )
    click.echo(f"已写入配置: {config_path}")
    click.echo(f"decrypted_dir: {os.path.abspath(out_dir)}")
    click.echo("检测到数据库: " + ", ".join(sorted(db_files)))
    if decrypt_result["decrypted"]:
        click.echo("已导出:")
        for item in decrypt_result["decrypted"]:
            click.echo(f"  {item['name']}: {item['output']}")
    if decrypt_result["failures"]:
        click.echo("导出失败:")
        for item in decrypt_result["failures"]:
            click.echo(f"  {item['name']}: {item['error']}")
