# Windows 端开发交接

Linux 麦克风不稳，项目转移到 Windows 继续。这份文档是给 **Windows 上 Claude Code 会话**看的，让它能直接接上。

## TL;DR

- **保留** Linux 项目（当前目录 `/home/zs/buzhiAI/TTS/`）作为参考代码，不改
- 在 Windows 上**新开项目**（推荐 `C:\voice-input\` 或 `D:\voice-input\`），大部分逻辑复用 Paraformer STT 思路但框架全换
- Windows 版**不走输入法框架（TSF 太复杂）**，走全局热键 + 剪贴板粘贴
- **能直接复用的文件**：`src/voice_ibus/stt.py`（改导入即可）、模型文件（跨平台 onnx）、`src/voice_ibus/config.py`（只需要删掉 `os.path.expanduser` 改成 pathlib.home()）
- **要全部重写**：`recorder.py`（sounddevice 替代 pw-record）、`engine.py` → 改为 `hotkey.py` + `injector.py`、`__main__.py` 托盘/后台服务

## 目标（沿用 Linux 版）

- 按住全局热键说话，松开后识别结果自动上屏到当前焦点应用
- 本地 Paraformer-zh 识别，无联网
- 主用于跟 Claude Code CLI 交互，但任何文本框都通用

## Windows 版架构

```
┌──────────────────────────────────────────────┐
│  voice-input-win (Python 3.11 常驻进程)       │
│                                               │
│  hotkey listener (keyboard lib)               │
│      ↓ RightAlt press                         │
│  Recorder (sounddevice 16kHz mono s16)        │
│      ↓ RightAlt release                       │
│  Paraformer STT (sherpa-onnx)                 │
│      ↓ text                                   │
│  Clipboard (pywin32 / pyperclip)              │
│      ↓                                        │
│  Simulate Ctrl+V (keyboard.send)              │
└──────────────────────────────────────────────┘
```

## Windows 版技术栈

| 组件 | 选型 | 备注 |
|---|---|---|
| Python | 3.11+ 官方安装包 | 不要用 Microsoft Store 版（沙盒限制） |
| 全局热键 | `keyboard` (PyPI) | 需要管理员权限才能捕获全局热键；或用 `pynput` 不需管理员但偶有抖动 |
| 录音 | `sounddevice` | Windows 上 PortAudio 轮子直接装，不像 Linux 那样要编译 |
| STT | `sherpa-onnx` | 和 Linux 版同一个包、同一个模型 |
| 剪贴板 | `pyperclip`（简单）或 `pywin32 + win32clipboard`（稳）| pyperclip 足够 |
| 注入 | `keyboard.send("ctrl+v")` | 已测稳，中文 Electron/浏览器/终端全通 |
| 配置 | TOML（tomllib 内置） | 同 Linux |
| 打包 | PyInstaller（可选） | v0.1 不必，直接 .venv 跑 |

## 推荐热键（Windows 语境）

- **RightAlt（AltGr）按住**：推荐。中文用户几乎不按 AltGr，不会误触。
- CapsLock：Windows 上也能拦截但有些应用仍会收到大写切换信号，不稳。
- F9：无副作用，适合台式机全尺寸键盘。
- `Pause/Break`、`ScrollLock`：几乎没人用，完美 PTT 键，但笔记本通常没有。

## Windows 依赖安装（写脚本 setup.ps1）

```powershell
# 1. 确认 Python 3.11+ 已装
python --version

# 2. 装 uv（和 Linux 版一样）
winget install --id=astral-sh.uv -e

# 3. 在项目目录建 venv
cd C:\voice-input
uv venv
.\.venv\Scripts\activate
uv pip install sherpa-onnx sounddevice numpy keyboard pyperclip

# 4. 下 Paraformer 模型（和 Linux 版同一个）
python scripts\download_model.py
```

## 复用的文件清单

从 `/home/zs/buzhiAI/TTS/` 抓走下面这些文件作为起点（大部分原样，小改）：

| Linux 源 | Windows 目标 | 改动量 |
|---|---|---|
| `src/voice_ibus/stt.py` | `src/voice_input/stt.py` | 0（跨平台） |
| `src/voice_ibus/config.py` | `src/voice_input/config.py` | 路径改成 `Path.home() / "AppData/Roaming/voice-input/config.toml"`；字段可能增删 |
| `resources/default-config.toml` | `config\default-config.toml` | 删掉 `[audio] device`、改 hotkey 默认值 |
| `scripts/download-model.py` | `scripts/download_model.py` | 改 DEFAULT_DEST 到 `%LOCALAPPDATA%\voice-input\models\paraformer-zh` |
| `docs/superpowers/specs/2026-04-22-ibus-voice-input-design.md` | 参考，不搬 | Windows 版另写 spec |
| `tests/test_stt.py`、`tests/test_config.py` | 同位置 | 改路径 |

## 要新写的模块

### `recorder_win.py`
```python
# 大致骨架，实装时补细节
import queue
import sounddevice as sd
import numpy as np

