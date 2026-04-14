# qq-cli

A CLI tool for reading your local NTQQ databases — query sessions, chat history, contacts, files, and more.

**Supported version: macOS QQ 6.9.93** (other versions untested)

## Quick Start

```bash
uv run qq-cli init
uv run qq-cli sessions --limit 20
```

`init` automatically locates your QQ database, captures the runtime key, exports plaintext databases, and saves config to `~/.qq-cli/config.json`.

> If auto re-signing fails, follow the manual QQ.app re-signing steps in [DECRYPT_CN.md](./DECRYPT_CN.md), then re-run `init`.

## Commands

```bash
uv run qq-cli init                              # Initialize (auto decrypt)
uv run qq-cli init --force --timeout 240        # Force re-initialize

uv run qq-cli contacts                          # List contacts
uv run qq-cli contacts --groups                 # List groups
uv run qq-cli members "Some Group"              # List group members
uv run qq-cli sessions --limit 20               # Recent sessions
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