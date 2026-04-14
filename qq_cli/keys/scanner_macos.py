"""macOS runtime key extraction for NTQQ via LLDB."""

from __future__ import annotations

import json
import os
import platform
import plistlib
import shutil
import subprocess
import tempfile
import textwrap
import time


DEFAULT_TIMEOUT = 120
FAST_SCAN_TIMEOUT = 20
STATE_DIR = os.path.expanduser("~/.qq-cli")


def _find_qq_app(app_path: str | None = None) -> str:
    candidates = []
    if app_path:
        candidates.append(os.path.abspath(os.path.expanduser(app_path)))
    candidates.extend(
        [
            "/Applications/QQ.app",
            os.path.expanduser("~/Applications/QQ.app"),
        ]
    )
    for candidate in candidates:
        if os.path.isdir(candidate):
            return candidate
    raise RuntimeError("未找到 QQ.app，请使用 --app-path 显式指定")


def _qq_exec_path(app_path: str) -> str:
    path = os.path.join(app_path, "Contents", "MacOS", "QQ")
    if not os.path.isfile(path):
        raise RuntimeError(f"QQ 可执行文件不存在: {path}")
    return path


def _get_entitlements(app_path: str) -> dict | None:
    try:
        result = subprocess.run(
            ["codesign", "-d", "--entitlements", ":-", app_path],
            capture_output=True,
            timeout=15,
        )
        if result.returncode == 0 and result.stdout:
            return plistlib.loads(result.stdout)
    except Exception:
        return None
    return None


def _has_debug_entitlement(app_path: str) -> bool:
    entitlements = _get_entitlements(app_path) or {}
    return bool(entitlements.get("com.apple.security.get-task-allow"))


def _resign_qq(app_path: str) -> None:
    entitlements = _get_entitlements(app_path) or {}
    entitlements["com.apple.security.get-task-allow"] = True
    ent_data = plistlib.dumps(entitlements, fmt=plistlib.FMT_XML)

    fd, ent_path = tempfile.mkstemp(prefix="qq-cli-ent-", suffix=".plist")
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(ent_data)
        result = subprocess.run(
            ["codesign", "--force", "--sign", "-", "--entitlements", ent_path, app_path],
            capture_output=True,
            text=True,
            timeout=60,
        )
    finally:
        os.unlink(ent_path)

    if result.returncode != 0:
        stderr = result.stderr.strip() or result.stdout.strip()
        raise RuntimeError(
            "自动为 QQ 添加 get-task-allow 失败。\n"
            f"{stderr}\n"
            "请使用管理员权限重新执行，或手动按文档对 QQ 重新签名。"
        )


def _refresh_launch_services(app_path: str) -> None:
    """重签名后刷新 Launch Services 缓存，确保 open 启动的是新签名版本。"""
    try:
        subprocess.run(
            ["/System/Library/Frameworks/CoreServices.framework/Frameworks/"
             "LaunchServices.framework/Support/lsregister",
             "-f", app_path],
            capture_output=True,
            timeout=15,
        )
    except Exception:
        pass


def _ensure_debuggable(app_path: str) -> bool:
    if _has_debug_entitlement(app_path):
        return False
    _resign_qq(app_path)
    _refresh_launch_services(app_path)
    return True


def _kill_running_qq() -> None:
    subprocess.run(["killall", "QQ"], capture_output=True, text=True, timeout=10)


def _copy_snapshot_dir(target_db_dir: str, snapshot_dir: str) -> None:
    os.makedirs(snapshot_dir, exist_ok=True)
    for name in os.listdir(target_db_dir):
        if not (
            name.endswith(".db")
            or name.endswith(".db-wal")
            or name.endswith(".db-shm")
            or name.endswith(".material")
        ):
            continue
        src = os.path.join(target_db_dir, name)
        if os.path.isfile(src):
            shutil.copy2(src, os.path.join(snapshot_dir, name))


def _find_running_qq_pid() -> int | None:
    try:
        result = subprocess.run(
            ["pgrep", "-x", "QQ"],
            capture_output=True,
            text=True,
            timeout=5,
        )
    except Exception:
        return None
    if result.returncode != 0:
        return None
    for line in (result.stdout or "").splitlines():
        line = line.strip()
        if line.isdigit():
            return int(line)
    return None


def _c_source_path() -> str:
    return os.path.join(os.path.dirname(__file__), "find_qq_key_macos.c")


def _c_binary_path() -> str:
    machine = platform.machine()
    out_dir = os.path.join(STATE_DIR, "bin")
    os.makedirs(out_dir, exist_ok=True)
    return os.path.join(out_dir, f"find_qq_key_macos.{machine}")


