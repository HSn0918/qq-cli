# qq-cli

读取本地 NTQQ 数据库的命令行工具，支持查会话、聊天记录、联系人、文件等。

## 快速开始

```bash
uv run qq-cli init
uv run qq-cli sessions --limit 20
```

`init` 会自动找到你的 QQ 数据库、抓取运行时密钥、导出明文库，配置写到 `~/.qq-cli/config.json`。

> 如果 `init` 自动补签名失败，先按 [DECRYPT_CN.md](./DECRYPT_CN.md) 手动给 QQ.app 补权限，再重新执行。

## 常用命令

```bash
uv run qq-cli init                              # 初始化（自动解密）
uv run qq-cli init --force --timeout 240        # 强制重新初始化

uv run qq-cli contacts                          # 列出联系人
uv run qq-cli contacts --groups                 # 列出群聊
uv run qq-cli members "某个群"                  # 列出群成员
uv run qq-cli sessions --limit 20               # 最近会话
uv run qq-cli history "张三" --limit 50         # 聊天记录
uv run qq-cli history "某个群" --start-time "2026-04-01 00:00:00"
uv run qq-cli files --chat "某个群"             # 聊天文件
uv run qq-cli collections                       # 收藏
uv run qq-cli emojis                            # 表情
uv run qq-cli emojis --system                   # 系统表情
```

如果已经手动拿到了运行时 `pKey`，也可以直接解密：

```bash
uv run qq-cli decrypt --key '你的运行时 pKey'
```