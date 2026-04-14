"""Attachment listing."""

from __future__ import annotations

import click

from ..core.contacts import resolve_chat_target
from ..core.messages import load_files
from ..output.formatter import output


@click.command("files")
@click.option("--chat", default="", help="按聊天对象过滤")
@click.option("--limit", default=50, help="返回数量")
@click.option("--format", "fmt", default="json", type=click.Choice(["json", "text"]), help="输出格式")
@click.pass_context
def files(ctx, chat, limit, fmt):
    """查看聊天文件与媒体路径。"""
    app = ctx.obj
    target = None
    if chat:
        target = resolve_chat_target(chat, app.buddies, app.groups, app.recent_sessions())
        if not target:
            raise click.ClickException(f"找不到聊天对象: {chat}")

    rows = load_files(app.db_files, app.buddies, app.groups, limit=limit, target=target)

    if fmt == "json":
        output(rows, "json")
        return

    lines = []
    for row in rows:
        lines.append(
            f'[{row["time"] or "-"}] {row["chat_name"]} {row["file_name"] or "-"}\n'
            f'  path={row["file_path"] or "-"}'
        )
    output("\n\n".join(lines) if lines else "无结果", "text")
