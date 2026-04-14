# qq-cli

面向本地 NTQQ 数据库的命令行查询工具，结构参考 `wechat-cli`，但数据模型切换为 NTQQ 的多库设计。

当前版本已经支持在 macOS 上直接执行 `qq-cli init`：

- 自动定位用户 `nt_db`
- 启动 QQ 并在运行期抓取当前用户库的 `pKey`
- 自动快照原始数据库
- 自动导出明文数据库

真实 NTQQ 原始库通常不能直接被 `sqlite3` 打开，需要先参照 QQDecrypt 的流程去掉 1024 字节自定义头，再按 SQLCipher 参数和运行时 `pKey` 导出明文数据库。不同 QQ 版本、不同数据库命中的 `pKey` 长度可能不同，不应再假设固定为 `32` 字节。

当前版本直接读取以下数据库：

- `nt_msg.db`
- `profile_info.db`
- `group_info.db`
- `files_in_chat.db`
- `rich_media.db`
- `collection.db`
- `emoji.db`

## 已实现命令

```bash
uv run qq-cli init
uv run qq-cli decrypt --key 'runtime-pKey'
uv run qq-cli contacts
uv run qq-cli contacts --groups
uv run qq-cli members "某个群"
uv run qq-cli sessions --limit 20
uv run qq-cli history "张三" --limit 50
uv run qq-cli history "某个群" --start-time "2026-04-01 00:00:00"
uv run qq-cli files --chat "某个群"
uv run qq-cli collections
uv run qq-cli emojis
uv run qq-cli emojis --system
```

## 配置

首次运行：

```bash
uv run qq-cli init
```

默认配置写入 `~/.qq-cli/config.json`，核心字段：

```json
{
  "db_dir": "/path/to/nt_db",
  "decrypted_dir": "/path/to/plaintext-dbs",
  "db_key": "runtime-pKey"
}
```

也可以显式指定：

```bash
uv run qq-cli init --db-dir /path/to/nt_db
uv run qq-cli --config /path/to/config.json sessions
```

推荐直接初始化：

```bash
uv run qq-cli init
uv run qq-cli sessions
```

如果你已经拿到了运行时 `pKey`，也可以单独解密：

```bash
export QQ_CLI_KEY='你的运行时 pKey'
uv run qq-cli decrypt --key-env QQ_CLI_KEY
uv run qq-cli sessions
```

也可以显式指定导出目录：

```bash
uv run qq-cli init --db-dir /path/to/nt_db --decrypted-dir /tmp/qq-cli-decrypted
uv run qq-cli decrypt --key '你的运行时 pKey' --out-dir /tmp/qq-cli-decrypted
uv run qq-cli sessions
```

如果 QQ.app 还没有 `get-task-allow` 调试权限，`qq-cli init` 会先尝试自动补签名；这一步通常需要管理员权限。

## 真实验证

已经在 macOS 上对真实 QQ 客户端做过一轮端到端验证，不走 mock 或测试数据：

```bash
uv run qq-cli init --force --timeout 240
uv run qq-cli sessions --limit 5
uv run qq-cli contacts --groups --limit 5
uv run qq-cli members "某个群"
uv run qq-cli history "某个群" --limit 10
```

验证结果：

- `init` 能自动定位用户 `nt_db`、抓取运行时 key、写入 `~/.qq-cli/config.json`
- `init` 完成后会自动导出 `nt_msg`、`profile_info`、`group_info`、`emoji`、`collection`、`files_in_chat`、`rich_media`
- 实测用户 `nt_db` 的运行时 key 长度可能是 `16`，不要再假设固定 `32` 字节
- `sessions` 能返回真实最近会话
- `contacts --groups` 能列出真实群聊
- `members` 能列出真实群成员和管理员
- `history` 已经能恢复文本、图片占位、引用消息、聊天记录卡片等常见内容

如果第一次 `init` 超时，常见原因是 QQ 已经启动但尚未完成前台初始化；把 QQ 激活到前台后重试即可。

## 数据来源

实现时参考了以下公开资料：

- [QQNT 数据库存放位置与结构概览](https://lengyue.me/2023/09/19/ntqq-db/)
- [QQDecrypt: 读取数据库说明](https://qqbackup.github.io/QQDecrypt/view/read_db.html)
- [QQDecrypt: 消息导出说明](https://qqbackup.github.io/QQDecrypt/view/message_export.html)
- [QQDecrypt: nt_msg.db](https://qqbackup.github.io/QQDecrypt/view/db_file_analysis/nt_msg.db.html)
- [QQDecrypt: profile_info.db](https://qqbackup.github.io/QQDecrypt/view/db_file_analysis/profile_info.db.html)
- [QQDecrypt: group_info.db](https://qqbackup.github.io/QQDecrypt/view/db_file_analysis/group_info.db.html)
- [QQDecrypt: emoji.db](https://qqbackup.github.io/QQDecrypt/view/db_file_analysis/emoji.db.html)
- [QQDecrypt: collection.db](https://qqbackup.github.io/QQDecrypt/view/db_file_analysis/collection.db.html)
- [QQDecrypt: files_in_chat.db](https://qqbackup.github.io/QQDecrypt/view/db_file_analysis/files_in_chat.db.html)
- [QQDecrypt: rich_media.db](https://qqbackup.github.io/QQDecrypt/view/db_file_analysis/rich_media.db.html)
- [QQDecrypt: NTQQ (macOS ARM) 解密](https://qqbackup.github.io/QQDecrypt/decrypt/NTQQ%20(macOS%20ARM).html)
- [QQDecrypt: 解密数据库](https://qqbackup.github.io/QQDecrypt/decrypt/decode_db.html)

## 设计取舍

- macOS 版 `qq-cli init` 现在会直接启动 QQ、命中用户 `nt_db`、抓取运行时 key，然后立即解密，不再要求手工 LLDB。
- `decrypt` 命令仍保留，流程参照 QQDecrypt：先移除 1024 字节头，再按 SQLCipher 参数导出明文库。
- `40800` / `40051` protobuf 采用“字段驱动的尽力解析”，优先恢复文本、文件名、媒体路径、引用内容。
- 对不同 QQNT 版本的字段漂移做了保守兼容：查询前先检查表和列是否存在，不假设所有列始终都在。
