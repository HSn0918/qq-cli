"""qq-cli 入口。"""

from __future__ import annotations

import sys

import click

from qq_cli import __version__
from qq_cli.core.context import AppContext
from qq_cli.core.db import EncryptedNTQQDatabaseError


@click.group()
@click.version_option(version=__version__, prog_name="qq-cli")
@click.option(
    "--config",
    "config_path",
    default=None,
    envvar="QQ_CLI_CONFIG",
    help="config.json 路径；默认读取 ~/.qq-cli/config.json",
)
@click.option(
    "--mode",
    "db_mode",
    default="live",
    type=click.Choice(["auto", "live", "decrypted"]),
    show_default=True,
    help=(
        "数据库读取模式：live 为默认实验模式，会按需临时解密原始加密库；"
        "auto 优先已导出的明文库；"
        "decrypted 直接读取明文目录"
    ),
)
@click.option(
    "--decrypted-dir",
    default=None,
    help="显式指定明文数据库目录；传入后优先于 --mode，适合手动导出的明文库",
)
@click.pass_context
def cli(ctx, config_path, db_mode, decrypted_dir):
    """QQ CLI — 查询 NTQQ 本地数据库。"""
    if ctx.invoked_subcommand in ("init", "version", "decrypt"):
        return

    try:
        ctx.obj = AppContext(config_path, mode=db_mode, decrypted_dir=decrypted_dir)
        ctx.call_on_close(ctx.obj.close)
    except FileNotFoundError as exc:
        click.echo(str(exc), err=True)
        sys.exit(1)
    except EncryptedNTQQDatabaseError as exc:
        click.echo(str(exc), err=True)
        sys.exit(2)
    except Exception as exc:  # pragma: no cover - defensive path
        click.echo(f"初始化失败: {exc}", err=True)
        sys.exit(1)


from qq_cli.commands.collections import collections
from qq_cli.commands.contacts import contacts
from qq_cli.commands.decrypt import decrypt
from qq_cli.commands.emojis import emojis
from qq_cli.commands.files import files
from qq_cli.commands.history import history
from qq_cli.commands.init import init
from qq_cli.commands.members import members
from qq_cli.commands.search import search
from qq_cli.commands.sessions import sessions
from qq_cli.commands.stats import stats

cli.add_command(init)
cli.add_command(decrypt)
cli.add_command(contacts)
cli.add_command(members)
cli.add_command(sessions)
cli.add_command(history)
cli.add_command(search)
cli.add_command(stats)
cli.add_command(files)
cli.add_command(collections)
cli.add_command(emojis)


if __name__ == "__main__":
    cli()
