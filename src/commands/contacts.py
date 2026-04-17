"""List contacts or groups."""

from __future__ import annotations

import click

from qq_cli.core.contacts import merge_recent_contacts
from qq_cli.output.formatter import output


@click.command("contacts")
@click.option("--groups", is_flag=True, help="只显示群聊")
@click.option("--all", "include_all", is_flag=True, help="合并最近会话中的对象，而不只限于好友/群列表")
@click.option("--query", default="", help="按名称、nt_uid、uin、QID 搜索")
@click.option("--limit", default=100, show_default=True, help="返回数量；--all 时也会在合并后按此数量截断")
@click.option("--format", "fmt", default="json", type=click.Choice(["json", "text"]), help="输出格式")
@click.pass_context
def contacts(ctx, groups, include_all, query, limit, fmt):
    """列出联系人或群聊。

    默认只返回通讯录里的好友，或群列表里的群。
    传入 `--all` 后，会把最近会话里出现、但不在联系人/群列表中的对象也合并进结果。
    """
    app = ctx.obj
    items = app.groups if groups else app.buddies
    if include_all:
        items = merge_recent_contacts(
            items,
            app.recent_sessions(limit=max(limit, 1000)),
            groups=groups,
        )
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
            suffix = " [recent]" if item.get("source") == "recent_session" else ""
            lines.append(f'{item["display_name"]} ({item["group_uin"]}){suffix}')
        else:
            suffix = " [recent]" if item.get("source") == "recent_session" else ""
            lines.append(
                f'{item["display_name"]} '
                f'(uin={item["uin"]}, nt_uid={item["nt_uid"]}, qid={item["qid"] or "-"}){suffix}'
            )
    output("\n".join(lines) if lines else "无结果", "text")
