"""List contacts or groups."""

from __future__ import annotations

import click

from ..output.formatter import output


@click.command("contacts")
@click.option("--groups", is_flag=True, help="只显示群聊")
@click.option("--query", default="", help="按名称、nt_uid、uin、QID 搜索")
@click.option("--limit", default=100, help="返回数量")
@click.option("--format", "fmt", default="json", type=click.Choice(["json", "text"]), help="输出格式")
@click.pass_context
def contacts(ctx, groups, query, limit, fmt):
    """列出好友或群聊。"""
    app = ctx.obj
    items = app.groups if groups else app.buddies
    if query:
        needle = query.lower()
        filtered = []
        for item in items:
            values = [str(value or "").lower() for value in item.values()]
            if any(needle in value for value in values):
                filtered.append(item)
        items = filtered
    items = items[:limit]

    if fmt == "json":
        output(items, "json")
        return

    lines = []
    for item in items:
        if item["kind"] == "group":
            lines.append(f'{item["display_name"]} ({item["group_uin"]})')
        else:
            lines.append(
                f'{item["display_name"]} '
                f'(uin={item["uin"]}, nt_uid={item["nt_uid"]}, qid={item["qid"] or "-"})'
            )
    output("\n".join(lines) if lines else "无结果", "text")
