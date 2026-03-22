# openilink-sdk-python

微信 iLink Bot API 的 Python SDK，覆盖完整生命周期：扫码登录、消息监听、文本发送、输入状态指示、主动推送。

## 安装

```bash
# 从源码安装
git clone https://github.com/openilink/openilink-sdk-python.git
cd openilink-sdk-python
pip install -e .
```

## 快速开始

### 最小 Echo Bot

```python
from openilink import Client, LoginCallbacks, MonitorOptions, extract_text, print_qrcode

client = Client()

# 扫码登录
result = client.login_with_qr(
    callbacks=LoginCallbacks(on_qrcode=print_qrcode)
)
print(f"登录成功! BotID={result.bot_id}")

# 收到什么就回复什么
client.monitor(
    lambda msg: client.push(msg.from_user_id, "echo: " + extract_text(msg)),
    opts=MonitorOptions(on_error=lambda e: print(f"错误: {e}")),
)
```

运行后终端会显示二维码，用微信扫描即可登录。

## 核心概念

### 1. 创建客户端

```python
from openilink import Client

# 首次使用，需要扫码登录
client = Client()

# 已有 token，跳过扫码直接使用
client = Client(token="你保存的bot_token")
```

支持的参数：

| 参数 | 默认值 | 说明 |
|---|---|---|
| `token` | `""` | Bot Token，为空则需要扫码登录 |
| `base_url` | `https://ilinkai.weixin.qq.com` | API 地址 |
| `cdn_base_url` | `https://novac2c.cdn.weixin.qq.com/c2c` | CDN 地址 |
| `bot_type` | `"3"` | Bot 类型 |
| `version` | `"1.0.0"` | 客户端版本号 |
| `session` | `None` | 自定义 `requests.Session` |

### 2. 扫码登录

```python
from openilink import Client, LoginCallbacks, print_qrcode

client = Client()

result = client.login_with_qr(
    callbacks=LoginCallbacks(
        on_qrcode=print_qrcode,                        # 二维码就绪
        on_scanned=lambda: print("已扫码，请在手机上确认..."),  # 用户已扫码
        on_expired=lambda n, mx: print(f"二维码已过期，正在刷新 ({n}/{mx})..."),
    ),
    timeout=480,  # 登录超时时间（秒），默认 8 分钟
)

if result.connected:
    print(f"登录成功! BotID={result.bot_id} UserID={result.user_id}")
    # 保存 token，下次启动可以跳过扫码
    save_token(result.bot_token)
else:
    print(f"登录失败: {result.message}")
```

`LoginResult` 字段：

| 字段 | 类型 | 说明 |
|---|---|---|
| `connected` | `bool` | 是否登录成功 |
| `bot_token` | `str` | Bot Token，保存后下次可直接使用 |
| `bot_id` | `str` | Bot ID |
| `base_url` | `str` | 服务端返回的 API 地址 |
| `user_id` | `str` | 用户 ID |
| `message` | `str` | 状态消息 |

### 3. 监听消息

```python
from openilink import MonitorOptions

def handler(msg):
    text = extract_text(msg)
    if not text:
        return
    print(f"收到来自 {msg.from_user_id} 的消息: {text}")

    # 回复消息
    client.push(msg.from_user_id, f"你说了: {text}")

client.monitor(
    handler,
    opts=MonitorOptions(
        initial_buf="",                                      # 断点续传游标，空则从头开始
        on_buf_update=lambda buf: save_to_file(buf),         # 游标更新回调，持久化后可断点续传
        on_error=lambda e: print(f"错误: {e}"),              # 非致命错误回调
        on_session_expired=lambda: print("会话已过期!"),       # 会话过期回调
    ),
)
```

`monitor()` 会阻塞当前线程，自动处理重试和退避：
- 连续失败 3 次后退避 30 秒
- 会话过期（errcode -14）后等待 5 分钟
- 自动缓存每条消息的 `context_token`，供 `push()` 使用

