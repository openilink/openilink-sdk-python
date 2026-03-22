# 电脑重启后恢复 WeChat AI 会话指南

## 快速恢复（2 步）

电脑重启后，打开终端执行：

```bash
# 1. 进入项目目录
cd C:\Users\11421\wxl\openilink-sdk-python

# 2. 启动 Claude Code
claude
```

就这样！Claude Code 启动时会自动加载 `.mcp.json` 配置，MCP server 会自动启动 iLink daemon，整个链路会自动恢复。

## 如果 token 过期了（收不到消息）

iLink 的 token 有时效性，如果长时间没用可能会过期。这时需要重新登录：

```bash
# 先停掉旧的 daemon
python -m openilink stop

# 重新扫码登录
python -m openilink login

# 登录成功后启动 Claude Code
claude
```

## 如何判断是否正常工作？

在 Claude Code 里输入：

```bash
python -m openilink status
```

正常状态应该显示：
```
BotID:  507e12447387@im.bot
Daemon: running (pid=xxxxx)
```

如果显示 `Daemon: not running`，手动启动：
```bash
python -m openilink start
```

## 完整架构说明

```
你发微信消息
    ↓
微信服务器 → iLink API
    ↓
iLink Daemon（后台进程，长轮询收消息）
    ↓ 写入 .ilink/inbox.jsonl
MCP Server（Claude Code 插件，读取消息推送给 Claude）
    ↓
Claude Code（AI 处理消息）
    ↓ 调用 wechat_reply 工具
MCP Server → iLink API → 微信服务器
    ↓
你收到回复
```

电脑重启后需要恢复的就是 Claude Code 这一整条链。

## 各组件的持久化状态

| 文件 | 作用 | 重启后 |
|------|------|--------|
| `.ilink/state.json` | 登录 token | 保留，不用重新登录（除非过期） |
| `.ilink/inbox.jsonl` | 消息记录 | 保留，不丢消息 |
| `.ilink/sync_buf.dat` | 同步游标 | 保留，断点续传 |
| `.ilink/daemon.pid` | 进程 PID | 重启后失效，会自动清理 |
| `.mcp.json` | MCP 配置 | 保留，Claude Code 启动时自动加载 |

## 常见问题

**Q: 重启后之前的对话上下文还在吗？**
A: 不在。Claude Code 每次启动是新会话，但微信的消息记录（inbox.jsonl）还在。

**Q: 重启期间别人发的消息会丢吗？**
A: 不会。iLink 服务端会保存消息，daemon 重启后会通过 sync cursor 从断点继续拉取。

**Q: 可以开机自启动吗？**
A: 可以。把 `cd C:\Users\11421\wxl\openilink-sdk-python && python -m openilink start` 加到 Windows 启动项（shell:startup）里，daemon 就能开机自启。Claude Code 需要手动打开。