def _ensure_c_helper() -> str:
    source_path = _c_source_path()
    if not os.path.isfile(source_path):
        raise RuntimeError(f"缺少 C 扫描器源码: {source_path}")

    binary_path = _c_binary_path()
    needs_build = not os.path.isfile(binary_path)
    if not needs_build:
        try:
            needs_build = os.path.getmtime(binary_path) < os.path.getmtime(source_path)
        except OSError:
            needs_build = True

    if not needs_build:
        return binary_path

    result = subprocess.run(
        ["cc", "-O2", "-std=c11", "-o", binary_path, source_path],
        capture_output=True,
        text=True,
        timeout=60,
    )
    if result.returncode != 0:
        stderr = result.stderr.strip() or result.stdout.strip()
        raise RuntimeError(f"编译 QQ C 扫描器失败: {stderr}")
    os.chmod(binary_path, 0o755)
    return binary_path


def _extract_runtime_key_via_c_scan(db_dir: str, snapshot_dir: str, timeout: int) -> dict | None:
    pid = _find_running_qq_pid()
    if not pid:
        return None

    try:
        helper = _ensure_c_helper()
    except Exception:
        return None

    try:
        result = subprocess.run(
            [helper, str(pid), db_dir],
            capture_output=True,
            text=True,
            timeout=max(5, min(timeout, FAST_SCAN_TIMEOUT)),
        )
    except Exception:
        return None

    if result.returncode != 0:
        return None

    stdout = (result.stdout or "").strip()
    if not stdout:
        return None

    try:
        payload = json.loads(stdout.splitlines()[-1])
    except json.JSONDecodeError:
        return None

    if not payload.get("db_path") or not payload.get("key"):
        return None

    _copy_snapshot_dir(db_dir, snapshot_dir)
    payload["snapshot_dir"] = snapshot_dir
    payload["stdout"] = result.stdout
    payload["stderr"] = result.stderr
    payload["method"] = "c_scan"
    return payload


def _write_lldb_callback(module_path: str, target_db_dir: str, snapshot_dir: str, result_path: str, hits_path: str) -> None:
    source = textwrap.dedent(
        f"""
        import json
        import os
        import shutil
        import struct
        import time
        import lldb

        TARGET_DB_DIR = {os.path.realpath(target_db_dir)!r}
        SNAPSHOT_DIR = {snapshot_dir!r}
        RESULT_PATH = {result_path!r}
        HITS_PATH = {hits_path!r}


        def _read(process, addr, size):
            err = lldb.SBError()
            data = process.ReadMemory(addr, size, err)
            if not err.Success() or data is None:
                return b""
            return data


        def _u64(process, addr):
            data = _read(process, addr, 8)
            if len(data) != 8:
                return 0
            return struct.unpack("<Q", data)[0]


        def _read_c_string(process, addr, limit=1024):
            data = _read(process, addr, limit)
            if not data:
                return ""
            return data.split(b"\\0", 1)[0].decode("utf-8", "ignore")


        def _append_hit(info):
            with open(HITS_PATH, "a", encoding="utf-8") as handle:
                handle.write(json.dumps(info, ensure_ascii=False) + "\\n")


        def _copy_snapshot():
            os.makedirs(SNAPSHOT_DIR, exist_ok=True)
            for name in os.listdir(TARGET_DB_DIR):
                if not (
                    name.endswith(".db")
                    or name.endswith(".db-wal")
                    or name.endswith(".db-shm")
                    or name.endswith(".material")
                ):
                    continue
                src = os.path.join(TARGET_DB_DIR, name)
                if os.path.isfile(src):
                    shutil.copy2(src, os.path.join(SNAPSHOT_DIR, name))


        def breakpoint_callback(frame, bp_loc, internal_dict):
            process = frame.GetThread().GetProcess()
            regs = {{
                name: frame.FindRegister(name).GetValue()
                for name in ("x0", "x1", "x2", "x3")
            }}
            if not regs["x0"] or not regs["x2"] or not regs["x3"]:
                return False

            x0 = int(regs["x0"], 16)
            x2 = int(regs["x2"], 16)
            x3 = int(regs["x3"], 16)
            if x3 <= 0 or x3 > 128:
                return False

            key_bytes = _read(process, x2, x3)
            if len(key_bytes) != x3:
                return False

            key = key_bytes.split(b"\\0", 1)[0].decode("latin1", "ignore")
            if not key:
                return False
            if any(ord(ch) < 32 or ord(ch) > 126 for ch in key):
                return False

            adb = _u64(process, x0 + 0x28)
            pbt = _u64(process, adb + 8) if adb else 0
            bts = _u64(process, pbt + 8) if pbt else 0
            pager = _u64(process, bts) if bts else 0
            z_filename = _u64(process, pager + 0xD0) if pager else 0
            path = _read_c_string(process, z_filename)

            info = {{
                "captured_at": time.strftime("%Y-%m-%d %H:%M:%S"),
                "db_path": path,
                "db_name": os.path.basename(path) if path else "",
                "key": key,
                "key_len": len(key),
                "z_db_name": regs["x1"],
            }}
            _append_hit(info)

            if not path:
                return False

            try:
                matched = os.path.commonpath([TARGET_DB_DIR, os.path.realpath(path)]) == TARGET_DB_DIR
            except ValueError:
                matched = False

            if not matched:
                return False

            _copy_snapshot()
            with open(RESULT_PATH, "w", encoding="utf-8") as handle:
                json.dump(info, handle, ensure_ascii=False, indent=2)
                handle.write("\\n")
            return True
        """
    ).strip()
    with open(module_path, "w", encoding="utf-8") as handle:
        handle.write(source)
        handle.write("\n")


