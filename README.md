# qq-cli

A CLI tool for reading your local NTQQ databases — query sessions, chat history, contacts, files, and more.

> Notice: This project is intended mainly for learning, research, and personal data handling. Only use it with your own account, your own device, and your own data, and assume the related risks yourself.

**Supported version: macOS QQ 6.9.93** (other versions untested)

## Quick Start

```bash
uv run qq-cli init
uv run qq-cli sessions --limit 20
uv run qq-cli --mode live sessions --limit 20
```

`init` automatically locates your QQ database, captures the runtime key, exports plaintext databases, and saves config to `~/.qq-cli/config.json`.

> If auto re-signing fails, follow the manual QQ.app re-signing steps in [DECRYPT_CN.md](./DECRYPT_CN.md), then re-run `init`.

The default mode is `live`, which decrypts only the databases needed for the current query into a temporary workspace. If you want the more stable path, you should still export plaintext databases first and query those plaintext databases.

An experimental live mode is also available:

```bash
uv run qq-cli --mode live sessions --limit 20
```

Live mode does not write into `~/.qq-cli/decrypted`. It decrypts only the databases needed for the current query into a temporary workspace, then reuses the existing query pipeline. It is also the default mode now.

If you already exported plaintext databases manually, you can also point `qq-cli` at that directory explicitly:

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
uv run qq-cli --mode live sessions --limit 20  # Experimental: read raw encrypted NTQQ DBs
uv run qq-cli history "Someone" --limit 50      # Chat history
uv run qq-cli history "Some Group" --start-time "2026-04-01 00:00:00"
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

If you explicitly pass `--mode auto`, query commands prefer plaintext databases under `~/.qq-cli/decrypted`. Only when plaintext databases are missing will `qq-cli` fall back to the raw `nt_db` directory.

That means once `init` or `decrypt` succeeds, later commands such as the following usually no longer depend on QQ being open when you use `--mode auto` or `--mode decrypted`:

```bash
uv run qq-cli sessions
uv run qq-cli history "Some Group"
uv run qq-cli contacts --groups
```

usually no longer depend on QQ being open and do not need to capture the runtime key again.

If you explicitly pass `--mode live`, `qq-cli` will:

- force reads from the raw `nt_db`
- require `db_key` in config or `QQ_CLI_KEY` in the environment
- decrypt only the databases touched by the current query into a temporary workspace
- clean up that temporary workspace when the process exits

If you explicitly pass `--mode decrypted --decrypted-dir /path/to/decrypted`, `qq-cli` will read directly from that plaintext directory instead of relying on the configured default `decrypted_dir`.

## Large Databases And Live Export

`nt_msg.db` is usually the largest database and can easily grow to hundreds of MB or several GB. Size alone is not the main problem. Reading an already-exported plaintext database is just normal SQLite access and usually works fine.

The fragile part is the export step:

- `init` / `decrypt` runs `sqlcipher_export()` over the entire encrypted database
- for large `nt_msg.db`, export scans the whole database, not just recent messages
- if some pages, indexes, or WAL state are inconsistent on this machine, QQ may still run, but export can fail with:

```text
Runtime error near line 7: database disk image is malformed
```

In practice this is closer to “the local `nt_msg.db` content is inconsistent or partially damaged” than “the database is too large to open”.

Live mode only reduces the cost of doing a full export before every query. It does not bypass corruption or inconsistency in the underlying database files. If the source pages are already damaged, live mode can fail during on-demand decryption as well.

## Troubleshooting

### If plaintext databases already exist, use them directly

Check whether `~/.qq-cli/decrypted` already contains `nt_msg.db`, `profile_info.db`, and other plaintext files.

If it does, prefer querying directly:

```bash
uv run qq-cli sessions --limit 20
uv run qq-cli contacts --groups
uv run qq-cli history "Some Group" --limit 50
```

If these commands return data, the existing plaintext export is already usable and you do not need to rerun `init`.

### If export fails only on one Mac

If the same account exports fine on another machine, but this machine consistently fails on `nt_msg.db` with `database disk image is malformed`, the most likely issue is this machine's local `nt_msg.db`, not the key, permissions, or `qq-cli` itself.

Practical next steps:

- keep using the plaintext databases that already work
- copy exported plaintext databases from a healthy machine
- back up the raw `nt_db` first, then attempt recovery on `nt_msg.db`

### Permission denied under `~/.qq-cli/decrypted`

If you see:

```text
Permission denied: ~/.qq-cli/decrypted/xxx.db
```

it usually means `qq-cli init` or `qq-cli decrypt` was previously run with `sudo`, so the output directory is now owned by `root`.

Fix it with:

```bash
sudo chown -R "$USER":staff ~/.qq-cli/decrypted
```
