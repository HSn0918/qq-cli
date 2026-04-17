"""Search messages by keyword."""

from __future__ import annotations

import click

from qq_cli.core.contacts import resolve_chat_target
from qq_cli.core.messages import parse_time_input, search_messages
from qq_cli.output.formatter import output


@click.command("search")
@click.argument("keyword")
@click.option("--chat", default="", help="限定聊天对象（不填则全库搜索）")
@click.option("--limit", default=50, help="返回数量")
@click.option("--offset", default=0, help="分页偏移量")
@click.option("--start-time", default="", help="起始时间 YYYY-MM-DD [HH:MM[:SS]]")
@click.option("--end-time", default="", help="结束时间 YYYY-MM-DD [HH:MM[:SS]]")
@click.option("--format", "fmt", default="json", type=click.Choice(["json", "text"]), help="输出格式")
@click.pass_context
def search(ctx, keyword, chat, limit, offset, start_time, end_time, fmt):
    """搜索消息内容。

    \b
    示例:
      qq-cli search "关键词"
      qq-cli search "关键词" --chat "某个群"
      qq-cli search "关键词" --start-time "2026-04-01" --limit 100
    """
    app = ctx.obj

    target = None
    if chat:
        target = resolve_chat_target(chat, app.buddies, app.groups, app.recent_sessions())
        if not target:
            raise click.ClickException(f"找不到聊天对象: {chat}")

    start_ts = parse_time_input(start_time)
    end_ts = parse_time_input(end_time)

    rows = search_messages(
        app.db_files,
        target,
        app.buddies,
        keyword=keyword,
        limit=limit,
        offset=offset,
        start_ts=start_ts,
        end_ts=end_ts,
    )

    scope = target.display_name if target else "全部消息"

    if fmt == "json":
        output({
            "scope": scope,
            "keyword": keyword,
            "count": len(rows),
            "offset": offset,
            "limit": limit,
            "results": rows,
        }, "json")
    else:
        if not rows:
            output(f'在 {scope} 中未找到包含"{keyword}"的消息', "text")
            return
        lines = [f'在 {scope} 中搜索"{keyword}"，找到 {len(rows)} 条结果:\n']
        for row in rows:
            lines.append(f'[{row["time"] or "-"}] {row["sender"]}: {row["text"]}')
        output("\n".join(lines), "text")
