# qq-cli

面向本地 NTQQ 数据库的命令行查询工具，结构参考 `wechat-cli`，但数据模型切换为 NTQQ 的多库设计。

当前版本已经支持在 macOS 上直接执行 `qq-cli init`：

- 自动定位用户 `nt_db`
- 启动 QQ 并在运行期抓取当前用户库的 `pKey`
- 自动快照原始数据库
- 自动导出明文数据库

破解/解密相关说明已经单独拆到 [`DECRYPT_CN.md`](./DECRYPT_CN.md)，里面包含：

- `qq-cli init` 的自动抓 key + 自动解密流程
- `qq-cli decrypt` 的手动解密方式
- QQ.app 的手动重签名步骤
- 真实 QQ 客户端验证结果
- 常见超时与签名问题的排障说明

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

如果 QQ.app 还没有 `get-task-allow` 调试权限，`qq-cli init` 会先尝试自动补签名；这一步通常需要管理员权限。自动补签失败时，可以直接按 [`DECRYPT_CN.md`](./DECRYPT_CN.md) 里的“手动重签名 QQ.app”步骤处理。

## 破解与解密

最常用的方式是直接执行：

```bash
uv run qq-cli init
```

这条命令会自动完成：

- 定位真实 `nt_db`
- 启动 QQ 并抓取运行时 `pKey`
- 导出明文数据库
- 写入 `~/.qq-cli/config.json`

更完整的破解/解密说明、真实验证记录、手动 `decrypt` 用法和排障说明见 [`DECRYPT_CN.md`](./DECRYPT_CN.md)。