### 4. 发送消息

```python
# 方式一：push（推荐） —— 使用自动缓存的 context_token
client.push(user_id, "你好!")

# 方式二：send_text —— 手动传入 context_token
client.send_text(user_id, "你好!", context_token)
```

> `push()` 要求目标用户之前发过消息（SDK 会自动缓存其 context_token）。
> 如果用户从未发过消息，会抛出 `NoContextTokenError`。

### 5. 输入状态指示

```python
# 获取 typing_ticket
config = client.get_config(user_id, context_token)

# 显示"正在输入..."
client.send_typing(user_id, config.typing_ticket)

# 取消输入状态
from openilink import TypingStatus
client.send_typing(user_id, config.typing_ticket, TypingStatus.CANCEL)
```

### 6. 获取 CDN 上传地址

```python
resp = client.get_upload_url({
    "filekey": "my-file-key",
    "media_type": 1,         # 1=图片 2=视频 3=文件 4=语音
    "to_user_id": user_id,
    "rawsize": file_size,
    "rawfilemd5": file_md5,
    "filesize": file_size,
})
print(resp.upload_param)
```

### 7. 优雅停止

```python
import signal

def on_signal(sig, frame):
    client.stop()  # 通知 monitor 停止

signal.signal(signal.SIGINT, on_signal)
signal.signal(signal.SIGTERM, on_signal)
```

## 消息结构

收到的每条消息是 `WeixinMessage` 对象：

```python
msg.from_user_id    # 发送者 ID
msg.to_user_id      # 接收者 ID
msg.message_id      # 消息 ID
msg.message_type    # MessageType.USER(1) 或 MessageType.BOT(2)
msg.message_state   # MessageState.NEW(0) / GENERATING(1) / FINISH(2)
msg.context_token   # 上下文 token，回复时需要
msg.session_id      # 会话 ID
msg.group_id        # 群 ID（私聊为空）
msg.item_list       # 消息内容列表 [MessageItem, ...]
```

每个 `MessageItem` 包含一种内容类型：

```python
item.type           # MessageItemType: TEXT(1) IMAGE(2) VOICE(3) FILE(4) VIDEO(5)
item.text_item      # TextItem: .text
item.image_item     # ImageItem: .url, .media, .thumb_media, ...
item.voice_item     # VoiceItem: .media, .playtime, .text(语音转文字), ...
item.file_item      # FileItem: .file_name, .media, .md5, ...
item.video_item     # VideoItem: .media, .play_length, .thumb_media, ...
```

使用 `extract_text(msg)` 可以快速提取第一条文本内容。

## 完整示例：命令机器人

```python
import signal
import sys
from pathlib import Path
from openilink import (
    Client, LoginCallbacks, MonitorOptions,
    extract_text, print_qrcode,
)

BUF_FILE = Path("sync_buf.dat")
TOKEN_FILE = Path("bot_token.dat")


def load_file(path: Path) -> str:
    try:
        return path.read_text().strip()
    except FileNotFoundError:
        return ""


def main():
    token = load_file(TOKEN_FILE)
    client = Client(token=token)

    # 没有 token 则扫码登录
    if not token:
        result = client.login_with_qr(
            callbacks=LoginCallbacks(
                on_qrcode=print_qrcode,
                on_scanned=lambda: print("已扫码，请确认..."),
            )
        )
        if not result.connected:
            print(f"登录失败: {result.message}", file=sys.stderr)
            sys.exit(1)
        TOKEN_FILE.write_text(result.bot_token)
        print(f"登录成功! BotID={result.bot_id}")

    # Ctrl+C 优雅退出
    signal.signal(signal.SIGINT, lambda *_: client.stop())

    def handler(msg):
        text = extract_text(msg)
        if not text:
            return

        user = msg.from_user_id
        print(f"[{user}] {text}")

        if text == "/help":
            client.push(user, "支持的命令:\n/help - 帮助\n/ping - 测试\n/time - 当前时间")
        elif text == "/ping":
            client.push(user, "pong!")
        elif text == "/time":
            from datetime import datetime
            client.push(user, datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        else:
            client.push(user, f"你说了: {text}")

    print("开始监听消息... (Ctrl+C 退出)")
    client.monitor(handler, opts=MonitorOptions(
        initial_buf=load_file(BUF_FILE),
        on_buf_update=lambda buf: BUF_FILE.write_text(buf),
        on_error=lambda e: print(f"错误: {e}", file=sys.stderr),
        on_session_expired=lambda: print("会话过期，需要重新登录", file=sys.stderr),
    ))


if __name__ == "__main__":
    main()
```

