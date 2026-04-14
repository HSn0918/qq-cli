"""qq-cli 入口。"""

from __future__ import annotations

import sys

import click

from . import __version__
from .core.context import AppContext
from .core.db import EncryptedNTQQDatabaseError


@click.group()
@click.version_option(version=__version__, prog_name="qq-cli")
@click.option(
    "--config",
    "config_path",
    default=None,
    envvar="QQ_CLI_CONFIG",
    help="config.json 路径（默认自动查找）",
)
@click.pass_context
def cli(ctx, config_path):
    """QQ CLI — 查询 NTQQ 本地数据库。"""
    if ctx.invoked_subcommand in ("init", "version"):
        return

    try:
        ctx.obj = AppContext(config_path)
    except FileNotFoundError as exc:
        click.echo(str(exc), err=True)
        sys.exit(1)
    except EncryptedNTQQDatabaseError as exc:
        click.echo(str(exc), err=True)
        sys.exit(2)
    except Exception as exc:  # pragma: no cover - defensive path
        click.echo(f"初始化失败: {exc}", err=True)
        sys.exit(1)


from .commands.collections import collections
from .commands.contacts import contacts
from .commands.decrypt import decrypt
from .commands.emojis import emojis
from .commands.files import files
from .commands.history import history
from .commands.init import init
from .commands.members import members
from .commands.sessions import sessions

cli.add_command(init)
cli.add_command(decrypt)
cli.add_command(contacts)
cli.add_command(members)
cli.add_command(sessions)
cli.add_command(history)
cli.add_command(files)
cli.add_command(collections)
cli.add_command(emojis)


if __name__ == "__main__":
    cli()
