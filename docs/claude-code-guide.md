# 在 Claude Code 中使用 iLink 微信机器人

本文档介绍如何安装 Claude Code，并通过 MCP Channel 或 slash 命令在终端中收发微信消息。

## 前置条件

- Python >= 3.10
- 已安装 openilink SDK（见主 README）
- 一个微信账号（用于扫码登录）

## 安装 Claude Code

```bash
# 通过 npm 全局安装（需要 Node.js >= 18）
npm install -g @anthropic-ai/claude-code

# 验证安装
claude --version
```

### 首次使用

```bash
# 在项目目录下启动 Claude Code
cd openilink-sdk-python
claude
```

首次启动会要求登录 Anthropic 账号，按照终端提示完成即可。

## 方式一：MCP Channel（推荐）

类似 Telegram Channel 的体验 —— 微信消息自动推送到 Claude Code 会话中，Claude 直接处理并回复。

### 快速开始

**第一步：扫码登录**

```bash
python -m openilink login
```

终端会显示二维码，用微信扫描确认即可。Token 自动保存，下次无需重新扫码。

**第二步：启动 Claude Code**

```bash
cd openilink-sdk-python
claude
```

项目目录下的 `.mcp.json` 会自动注册 WeChat MCP server。启动后会看到：

```
WeChat iLink connected. Listening for messages.
```

**第三步：收发消息**

现在就可以了！当有人通过微信发消息给你的 bot，消息会自动出现在 Claude Code 会话中：

```
<channel source="wechat" chat_id="wxid_abc123" user="wxid_abc123" ts="...">
你好
```

Claude 会通过 `wechat_reply` 工具回复消息。

### 工作原理

```
┌──────────┐         ┌──────────────┐        ┌─────────────┐
│  微信用户 │ ──────→ │ iLink API    │ ─────→ │   Daemon    │
│          │         │              │        │ (后台监听)   │
└──────────┘         └──────────────┘        └──────┬──────┘
     ▲                                              │ 写入
     │                                              ▼
     │                                       inbox.jsonl
     │                                              │ 读取
     │            ┌─────────────┐            ┌──────┴──────┐
     │            │ Claude Code │ ◄─────────→│ MCP Server  │
     │            │  (AI 处理)  │  channel    │ (wechat)    │
     │            └──────┬──────┘ notification└─────────────┘
     │                   │
     │                   │ wechat_reply tool
     │                   ▼
     └──────── iLink API ── 发送回复
```

1. **Daemon** 长轮询 iLink API，将新消息写入 `inbox.jsonl`
2. **MCP Server** 轮询 inbox，通过 `notifications/claude/channel` 推送到 Claude Code
3. **Claude** 在当前会话中处理消息，调用 `wechat_reply` 工具回复
4. **MCP Server** 通过 SDK 调用 iLink API 发送回复

### MCP 配置

项目根目录的 `.mcp.json` 会自动加载：

```json
{
  "mcpServers": {
    "wechat": {
      "command": "python",
      "args": ["-m", "openilink.mcp_server"]
    }
  }
}
```

如果想全局启用（所有项目都能用），将配置合并到 `~/.claude/mcp.json`。

## 方式二：Slash 命令

手动控制模式，通过 slash 命令操作。

### 1. 启动机器人 — `/ilink-start`

```
/ilink-start
```

检查登录状态，未登录则显示二维码扫码，然后启动后台守护进程。

### 2. 查看新消息 — `/ilink-check`

```
/ilink-check
```

显示自上次查看后收到的所有新消息。

### 3. 回复消息 — `/ilink-reply`

```
/ilink-reply <user_id> <消息内容>
```

### 4. 停止机器人 — `/ilink-stop`

```
/ilink-stop
```

## CLI 命令行（不依赖 Claude Code）

```bash
python -m openilink login          # 扫码登录
python -m openilink start          # 启动后台守护进程
python -m openilink stop           # 停止守护进程
python -m openilink status         # 查看状态
python -m openilink check          # 查看新消息
python -m openilink send <uid> <text>  # 发送消息
python -m openilink auto           # 自动回复（claude -p）
```

### auto 命令选项

```bash
python -m openilink auto --interval 5      # 轮询间隔（默认 3 秒）
python -m openilink auto --timeout 60      # Claude 超时（默认 120 秒）
python -m openilink auto --prompt "..."    # 自定义系统提示词
```

## 数据文件

所有运行时数据存储在 `.ilink/` 中（已在 `.gitignore` 中）：

| 文件 | 说明 |
|---|---|
| `state.json` | 登录凭证（token、bot_id 等） |
| `inbox.jsonl` | 收到的消息（每行一条 JSON） |
| `sync_buf.dat` | 消息同步游标 |
| `daemon.pid` | 守护进程 PID |
| `daemon.log` | 守护进程日志 |
| `cursor` | CLI check 已读位置 |
| `mcp_cursor` | MCP server 已读位置 |
| `auto_cursor` | auto 命令已读位置 |
| `qrcode.png` | 登录二维码图片 |

## 常见问题

### Q: MCP Channel 和 Slash 命令有什么区别？

MCP Channel 是推送模式，消息自动出现在 Claude Code 中，Claude 有完整上下文可以智能回复。Slash 命令是拉取模式，需要手动 `/ilink-check` 查看。推荐用 MCP Channel。

### Q: Token 多久过期？

取决于微信 iLink 服务端策略。会话过期后 daemon 日志会输出 `session expired`，需要重新 `python -m openilink login`。

### Q: 能收发图片/文件吗？

目前只支持文本消息。如需富媒体，请直接使用 Python SDK 编程。

### Q: 如何在不同项目中使用？

把 `.mcp.json` 复制到目标项目，并确保 `.ilink/state.json` 存在（或重新 login）。也可以将 MCP 配置加到 `~/.claude/mcp.json` 全局使用。
