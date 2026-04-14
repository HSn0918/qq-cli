"""Emoji listing."""

from __future__ import annotations

import click

from ..core.messages import load_emojis
from ..output.formatter import output


@click.command("emojis")
@click.option("--system", is_flag=True, help="查看系统表情库，而不是收藏表情")
@click.option("--limit", default=50, help="返回数量")
@click.option("--format", "fmt", default="json", type=click.Choice(["json", "text"]), help="输出格式")
@click.pass_context
def emojis(ctx, system, limit, fmt):
    """查看收藏表情或系统表情。"""
    app = ctx.obj
    rows = load_emojis(app.db_files, limit=limit, system=system)

    if fmt == "json":
        output(rows, "json")
        return

    lines = []
    for row in rows:
        if system:
            lines.append(f'{row["emoji_id"]}: {row["description"]}')
        else:
            lines.append(f'{row["file_name"]} -> {row["local_path"] or row["download_url"]}')
    output("\n".join(lines) if lines else "无结果", "text")
