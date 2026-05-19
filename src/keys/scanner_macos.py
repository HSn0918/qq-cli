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


def _find_wrapper_node_path(qq_app: str) -> str | None:
    version_root = os.path.expanduser(
        "~/Library/Containers/com.tencent.qq/Data/Library/Application Support/QQ/versions"
    )
    candidates = []
    if os.path.isdir(version_root):
        for name in os.listdir(version_root):
            candidate = os.path.join(
                version_root,
                name,
                "QQUpdate.app",
                "Contents",
                "Resources",
                "app",
                "wrapper.node",
            )
            if os.path.isfile(candidate):
                candidates.append(candidate)
    if candidates:
        candidates.sort(key=lambda path: os.path.getmtime(path), reverse=True)
        return candidates[0]

    candidate = os.path.join(qq_app, "Contents", "Resources", "app", "wrapper.node")
    return candidate if os.path.isfile(candidate) else None


def _find_key_symbols_offline(wrapper_path: str) -> list[str]:
    """Scan wrapper.node on disk to find symbols that set the SQLCipher key.

    Locate SetDBKey / nt_sqlite3_key log strings in __cstring, then byte-scan
    __text for adrp+add pairs whose computed target hits one of those strings,
    and map each hit back to its containing symbol via LLDB. This avoids
    disassembling every unnamed_symbol, which on newer wrapper.node builds is
    too slow. Multiple candidates are returned because 6.9.80 uses a SetDBKey
    wrapper (v2 ABI) while 6.9.95+ uses nt_sqlite3_key (new ABI); the runtime
    callback is ABI-aware and probes both layouts.
    """
    scan_script_source = textwrap.dedent(
        """
        import lldb
        import struct
        import sys

        RESULT_PATH = sys.argv[1] if len(sys.argv) > 1 else "/tmp/qq-cli-sym.txt"

        TARGET_STRINGS = (
            "SetDBKey sqlite3_key failed",
            "SetDBKey sqlite3_key failed:{}",
            "nt_sqlite3_key_v2: db=%p",
            "nt_sqlite3_key: db=%p",
        )


        def _decode_adrp(instr_word, instr_addr):
            if (instr_word >> 31) & 1 != 1:
                return None
            if (instr_word >> 24) & 0x1F != 0x10:
                return None
            immlo = (instr_word >> 29) & 3
            immhi = (instr_word >> 5) & 0x7FFFF
            imm21 = (immhi << 2) | immlo
            if imm21 & (1 << 20):
                imm21 -= 1 << 21
            page_base = (instr_addr & ~0xFFF) + (imm21 << 12)
            rd = instr_word & 0x1F
            return rd, page_base


        def _decode_add_imm(instr_word):
            if (instr_word >> 23) & 0x1FF != 0b100100010:
                return None
            sh = (instr_word >> 22) & 1
            imm12 = (instr_word >> 10) & 0xFFF
            if sh:
                imm12 <<= 12
            rn = (instr_word >> 5) & 0x1F
            rd = instr_word & 0x1F
            return rd, rn, imm12


        def _find_subsection(parent, name):
            for sj in range(parent.GetNumSubSections()):
                sub = parent.GetSubSectionAtIndex(sj)
                if sub.GetName() == name:
                    return sub
            return None


        def _read_section(section):
            err = lldb.SBError()
            data = section.GetSectionData()
            size = data.GetByteSize()
            raw = bytearray()
            for off in range(0, size, 65536):
                chunk_sz = min(65536, size - off)
                buf = data.ReadRawData(err, off, chunk_sz)
                if err.Fail():
                    return None
                raw.extend(buf)
            return bytes(raw)


        def scan_symbols(debugger, command, result, internal_dict):
            target = debugger.GetSelectedTarget()
            if not target.IsValid():
                return
            module = target.GetModuleAtIndex(0)
            text_outer = module.FindSection("__TEXT")
            if not text_outer:
                return
            text_sub = _find_subsection(text_outer, "__text")
            cstring_sub = _find_subsection(text_outer, "__cstring")
            if not text_sub or not cstring_sub:
                return

            cstring_raw = _read_section(cstring_sub)
            if cstring_raw is None:
                return
            cstring_file_addr = cstring_sub.GetFileAddress()

            str_addr_to_label = {}
            for label in TARGET_STRINGS:
                idx = cstring_raw.find(label.encode("utf-8") + b"\\x00")
                if idx >= 0:
                    str_addr_to_label[cstring_file_addr + idx] = label
            if not str_addr_to_label:
                return

            text_raw = _read_section(text_sub)
            if text_raw is None:
                return
            text_file_addr = text_sub.GetFileAddress()
            n_words = len(text_raw) // 4
            words = struct.unpack("<" + "I" * n_words, text_raw[: n_words * 4])

            last_adrp = {}
            sym_hits = {}
            for i in range(n_words):
                w = words[i]
                addr = text_file_addr + i * 4
                adrp = _decode_adrp(w, addr)
                if adrp is not None:
                    last_adrp[adrp[0]] = (adrp[1], addr)
                    continue
                add = _decode_add_imm(w)
                if add is None:
                    continue
                _, rn, imm = add
                src = last_adrp.get(rn)
                if not src:
                    continue
                tgt = src[0] + imm
                label = str_addr_to_label.get(tgt)
                if not label:
                    continue
                sb_addr = target.ResolveFileAddress(src[1])
                symbol = sb_addr.GetSymbol()
                if not symbol.IsValid():
                    continue
                name = symbol.GetName() or ""
                if not name:
                    continue
                entry = sym_hits.setdefault(name, {"labels": set(), "count": 0})
                entry["labels"].add(label)
                entry["count"] += 1

            if not sym_hits:
                return

            def rank(item):
                name, info = item
                preferred = 0
                for idx, label in enumerate(TARGET_STRINGS):
                    if label in info["labels"]:
                        preferred = len(TARGET_STRINGS) - idx
                        break
                return (preferred, info["count"])

            ordered = sorted(sym_hits.items(), key=rank, reverse=True)
            with open(RESULT_PATH, "w") as f:
                for name, _ in ordered:
                    f.write(name + "\\n")


        def __lldb_init_module(debugger, internal_dict):
            debugger.HandleCommand("command script add -f scan.scan_symbols qq_cli_scan")
        """
    ).strip()

    import tempfile as _tempfile
    with _tempfile.TemporaryDirectory(prefix="qq-cli-scan-") as work_dir:
        script_path = os.path.join(work_dir, "scan.py")
        result_path = os.path.join(work_dir, "sym.txt")
        lldb_cmd_path = os.path.join(work_dir, "scan.lldb")

        with open(script_path, "w") as f:
            f.write(scan_script_source + "\n")
        # patch RESULT_PATH into the script
        with open(script_path) as f:
            src = f.read()
        src = src.replace(
            'sys.argv[1] if len(sys.argv) > 1 else "/tmp/qq-cli-sym.txt"',
            repr(result_path),
        )
        with open(script_path, "w") as f:
            f.write(src)

        with open(lldb_cmd_path, "w") as f:
            f.write(f"command script import {script_path}\n")
            f.write("qq_cli_scan\n")
            f.write("quit\n")

        try:
            subprocess.run(
                ["lldb", wrapper_path, "--batch", "-s", lldb_cmd_path],
                capture_output=True,
                text=True,
                timeout=60,
            )
        except Exception:
            return []

        if os.path.isfile(result_path):
            with open(result_path) as f:
                names = [ln.strip() for ln in f if ln.strip()]
            return names
    return []


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


        def _find_key_symbol(target):
            # Find unnamed symbol in wrapper.node that calls sqlite3_key/sqlite3_key_v2
            wrapper = None
            for i in range(target.GetNumModules()):
                m = target.GetModuleAtIndex(i)
                fname = m.GetFileSpec().GetFilename()
                if fname and fname.startswith("wrapper") and fname.endswith(".node"):
                    wrapper = m
                    break
            if not wrapper:
                return None

            for i in range(wrapper.GetNumSymbols()):
                sym = wrapper.GetSymbolAtIndex(i)
                if sym.GetType() != lldb.eSymbolTypeCode:
                    continue
                name = sym.GetName() or ""
                if "unnamed_symbol" not in name and "sqlite3_key" not in name:
                    continue
                addr = sym.GetStartAddress()
                if not addr.IsValid():
                    continue
                instructions = target.ReadInstructions(addr, 200)
                for j in range(instructions.GetSize()):
                    inst = instructions.GetInstructionAtIndex(j)
                    operands = inst.GetOperands(target) or ""
                    if "sqlite3_key" in operands:
                        return name
            return None


        _BP_SET = False


        def __lldb_init_module(debugger, internal_dict):
            pass


        def handle_stop(debugger, command, result, internal_dict):
            global _BP_SET
            if _BP_SET:
                return
            target = debugger.GetSelectedTarget()
            sym_name = _find_key_symbol(target)
            if not sym_name:
                return
            bp = target.BreakpointCreateByName(sym_name, "wrapper.node")
            bp.SetScriptCallbackFunction("qq_cli_lldb_hook.breakpoint_callback")
            _BP_SET = True


        def _try_read_key(process, ptr_hex, len_hex):
            if not ptr_hex or not len_hex:
                return None
            try:
                ptr = int(ptr_hex, 16)
                length = int(len_hex, 16)
            except ValueError:
                return None
            if length <= 0 or length > 128:
                return None
            data = _read(process, ptr, length)
            if len(data) != length:
                return None
            stripped = data.split(b"\\0", 1)[0]
            if not stripped:
                return None
            if any(b < 0x20 or b > 0x7e for b in stripped):
                return None
            return stripped.decode("latin1")


        def _walk_sqlite_path(process, x0_hex):
            if not x0_hex:
                return ""
            try:
                x0 = int(x0_hex, 16)
            except ValueError:
                return ""
            adb = _u64(process, x0 + 0x28)
            pbt = _u64(process, adb + 8) if adb else 0
            bts = _u64(process, pbt + 8) if pbt else 0
            pager = _u64(process, bts) if bts else 0
            z_filename = _u64(process, pager + 0xD0) if pager else 0
            return _read_c_string(process, z_filename)


        def breakpoint_callback(frame, bp_loc, internal_dict):
            process = frame.GetThread().GetProcess()
            regs = {{
                name: frame.FindRegister(name).GetValue()
                for name in ("x0", "x1", "x2", "x3")
            }}

            # v2 ABI (SetDBKey wrapper, 6.9.80): x0=db*, x2=key, x3=len
            v2_key = _try_read_key(process, regs["x2"], regs["x3"])
            v2_path = _walk_sqlite_path(process, regs["x0"]) if v2_key else ""

            # nt ABI (nt_sqlite3_key, 6.9.95+): x1=key, x2=len, x0 still db*
            nt_key = _try_read_key(process, regs["x1"], regs["x2"])
            nt_path = _walk_sqlite_path(process, regs["x0"]) if nt_key else ""

            now = time.strftime("%Y-%m-%d %H:%M:%S")
            _append_hit({{
                "captured_at": now,
                "v2_key": v2_key,
                "v2_path": v2_path,
                "nt_key": nt_key,
                "nt_path": nt_path,
            }})

            def _matches_target(path):
                if not path:
                    return False
                try:
                    return os.path.commonpath([TARGET_DB_DIR, os.path.realpath(path)]) == TARGET_DB_DIR
                except ValueError:
                    return False

            if v2_key and _matches_target(v2_path):
                with open(RESULT_PATH, "w", encoding="utf-8") as handle:
                    json.dump({{
                        "captured_at": now,
                        "db_path": v2_path,
                        "db_name": os.path.basename(v2_path),
                        "key": v2_key,
                        "key_len": len(v2_key),
                        "abi": "v2",
                    }}, handle, ensure_ascii=False, indent=2)
                    handle.write("\\n")
                return True

            if nt_key and _matches_target(nt_path):
                with open(RESULT_PATH, "w", encoding="utf-8") as handle:
                    json.dump({{
                        "captured_at": now,
                        "db_path": nt_path,
                        "db_name": os.path.basename(nt_path),
                        "key": nt_key,
                        "key_len": len(nt_key),
                        "abi": "nt",
                    }}, handle, ensure_ascii=False, indent=2)
                    handle.write("\\n")
                return True

            return False
        """
    ).strip()
    with open(module_path, "w", encoding="utf-8") as handle:
        handle.write(source)
        handle.write("\n")


def _write_lldb_commands(script_path: str, module_path: str, sym_names: list[str]) -> None:
    lines = [
        "settings set target.process.stop-on-sharedlibrary-events false",
        f"command script import {module_path}",
    ]
    for i, sym in enumerate(sym_names, start=1):
        lines.append(f"breakpoint set -s wrapper.node -n {sym}")
        lines.append(f"breakpoint command add -F qq_cli_lldb_hook.breakpoint_callback {i}")
    lines.extend([
        "process attach -n QQ --waitfor",
        "process continue",
    ])
    with open(script_path, "w", encoding="utf-8") as handle:
        handle.write("\n".join(lines))
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
    timeout: int,
) -> dict:
    # 在启动 LLDB 之前，先离线从磁盘上的 wrapper.node 扫出正确的 symbol 名
    sym_names: list[str] = []
    wrapper_path = _find_wrapper_node_path(qq_app)
    if wrapper_path:
        sym_names = _find_key_symbols_offline(wrapper_path)
    if not sym_names:
        # 回退到已知的 symbol（QQ 6.9.x arm64 老版本）
        sym_names = ["___lldb_unnamed_symbol372387"]

    # 杀掉已有的 QQ 进程（保证断点能在启动期触发）
    _kill_running_qq()

    with tempfile.TemporaryDirectory(prefix="qq-cli-lldb-") as work_dir:
        module_path = os.path.join(work_dir, "qq_cli_lldb_hook.py")
        script_path = os.path.join(work_dir, "commands.lldb")
        result_path = os.path.join(work_dir, "key-result.json")
        hits_path = os.path.join(work_dir, "hits.jsonl")

        _write_lldb_callback(module_path, target_db_dir, snapshot_dir, result_path, hits_path)
        _write_lldb_commands(script_path, module_path, sym_names)

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

        deadline = time.monotonic() + max(1, timeout)
        result_payload = None
        while time.monotonic() < deadline:
            if os.path.exists(result_path):
                try:
                    with open(result_path, encoding="utf-8") as handle:
                        result_payload = json.load(handle)
                except (OSError, json.JSONDecodeError):
                    result_payload = None
                if result_payload:
                    break
            if proc.poll() is not None:
                break
            time.sleep(0.5)

        if proc.poll() is None:
            proc.kill()
        try:
            stdout, stderr = proc.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            stdout, stderr = "", ""

        if result_payload:
            # Snapshot happens here — delay so QQ finishes startup and WAL checkpoints
            time.sleep(30)
            _copy_snapshot_dir(target_db_dir, snapshot_dir)
            result_payload["snapshot_dir"] = snapshot_dir
            result_payload["stdout"] = stdout
            result_payload["stderr"] = stderr
            result_payload["method"] = "lldb"
            result_payload["waited_for_checkpoint"] = True
            return result_payload

        combined = ((stdout or "") + "\n" + (stderr or "")).strip()
        hits_tail = _tail_text(hits_path, limit=8)
        detail = combined[-2000:] if combined else "无"
        raise RuntimeError(
            "等待 QQ 打开用户数据库超时。\n"
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

    return _extract_runtime_key_via_lldb(target_db_dir, snapshot_dir, qq_app, timeout)
