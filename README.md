# qq-cli

A CLI tool for reading your local NTQQ databases — query sessions, chat history, contacts, files, and more.

> Notice: This project is intended mainly for learning, research, and personal data handling. Only use it with your own account, your own device, and your own data, and assume the related risks yourself.

**Supported version: macOS QQ 6.9.93** (other versions untested)

## Project Structure

```
src/
├── __init__.py
├── main.py
├── commands/
│   ├── collections.py
│   ├── contacts.py
│   ├── decrypt.py
│   ├── emojis.py
│   ├── files.py
│   ├── history.py
│   ├── init.py
│   ├── members.py
│   └── sessions.py
├── core/
│   ├── config.py
│   ├── contacts.py
│   ├── context.py
│   ├── db.py
│   ├── decrypt.py
│   ├── live.py
│   ├── messages.py
│   └── protobuf.py
├── keys/
│   ├── find_qq_key_macos.c
│   └── scanner_macos.py
└── output/
    └── formatter.py
```

## Install

### npm (recommended)

The npm package ships a `darwin-arm64` binary directly:

```bash
npm install -g @hsn0918/qq-cli
qq-cli --help
```

If your local npm registry is not the official one, install from npm explicitly:

```bash
npm install -g @hsn0918/qq-cli --registry=https://registry.npmjs.org/
qq-cli --help
```

> The current npm package is built for macOS + Apple Silicon. The binary is built locally and bundled at publish time.

When publishing, use the official npm registry to avoid local mirror settings interfering:

```bash
npm login --registry=https://registry.npmjs.org/
npm publish --registry=https://registry.npmjs.org/ --access public
```

### Python / uv

```bash
uv tool install .
# or
uv run qq-cli --help
```

## Quick Start

```bash
uv run qq-cli init
uv run qq-cli sessions --limit 20
```

`init` automatically locates your QQ database, captures the runtime key, exports plaintext databases, and saves config to `~/.qq-cli/config.json`.

> If auto re-signing fails, follow the manual QQ.app re-signing steps in [DECRYPT_CN.md](./DECRYPT_CN.md), then re-run `init`.

The default mode is `live`: it decrypts only the databases needed for the current query into a temporary workspace. If you want the more stable path, export plaintext databases first and query those instead.

```bash
uv run qq-cli --mode live sessions --limit 20
```

Live mode does not write into `~/.qq-cli/decrypted`. It decrypts only the databases needed for the current query into a temporary workspace, then reuses the existing query pipeline.

If you already exported plaintext databases manually, point `qq-cli` at that directory explicitly:

```bash
uv run qq-cli --mode decrypted --decrypted-dir /path/to/decrypted sessions --limit 20
```

## Commands

```bash
uv run qq-cli init                              # Initialize (auto decrypt)
uv run qq-cli init --force --timeout 240        # Force re-initialize

uv run qq-cli contacts                          # List contacts
uv run qq-cli contacts --groups                 # List groups
uv run qq-cli members "Some Group"              # List group members
uv run qq-cli sessions --limit 20               # Recent sessions
uv run qq-cli --mode live sessions --limit 20   # Read raw encrypted NTQQ DBs
uv run qq-cli history "Someone" --limit 50      # Chat history
uv run qq-cli history "Some Group" --start-time "2026-04-01 00:00:00"
uv run qq-cli history "Some Group" --start-time "2026-04-01 00:00:00" --end-time "2026-04-16 23:59:59" --output ./history.json
uv run qq-cli search "keyword"                  # Search all messages
uv run qq-cli search "keyword" --chat "Someone" # Search in a specific chat
uv run qq-cli stats "Some Group"                # Chat statistics
uv run qq-cli stats "Some Group" --format text  # Statistics as text with bar chart
uv run qq-cli files --chat "Some Group"         # Files in chat
uv run qq-cli collections                       # Collections
uv run qq-cli emojis                            # Emojis
uv run qq-cli emojis --system                   # System emojis
```

If you already have the runtime `pKey`, you can decrypt directly:

```bash
uv run qq-cli decrypt --key 'your-runtime-pKey'
```

## How It Works

**`--mode auto`** — prefer plaintext databases under `~/.qq-cli/decrypted`; fall back to raw `nt_db` only when plaintext is missing.

**`--mode live`** — force reads from raw `nt_db`, require `db_key` in config or `QQ_CLI_KEY` env, decrypt only the databases touched by the current query into a temporary workspace, and clean up on exit.

**`--mode decrypted --decrypted-dir /path`** — read directly from the specified plaintext directory instead of the default `decrypted_dir`.

Once `init` or `decrypt` succeeds, commands like the following usually no longer depend on QQ being open (when using `--mode auto` or `--mode decrypted`):

```bash
uv run qq-cli sessions
uv run qq-cli history "Some Group"
uv run qq-cli contacts --groups
```

## Large Databases And Live Export

`nt_msg.db` is usually the largest database and can easily grow to hundreds of MB or several GB. Reading an already-exported plaintext database is just normal SQLite access and usually works fine.

The fragile part is the export step:

- `init` / `decrypt` runs `sqlcipher_export()` over the entire encrypted database
- for large `nt_msg.db`, export scans the whole database, not just recent messages
- if some pages, indexes, or WAL state are inconsistent, QQ may still run but export can fail:

```
Runtime error near line 7: database disk image is malformed
```

This means the local `nt_msg.db` content is inconsistent or partially damaged, not that the database is too large to open.

Live mode only reduces the cost of a full export before every query. It does not bypass corruption in the underlying database files.

## Troubleshooting

### If plaintext databases already exist, use them directly

Check whether `~/.qq-cli/decrypted` already contains `nt_msg.db`, `profile_info.db`, and other plaintext files. If it does:

```bash
uv run qq-cli sessions --limit 20
uv run qq-cli contacts --groups
uv run qq-cli history "Some Group" --limit 50
```

If these return data, the existing export is usable and you do not need to rerun `init`.

### If export fails only on one Mac

If the same account exports fine on another machine but this machine consistently fails on `nt_msg.db` with `database disk image is malformed`, the issue is most likely this machine's local `nt_msg.db`.

Options:

- keep using the plaintext databases that already work
- copy exported plaintext databases from a healthy machine
- back up the raw `nt_db` first, then attempt recovery on `nt_msg.db`

### Permission denied under `~/.qq-cli/decrypted`

If you see:

```
Permission denied: ~/.qq-cli/decrypted/xxx.db
```

This usually means `qq-cli init` or `qq-cli decrypt` was previously run with `sudo`, so the output directory is now owned by `root`. Fix it with:

```bash
sudo chown -R "$USER":staff ~/.qq-cli/decrypted
```