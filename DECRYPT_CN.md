# 破解与解密说明

这份文档只讲 `qq-cli` 的破解/解密链路，不重复介绍查询命令本身。

## 结论

`qq-cli` 现在支持在 macOS 上直接执行：

```bash
uv run qq-cli init
```

它会自动完成以下步骤：

- 自动定位用户 `nt_db`
- 检查并补 `QQ.app` 的 `get-task-allow`
- 启动或重启 QQ
- 在运行时抓取当前用户数据库的 `pKey`
- 快照原始数据库
- 导出明文数据库
- 把 `db_dir`、`decrypted_dir`、`db_key` 写入 `~/.qq-cli/config.json`

也就是说，当前流程已经不是“手工 LLDB + 手工解密”，而是一键初始化。

## 自动破解

推荐直接执行：

```bash
uv run qq-cli init
```

如果你想覆盖已有配置，可以加：

```bash
uv run qq-cli init --force --timeout 240
```

默认配置文件：

```json
{
  "db_dir": "/path/to/nt_db",
  "decrypted_dir": "/path/to/plaintext-dbs",
  "db_key": "runtime-pKey"
}
```

默认写入路径为：

- `~/.qq-cli/config.json`
- `~/.qq-cli/decrypted/`

如果 `init` 自动补签名失败，可以先按下面的“手动重签名 QQ.app”处理，再重新执行 `uv run qq-cli init --force`。

## 手动重签名 QQ.app

如果 QQ.app 没有 `get-task-allow`，LLDB 无法附加，`qq-cli init` 就拿不到运行时 `pKey`。这种情况下可以手动补签名：

```bash
# 1. 退出 QQ
killall QQ 2>/dev/null

# 2. 导出 QQ 当前权限
codesign -d --entitlements - --xml /Applications/QQ.app > qq_ent.plist

# 3. 验证 plist 格式
plutil -lint qq_ent.plist

# 4. 清理旧字段（如果没有会忽略）
/usr/libexec/PlistBuddy -c "Delete :com.apple.security.get-task-allow" qq_ent.plist 2>/dev/null || true

# 5. 添加调试权限
/usr/libexec/PlistBuddy -c "Add :com.apple.security.get-task-allow bool true" qq_ent.plist

# 6. 用修改后的权限重新签名
codesign --force --sign - --entitlements qq_ent.plist /Applications/QQ.app

# 7. 验证权限是否生效
codesign -d --entitlements - --xml /Applications/QQ.app 2>/dev/null | grep get-task-allow -A1

# 8. 清理临时文件
rm qq_ent.plist

# 9. 重启 QQ
open /Applications/QQ.app

# 10. 重新执行初始化
uv run qq-cli init --force
```

如果你的 QQ 不在 `/Applications/QQ.app`，把上面的路径替换成真实安装路径即可。

## 手动解密

如果你已经拿到了运行时 `pKey`，也可以绕过 `init`，直接执行解密：

```bash
export QQ_CLI_KEY='你的运行时 pKey'
uv run qq-cli decrypt --key-env QQ_CLI_KEY
```

或者：

```bash
uv run qq-cli decrypt --key '你的运行时 pKey'
```

也可以只导出某个库：

```bash
uv run qq-cli decrypt --db nt_msg
uv run qq-cli decrypt --db profile_info
```

## 为什么不是离线暴力破解

这里需要区分两件事：

- 自动获取运行时 `pKey` 并解密
- 完全离线、不给 QQ 运行机会、只靠加密库去暴力破解

`qq-cli` 现在已经支持第一种，不支持第二种。

原因很简单：这批 NTQQ 数据库不是一个固定字符串密码就能从磁盘上直接猜出来，关键点在于运行中的 `pKey`。所以正确路线不是暴力枚举，而是在 QQ 运行时拿到真实 key，再按 SQLCipher 参数导出明文库。

## 实现依据

当前流程参考的是 QQDecrypt 的思路：

- 先处理 NTQQ 自定义头
- 按 SQLCipher 参数打开数据库
- 使用运行时 `pKey` 导出明文库

当前项目里还做了自动化封装：

- 自动补 `get-task-allow`
- 自动启动 QQ
- 自动通过 LLDB 命中用户 `nt_db`
- 自动快照并解密

## 真实验证

已经在 macOS 上对真实 QQ 客户端做过端到端验证，不走 mock 或测试数据：

```bash
uv run qq-cli init --force --timeout 240
uv run qq-cli sessions --limit 5
uv run qq-cli contacts --groups --limit 5
uv run qq-cli members "某个群"
uv run qq-cli history "某个群" --limit 10
```

验证结果：

- `init` 能自动定位用户 `nt_db`
- `init` 能抓到真实运行时 `pKey`
- `init` 会自动导出 `nt_msg`、`profile_info`、`group_info`、`emoji`、`collection`、`files_in_chat`、`rich_media`
- `sessions` 能读取真实最近会话
- `contacts --groups` 能列出真实群聊
- `members` 能列出真实群成员和管理员
- `history` 已经能恢复文本、图片占位、引用消息、聊天记录卡片等常见内容

实测发现不要再假设 `pKey` 固定为 `32` 字节。至少当前环境里已经观察到：

- `login.db` 命中的 key 长度为 `20`
- 用户 `nt_db` 命中的 key 长度为 `16`

## 常见问题

### 1. `init` 超时

如果第一次执行 `uv run qq-cli init` 超时，常见原因是 QQ 已经启动，但前台初始化还没完成。

处理方式：

- 确认 QQ 已正常登录
- 把 QQ 激活到前台
- 重新执行 `uv run qq-cli init --force`

### 2. QQ 无法被调试

如果 `QQ.app` 没有 `get-task-allow`，`init` 会尝试自动补签名。

这一步通常需要管理员权限，所以你可能会看到签名相关提示。只要补签成功，后续 `init` 就可以继续抓取运行时 key。自动补签失败时，直接按上面的“手动重签名 QQ.app”执行即可。

### 3. 为什么 `sqlite3` 直接打不开原始库

因为真实 NTQQ 原始库通常不能直接被 `sqlite3` 读取，必须先按 QQDecrypt 的思路处理自定义头并使用 SQLCipher 参数导出。

## 参考资料

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
