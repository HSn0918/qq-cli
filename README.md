# qq-cli

`qq-cli` is a local NTQQ database CLI inspired by `wechat-cli`, but adapted to NTQQ's multi-database layout.

It supports querying decrypted NTQQ data such as:

- `nt_msg.db`
- `profile_info.db`
- `group_info.db`
- `files_in_chat.db`
- `rich_media.db`
- `collection.db`
- `emoji.db`

## Quick Start

This project uses `uv`.

```bash
uv run qq-cli init
uv run qq-cli sessions --limit 20
```

On macOS, `qq-cli init` can:

- locate the real user `nt_db`
- launch QQ and capture the runtime `pKey`
- snapshot the raw databases
- decrypt them into plaintext SQLite files
- save config to `~/.qq-cli/config.json`

## Common Commands

```bash
uv run qq-cli init
uv run qq-cli decrypt --key 'runtime-pKey'
uv run qq-cli contacts
uv run qq-cli contacts --groups
uv run qq-cli members "Some Group"
uv run qq-cli sessions --limit 20
uv run qq-cli history "Some Chat" --limit 50
uv run qq-cli files --chat "Some Group"
uv run qq-cli collections
uv run qq-cli emojis
```

## Docs

- Chinese README: [README_CN.md](./README_CN.md)
- Decrypt guide: [DECRYPT_CN.md](./DECRYPT_CN.md)

## Notes

- `qq-cli` supports automatic runtime key capture and decryption on macOS.
- This is not an offline brute-force decryptor. The key point is obtaining the real runtime `pKey` from a running QQ process.
- Different QQ versions may expose different key lengths. Do not assume a fixed `32`-byte key.