def _write_lldb_commands(script_path: str, module_path: str) -> None:
    commands = textwrap.dedent(
        f"""
        settings set target.process.stop-on-sharedlibrary-events false
        command script import {module_path}
        breakpoint set -s wrapper.node -n ___lldb_unnamed_symbol372387
        breakpoint command add -F qq_cli_lldb_hook.breakpoint_callback 1
        process attach -n QQ --waitfor
        process continue
        """
    ).strip()
    with open(script_path, "w", encoding="utf-8") as handle:
        handle.write(commands)
        handle.write("\n")


def _tail_text(path: str, limit: int = 10) -> str:
    if not os.path.exists(path):
        return ""
    with open(path, encoding="utf-8") as handle:
        lines = handle.readlines()
    return "".join(lines[-limit:]).strip()


def _extract_runtime_key_via_lldb(
    target_db_dir: str,
    snapshot_dir: str,
    qq_app: str,
    qq_exec: str,
    timeout: int,
) -> dict:
    # 杀掉已有的 QQ 进程（需要重签名时必须重启；auto 时也重启保证断点能在启动期触发）
    _kill_running_qq()

    with tempfile.TemporaryDirectory(prefix="qq-cli-lldb-") as work_dir:
        module_path = os.path.join(work_dir, "qq_cli_lldb_hook.py")
        script_path = os.path.join(work_dir, "commands.lldb")
        result_path = os.path.join(work_dir, "key-result.json")
        hits_path = os.path.join(work_dir, "hits.jsonl")

        _write_lldb_callback(module_path, target_db_dir, snapshot_dir, result_path, hits_path)
        _write_lldb_commands(script_path, module_path)

        # LLDB 先启动，用 --waitfor 等待 QQ 进程出现后立刻 attach
        proc = subprocess.Popen(
            ["lldb", "--batch", "-s", script_path],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )

        # 等 LLDB 进入 --waitfor 状态再启动 QQ，否则 QQ 进程出现时 LLDB 还没准备好会错过
        # --waitfor 通常 1-2 秒内就绪，等 3 秒留足余量
        time.sleep(3)
        subprocess.Popen(["open", qq_app])

        try:
            stdout, stderr = proc.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.communicate()
            raise RuntimeError(
                "等待 QQ 打开用户数据库超时。\n"
                "请登录 QQ 后重试 qq-cli init。"
            )

        if os.path.exists(result_path):
            with open(result_path, encoding="utf-8") as handle:
                payload = json.load(handle)
            payload["snapshot_dir"] = snapshot_dir
            payload["stdout"] = stdout
            payload["stderr"] = stderr
            payload["method"] = "lldb"
            return payload

        combined = ((stdout or "") + "\n" + (stderr or "")).strip()
        hits_tail = _tail_text(hits_path, limit=8)
        detail = combined[-2000:] if combined else "无"
        raise RuntimeError(
            "未能在启动期捕获目标 nt_db 的运行时 key。\n"
            f"目标目录: {target_db_dir}\n"
            f"最近命中:\n{hits_tail or '无'}\n"
            f"LLDB 输出:\n{detail}"
        )


def extract_runtime_key(
    db_dir: str,
    snapshot_dir: str,
    app_path: str | None = None,
    timeout: int = DEFAULT_TIMEOUT,
    strategy: str = "auto",
) -> dict:
    qq_app = _find_qq_app(app_path)
    qq_exec = _qq_exec_path(qq_app)
    target_db_dir = os.path.realpath(db_dir)

    if not os.path.isdir(target_db_dir):
        raise RuntimeError(f"NTQQ 数据目录不存在: {target_db_dir}")

    resigned = _ensure_debuggable(qq_app)
    os.makedirs(snapshot_dir, exist_ok=True)

    if strategy not in {"auto", "c_scan", "lldb"}:
        raise RuntimeError(f"不支持的抓取策略: {strategy}")

    if strategy in {"auto", "c_scan"} and not resigned:
        payload = _extract_runtime_key_via_c_scan(target_db_dir, snapshot_dir, timeout)
        if payload:
            return payload
        if strategy == "c_scan":
            raise RuntimeError("C 快速扫描未能从当前 QQ 进程提取到运行时 key。")

    return _extract_runtime_key_via_lldb(target_db_dir, snapshot_dir, qq_app, qq_exec, timeout)
