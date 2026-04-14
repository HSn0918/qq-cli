"""Collections listing."""

from __future__ import annotations

import click

from ..core.messages import load_collections
from ..output.formatter import output


@click.command("collections")
@click.option("--limit", default=30, help="返回数量")
@click.option("--format", "fmt", default="json", type=click.Choice(["json", "text"]), help="输出格式")
@click.pass_context
def collections(ctx, limit, fmt):
    """查看收藏记录。"""
    app = ctx.obj
    rows = load_collections(app.db_files, limit=limit)

    if fmt == "json":
        output(rows, "json")
        return

    lines = []
    for row in rows:
        title = row["title"] or row["summary"] or row["sid"]
        lines.append(f'[{row["updated_time"] or "-"}] {title}')
    output("\n".join(lines) if lines else "无结果", "text")
