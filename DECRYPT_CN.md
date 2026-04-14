# QQ.app 重签名

`qq-cli init` 需要给 QQ.app 补 `get-task-allow` 调试权限才能抓到运行时密钥。通常会自动完成，失败时按下面步骤手动处理。

## 手动重签名步骤

```bash
# 1. 退出 QQ
killall QQ 2>/dev/null

# 2. 导出 QQ 当前权限
codesign -d --entitlements - --xml /Applications/QQ.app > qq_ent.plist

# 3. 验证 plist 格式
plutil -lint qq_ent.plist

# 4. 清理旧字段
/usr/libexec/PlistBuddy -c "Delete :com.apple.security.get-task-allow" qq_ent.plist 2>/dev/null || true

# 5. 添加调试权限
/usr/libexec/PlistBuddy -c "Add :com.apple.security.get-task-allow bool true" qq_ent.plist

# 6. 重新签名
codesign --force --sign - --entitlements qq_ent.plist /Applications/QQ.app

# 7. 验证是否生效
codesign -d --entitlements - --xml /Applications/QQ.app 2>/dev/null | grep get-task-allow -A1

# 8. 清理临时文件
rm qq_ent.plist

# 9. 重启 QQ
open /Applications/QQ.app

# 10. 重新初始化
uv run qq-cli init --force
```

如果 QQ 不在 `/Applications/QQ.app`，把路径换成实际安装位置。

## 常见问题

**`init` 超时**：确认 QQ 已正常登录并激活到前台，再重新执行 `uv run qq-cli init --force`。

**QQ 无法被调试**：`init` 会自动尝试补签名，这一步需要管理员权限。自动失败时按上面步骤手动处理。

**`sqlite3` 直接打不开原始库**：NTQQ 原始库有自定义头，必须先解密才能读取，直接用 `sqlite3` 打不开是正常的。