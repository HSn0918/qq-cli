"""Chat statistics."""

from __future__ import annotations

import click

from qq_cli.core.contacts import resolve_chat_target
from qq_cli.core.messages import parse_time_input, stats_messages
from qq_cli.output.formatter import output


@click.command("stats")
@click.argument("chat_name")
@click.option("--start-time", default="", help="起始时间 YYYY-MM-DD [HH:MM[:SS]]")
@click.option("--end-time", default="", help="结束时间 YYYY-MM-DD [HH:MM[:SS]]")
@click.option("--format", "fmt", default="json", type=click.Choice(["json", "text"]), help="输出格式")
@click.pass_context
def stats(ctx, chat_name, start_time, end_time, fmt):
    """聊天统计分析。

    \b
    示例:
      qq-cli stats "某个群"
      qq-cli stats "张三" --start-time "2026-04-01" --format text
    """
    app = ctx.obj

    target = resolve_chat_target(chat_name, app.buddies, app.groups, app.recent_sessions())
    if not target:
        raise click.ClickException(f"找不到聊天对象: {chat_name}")

    start_ts = parse_time_input(start_time)
    end_ts = parse_time_input(end_time)

    result = stats_messages(app.db_files, target, app.buddies, start_ts=start_ts, end_ts=end_ts)

    if fmt == "json":
        output({
            "chat": target.display_name,
            "kind": target.kind,
            **result,
        }, "json")
    else:
        tag = " [群聊]" if target.kind == "group" else ""
        lines = [f"{target.display_name}{tag} 聊天统计", f"消息总数: {result['total']}"]
        if start_time or end_time:
            lines.append(f"时间范围: {start_time or '最早'} ~ {end_time or '最新'}")
        if result["top_senders"]:
            lines.append("\n发言排行 Top 10:")
            for s in result["top_senders"]:
                lines.append(f"  {s['name']}: {s['count']}")
        if result["hourly"]:
            lines.append("\n24 小时活跃分布:")
            max_count = max(result["hourly"].values())
            for h in range(24):
                count = result["hourly"].get(h, 0)
                bar = "█" * int(count / max_count * 30) if max_count else ""
                lines.append(f"  {h:02d}时 |{bar} {count}")
        output("\n".join(lines), "text")
