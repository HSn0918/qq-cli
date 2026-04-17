# qq-cli

读取本地 NTQQ 数据库的命令行工具，支持查会话、聊天记录、联系人、文件等。

> 声明：本项目主要用于学习、研究和个人数据处理，请仅在你本人账号、本人设备、本人数据范围内使用，并自行承担相关风险。

**支持版本：macOS QQ 6.9.93**（其他版本未经验证）

## 快速开始

```bash
uv run qq-cli init
uv run qq-cli sessions --limit 20
uv run qq-cli --mode live sessions --limit 20
```

`init` 会自动找到你的 QQ 数据库、抓取运行时密钥、导出明文库，配置写到 `~/.qq-cli/config.json`。

> 如果 `init` 自动补签名失败，先按 [DECRYPT_CN.md](./DECRYPT_CN.md) 手动给 QQ.app 补权限，再重新执行。

`qq-cli` 的默认模式是 `live`，会按需临时解密当前查询需要的数据库；如果你更看重稳定性，仍然建议先导出明文库，再基于明文库查询。

也提供实验性的 live 模式：

```bash
uv run qq-cli --mode live sessions --limit 20
```

live 模式不会写入 `~/.qq-cli/decrypted`，而是按需把当前查询需要的数据库临时解密到系统临时目录，再复用现有查询逻辑。它现在也是默认模式。

如果你已经手动导出了明文库，也可以显式指定目录：

```bash
uv run qq-cli --mode decrypted --decrypted-dir /path/to/decrypted sessions --limit 20
```

## 常用命令

```bash
uv run qq-cli init                              # 初始化（自动解密）
uv run qq-cli init --force --timeout 240        # 强制重新初始化

uv run qq-cli contacts                          # 列出联系人
uv run qq-cli contacts --groups                 # 列出群聊
uv run qq-cli members "某个群"                  # 列出群成员
uv run qq-cli sessions --limit 20               # 最近会话
uv run qq-cli --mode live sessions --limit 20  # 实验：直接读取原始加密库
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

## 工作方式

如果显式传入 `--mode auto`，`qq-cli` 会优先读取 `~/.qq-cli/decrypted` 下的明文数据库；如果明文库不存在，才会退回到原始 `nt_db` 目录。

这意味着一旦 `init` 或 `decrypt` 成功过一次，后续如果你改用 `--mode auto` 或 `--mode decrypted`，下面这些命令通常都不再依赖 QQ 正在运行：

```bash
uv run qq-cli sessions
uv run qq-cli history "某个群"
uv run qq-cli contacts --groups
```

通常都不再依赖 QQ 正在运行，也不需要重新抓 key。

如果显式传入 `--mode live`，则会：

- 强制从原始 `nt_db` 读取
- 要求配置里已有 `db_key`，或环境变量 `QQ_CLI_KEY` 可用
- 对本次查询实际访问到的数据库做临时解密
- 进程退出后自动清理临时目录

如果显式传入 `--mode decrypted --decrypted-dir /path/to/decrypted`，则会直接读取你指定的明文库目录，不依赖默认配置里的 `decrypted_dir`。

## 大库与实时导出

`nt_msg.db` 往往是最大的库，常见到数百 MB 甚至数 GB。库大本身不是问题，`qq-cli` 查询明文库时走的是普通 SQLite 读取；只要明文库已经导出成功，通常可以正常打开。

真正容易出问题的是“导出阶段”：

- `init` / `decrypt` 需要对整个加密库执行 `sqlcipher_export()`
- 对 `nt_msg.db` 这类大库，导出会扫描整库，而不只是读取最近消息
- 如果本机这份 `nt_msg.db` 某些页、索引或 WAL 状态不一致，即使 QQ 自己还能运行，导出时也可能报：

```text
Runtime error near line 7: database disk image is malformed
```

这类错误更接近“本机消息库内容异常或局部损坏”，而不是“数据库太大所以打不开”。

live 模式只能减少“先全量导出再查询”的成本，不能绕过库本身的损坏或不一致。如果底层库页已经异常，live 模式在按需解密时同样可能失败。

## 排障

### 已经有明文库，优先直接用

先看 `~/.qq-cli/decrypted` 是否已经存在 `nt_msg.db`、`profile_info.db` 等文件。

如果存在，优先直接运行查询命令：

```bash
uv run qq-cli sessions --limit 20
uv run qq-cli contacts --groups
uv run qq-cli history "某个群" --limit 50
```

只要这些命令能返回结果，就说明当前明文库可用，不需要重新执行 `init`。

### 只有某台机器导出失败

如果同一账号在另一台电脑能正常导出，而当前机器始终在 `nt_msg.db` 上报 `database disk image is malformed`，更可能是这台机器本地的 `nt_msg.db` 有问题，而不是 key、权限或 `qq-cli` 本身的问题。

可以优先考虑：

- 继续使用当前已经导出的明文库
- 从另一台正常机器复制导出的明文库
- 备份原始 `nt_db` 后，再尝试修复或恢复 `nt_msg.db`

### 权限问题

如果报错是：

```text
Permission denied: ~/.qq-cli/decrypted/xxx.db
```

这通常是之前用 `sudo` 执行过 `qq-cli init` 或 `qq-cli decrypt`，导致导出目录归属成了 `root`。

修正方式：

```bash
sudo chown -R "$USER":staff ~/.qq-cli/decrypted
```
