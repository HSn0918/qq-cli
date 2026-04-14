"""输出格式化。"""

import json
import sys


def output_json(data, file=None):
    file = file or sys.stdout
    json.dump(data, file, ensure_ascii=False, indent=2)
    file.write("\n")


def output_text(text, file=None):
    file = file or sys.stdout
    file.write(text)
    if not text.endswith("\n"):
        file.write("\n")


def output(data, fmt="json", file=None):
    if fmt == "json":
        output_json(data, file=file)
        return
    if isinstance(data, str):
        output_text(data, file=file)
        return
    if isinstance(data, dict) and "text" in data:
        output_text(data["text"], file=file)
        return
    output_json(data, file=file)
