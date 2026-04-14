"""Group member listing."""

from __future__ import annotations

import click

from ..core.contacts import load_group_members, resolve_chat_target
from ..output.formatter import output


@click.command("members")
@click.argument("group_name")
@click.option("--include-exited", is_flag=True, help="包含已退群成员")
@click.option("--format", "fmt", default="json", type=click.Choice(["json", "text"]), help="输出格式")
@click.pass_context
def members(ctx, group_name, include_exited, fmt):
    """查看群成员。"""
    app = ctx.obj
    target = resolve_chat_target(group_name, app.buddies, app.groups, app.recent_sessions())
    if not target or target.kind != "group" or target.group_uin is None:
        raise click.ClickException(f"找不到群聊: {group_name}")

    rows = load_group_members(app.db_files, target.group_uin)
    if not include_exited:
        rows = [row for row in rows if not row["is_exited"]]

    if fmt == "json":
        output(
            {
                "group": target.display_name,
                "group_uin": target.group_uin,
                "count": len(rows),
                "members": rows,
            },
            "json",
        )
        return

    lines = [f'{row["display_name"]} ({row["uin"] or row["nt_uid"]})' for row in rows]
    output("\n".join(lines) if lines else "无结果", "text")
