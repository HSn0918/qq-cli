"""Chat history."""

from __future__ import annotations

from pathlib import Path

import click

from qq_cli.core.contacts import resolve_chat_target
from qq_cli.core.messages import load_history, parse_time_input
from qq_cli.output.formatter import output


@click.command("history")
@click.argument("chat_name")
@click.option("--limit", default=50, help="返回数量")
@click.option("--offset", default=0, help="分页偏移量")
@click.option("--start-time", default="", help="起始时间 YYYY-MM-DD [HH:MM[:SS]]")
@click.option("--end-time", default="", help="结束时间 YYYY-MM-DD [HH:MM[:SS]]")
@click.option("--format", "fmt", default="json", type=click.Choice(["json", "text"]), help="输出格式")
@click.option("--output", "output_path", default="", help="将结果额外写入文件；内容按当前 --format 输出")
@click.pass_context
def history(ctx, chat_name, limit, offset, start_time, end_time, fmt, output_path):
    """查看指定聊天记录。"""
    app = ctx.obj

    if limit <= 0:
        raise click.ClickException("limit 必须大于 0")
    if offset < 0:
        raise click.ClickException("offset 不能小于 0")

    target = resolve_chat_target(chat_name, app.buddies, app.groups, app.recent_sessions())
    if not target:
        raise click.ClickException(f"找不到聊天对象: {chat_name}")

    start_ts = parse_time_input(start_time)
    end_ts = parse_time_input(end_time)
    rows = load_history(
        app.db_files,
        target,
        app.buddies,
        limit=limit,
        offset=offset,
        start_ts=start_ts,
        end_ts=end_ts,
    )

    if fmt == "json":
        payload = {
            "chat": target.display_name,
            "kind": target.kind,
            "count": len(rows),
            "offset": offset,
            "limit": limit,
            "messages": rows,
        }
    else:
        header = f"{target.display_name} 的消息记录（{len(rows)} 条）"
        body = []
        for row in rows:
            body.append(f'[{row["time"] or "-"}] {row["sender"]}: {row["text"]}')
        payload = header + "\n\n" + "\n".join(body) if body else f"{header}\n\n无结果"

    output(payload, fmt)
    if output_path:
        path = Path(output_path).expanduser()
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as handle:
            output(payload, fmt, file=handle)
