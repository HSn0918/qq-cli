"""Recent session listing."""

from __future__ import annotations

import click

from ..output.formatter import output


@click.command("sessions")
@click.option("--limit", default=20, help="返回的会话数量")
@click.option("--format", "fmt", default="json", type=click.Choice(["json", "text"]), help="输出格式")
@click.pass_context
def sessions(ctx, limit, fmt):
    """查看最近会话。"""
    app = ctx.obj
    rows = app.recent_sessions(limit=limit)[:limit]
    if fmt == "json":
        output(rows, "json")
        return

    lines = []
    for row in rows:
        sender = f'{row["sender"]}: ' if row["sender"] else ""
        lines.append(f'[{row["time"] or "-"}] {row["chat_name"]}\n  {sender}{row["last_message"]}')
    output("\n\n".join(lines) if lines else "无结果", "text")