SAMPLE_RATE = 16_000

class Recorder:
    def __init__(self):
        self._q = queue.Queue()
        self._stream = None

    def start(self):
        self._q = queue.Queue()
        def cb(indata, frames, time_info, status):
            self._q.put(indata.copy())
        self._stream = sd.InputStream(
            samplerate=SAMPLE_RATE, channels=1, dtype='int16', callback=cb
        )
        self._stream.start()

    def stop(self) -> bytes:
        self._stream.stop()
        self._stream.close()
        chunks = []
        while not self._q.empty():
            chunks.append(self._q.get_nowait())
        if not chunks:
            return b""
        arr = np.concatenate(chunks, axis=0).flatten().astype(np.int16)
        return arr.tobytes()
```

### `hotkey.py`（核心循环）
```python
import keyboard
import threading
import time
from pathlib import Path

from voice_input.recorder_win import Recorder
from voice_input.stt import ParaformerStt
from voice_input.injector import paste_text

PTT_KEY = "right alt"
SILENCE_RMS_THRESHOLD = 60.0

def main():
    stt = ParaformerStt(<model-dir>)
    rec = Recorder()
    busy = threading.Lock()

    def on_press(_):
        if not busy.acquire(blocking=False):
            return
        try:
            rec.start()
            # 等释放
            keyboard.wait(PTT_KEY + " up")  # 或用 add_hotkey release
            pcm = rec.stop()
            if <too short / too silent>: return
            text = stt.recognize(pcm)
            if text:
                paste_text(text)
        finally:
            busy.release()

    keyboard.on_press_key(PTT_KEY, on_press)
    keyboard.wait()  # 主线程常驻
```

### `injector.py`
```python
import pyperclip
import keyboard
import time

def paste_text(text: str):
    # 保存旧剪贴板，粘贴新文字，短暂后恢复
    try:
        old = pyperclip.paste()
    except Exception:
        old = None
    pyperclip.copy(text)
    time.sleep(0.03)       # 确保剪贴板更新
    keyboard.send("ctrl+v")
    time.sleep(0.1)
    if old is not None:
        try:
            pyperclip.copy(old)   # 还给用户原剪贴板
        except Exception:
            pass
```

### `__main__.py`（后台常驻 + 托盘可选）
v0.1 可以只在控制台里打日志+等热键，不做托盘。v0.2 再加 `pystray` + 托盘菜单（开关、退出、设置）。

## Windows 特有坑

1. **`keyboard` 库要管理员权限**才能可靠捕获全局热键。第一版让用户用"以管理员身份运行"启动脚本即可。不想要管理员的话切 `pynput`。
2. **pyperclip + Ctrl+V 在某些 Office / 远程桌面里失效**，v0.1 接受，加个"复制模式"当后备（只复制不粘贴，用户自己 Ctrl+V）。
3. **keyboard.wait + on_press 别嵌套用**，容易死锁。推荐 `keyboard.on_press_key` + `keyboard.on_release_key` 配对。
4. **进程退出时要 `sd.InputStream.close()`**，不然 Windows 会保留麦克风占用，新进程开不了。
5. **模型路径别用 `C:/Program Files/`** — uv venv 默认不在那，用 `%LOCALAPPDATA%\voice-input\models\`。

## 验收清单（Windows v0.1）

- [ ] Python 3.11+ 启动，能常驻不崩
- [ ] 按 Right Alt 能录音（可以 print("start")/print("stop")验证）
- [ ] 录下的 PCM 跑 stt.recognize 能得到合理中文
- [ ] 识别结果通过 Ctrl+V 上屏到记事本、Edge、Claude Code CLI
- [ ] 原剪贴板内容被恢复（复制一段文字→语音输入→Ctrl+V 还是原文字）
- [ ] 超过 30 秒的长句不崩
- [ ] 没说话（静音）时不瞎编文字（RMS 阈值守卫）

## 给 Windows Claude Code 的工作流建议

1. 读这个文件（HANDOFF-WINDOWS.md）和 `docs/superpowers/specs/2026-04-22-ibus-voice-input-design.md` 做背景
2. 在 Windows 机器上新建项目：`C:\voice-input\`
3. 用 `superpowers:brainstorming` skill 过一遍新的 Windows spec（10-15 分钟，可以很快，因为大方向已定）
4. 按 M1→M6 迭代（参考 Linux 版 spec 的里程碑结构）
5. 实际验收时重点看静音时模型不瞎编、剪贴板能恢复这两条