## 错误处理

| 异常 | 场景 |
|---|---|
| `APIError` | API 返回错误（`ret != 0`），可通过 `.is_session_expired()` 判断会话是否过期 |
| `HTTPError` | HTTP 状态码 >= 400 |
| `NoContextTokenError` | 调用 `push()` 时目标用户没有缓存的 context token |

```python
from openilink import NoContextTokenError, APIError

try:
    client.push(user_id, "你好")
except NoContextTokenError:
    print("该用户还没有发过消息，无法主动推送")
except APIError as e:
    if e.is_session_expired():
        print("会话过期，请重新登录")
    else:
        print(f"API 错误: {e}")
```

## 断点续传

`monitor()` 通过 `get_updates_buf` 游标实现增量拉取。持久化这个游标，重启后可以从断点继续：

```python
client.monitor(handler, opts=MonitorOptions(
    initial_buf=Path("sync_buf.dat").read_text(),       # 启动时读取
    on_buf_update=lambda buf: Path("sync_buf.dat").write_text(buf),  # 实时保存
))
```

## API 参考

| 方法 | 说明 |
|---|---|
| `Client(token, base_url, ...)` | 创建客户端 |
| `client.login_with_qr(callbacks, timeout)` | 扫码登录 |
| `client.fetch_qr_code()` | 单独获取二维码 |
| `client.poll_qr_status(qrcode)` | 轮询扫码状态 |
| `client.monitor(handler, opts)` | 长轮询消息监听（阻塞） |
| `client.get_updates(buf)` | 单次拉取更新 |
| `client.send_message(msg)` | 发送原始消息 |
| `client.send_text(to, text, context_token)` | 发送文本消息 |
| `client.push(to, text)` | 使用缓存 token 主动推送 |
| `client.get_config(user_id, context_token)` | 获取 bot 配置 |
| `client.send_typing(user_id, ticket, status)` | 发送输入状态 |
| `client.get_upload_url(req)` | 获取 CDN 上传地址 |
| `client.set_context_token(user_id, token)` | 手动缓存 context token |
| `client.get_context_token(user_id)` | 获取缓存的 context token |
| `client.stop()` | 停止监听循环 |
| `extract_text(msg)` | 提取消息中第一条文本 |
| `print_qrcode(url)` | 在终端打印二维码 |

## 项目结构

```
openilink-sdk-python/
├── openilink/
│   ├── __init__.py    # 包入口，统一导出
│   ├── client.py      # 核心客户端，HTTP 请求封装和 API 方法
│   ├── types.py       # 数据类型定义（dataclass + enum）
│   ├── auth.py        # 扫码登录流程
│   ├── monitor.py     # 长轮询消息监听
│   ├── errors.py      # 异常类型
│   └── helpers.py     # 工具函数
├── examples/
│   └── echo_bot.py    # Echo 机器人示例
├── pyproject.toml
└── README.md
```

## 依赖

- Python >= 3.10
- [requests](https://pypi.org/project/requests/) >= 2.28
- [qrcode](https://pypi.org/project/qrcode/) >= 7.0

## License

MIT
