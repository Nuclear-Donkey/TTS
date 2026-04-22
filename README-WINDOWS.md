# voice-input-win — Windows 语音输入

按住 Right Alt 说话，松开后识别出的中文自动粘贴到当前光标位置。Claude Code CLI、PowerShell、Edge、VSCode、Office 全通用。本地离线识别（Paraformer-zh）。

## 系统要求

- Windows 10 或 Windows 11
- Python 3.10+ （[官网下载](https://www.python.org/downloads/)，安装时勾选"Add Python to PATH"）
- 可用麦克风
- 网络（首次下载模型 ~80 MB）
- 管理员权限（运行时；安装时不需要）

## 安装

解压本目录到任意位置（例如 `C:\voice-input\`），然后：

```bat
cd C:\voice-input
scripts\setup.bat
```

`setup.bat` 会做完：
1. 检查 Python
2. 创建 `.venv\`
3. pip 装 sherpa-onnx、sounddevice、keyboard、pyperclip
4. 下载 Paraformer-zh small 模型（~80 MB）到 `%LOCALAPPDATA%\voice-input\models\`
5. 拷默认配置到 `%APPDATA%\voice-input\config.toml`

## 启动

**推荐以管理员身份启动**（避免某些 UAC 窗口拦截热键）：

```bat
scripts\run-as-admin.bat
```

或者免管理员（大多数应用可用）：

```bat
scripts\run.bat
```

启动后终端会显示：

```
============================================================
  voice-input for Windows
============================================================
  hotkey:       hold  [right alt]  to talk
  model dir:    C:\Users\you\AppData\Local\voice-input\models\paraformer-zh
  audio device: (system default)
  inject:       paste
  log:          C:\Users\you\AppData\Local\voice-input\logs\service.log
  config:       C:\Users\you\AppData\Roaming\voice-input\config.toml
============================================================

  ready — hold [right alt] to speak
```

## 使用

1. 光标落到任何文本框（终端、浏览器、VSCode、Word 都行）
2. **按住 Right Alt** 说一句中文
3. **松开 Right Alt**
4. 约 100 ms 后文字出现在光标处

终端底部会滚动显示状态：
- `● recording…` — 正在收音
- `⏳ recognizing…` — 跑 STT
- `✓ 你刚说的话` — 已粘贴成功
- `✗ ...` / `(silent RMS=xxx)` — 错误或静音保护

## 配置

编辑 `%APPDATA%\voice-input\config.toml`：

```toml
[hotkey]
ptt = "right alt"        # 推荐，也可以 "caps lock" / "f9" / "right ctrl"

[audio]
device = ""              # 空 = 系统默认；也可填设备索引或名字子串

[stt]
num_threads = 4

[inject]
restore_clipboard = true
paste_delay = 0.05
```

改完**重启程序**生效。

## 排错

### 热键没反应
- 确认是**管理员模式**启动的（`run-as-admin.bat`）
- 任务管理器里看有没有 `python.exe`
- 看 `%LOCALAPPDATA%\voice-input\logs\service.log` 日志

### 文字没出现但日志显示已识别
- 当前窗口支持 Ctrl+V 吗？试试在记事本里
- 改配置 `paste_delay = 0.1` 重启

### 识别质量差 / 出现"没有没有"类乱码
- **麦克风信号太低** — 日志会显示 `(silent RMS=xxx)`
- 系统设置 → 声音 → 输入，选对正确的麦克风，把音量拉到 80%+
- 换用 77MB small 模型的话可以切到 217MB full 版：
  ```bat
  .venv\Scripts\python scripts\download_model_win.py --force
  ```

### 想换 PTT 键
改 `config.toml` 里 `[hotkey]` 的 `ptt`。常用键名：`right alt` / `left alt` / `caps lock` / `right ctrl` / `f9` / `pause` / `scroll lock`

### 看设备列表
```bat
.venv\Scripts\python -c "import sounddevice; print(sounddevice.query_devices())"
```

### 完整卸载
删除项目目录，以及：
- `%LOCALAPPDATA%\voice-input\` — 模型 + 日志
- `%APPDATA%\voice-input\` — 配置

## 目录布局

```
voice-input\
├── src\voice_input_win\
│   ├── __main__.py         # 入口
│   ├── config.py           # TOML 配置
│   ├── paths.py            # Windows 路径
│   ├── recorder.py         # sounddevice 录音
│   ├── stt.py              # sherpa-onnx Paraformer
│   ├── hotkey.py           # keyboard PTT 监听 + 状态机
│   └── injector.py         # pyperclip + Ctrl+V 粘贴
├── scripts\
│   ├── setup.bat           # 一键安装
│   ├── run-as-admin.bat    # 管理员启动
│   ├── run.bat             # 普通启动
│   └── download_model_win.py
├── resources\
│   └── default-config-win.toml
└── README-WINDOWS.md
```

## 性能（实测）

| 指标 | 值 |
|------|----|
| 内存占用 | ~450 MB（含模型） |
| STT 延迟（3s 音频） | ~50 ms |
| 端到端延迟（松键→上屏） | ~150 ms |
| 空闲 CPU | < 1% |

## 技术说明

不是 Windows IME（TSF 太复杂、C++/COM），而是"全局热键 + 剪贴板粘贴"。优点是所有应用兼容，缺点是会短暂占用剪贴板（程序会自动恢复原内容）。

STT 用 Paraformer-zh（达摩院），通过 sherpa-onnx 纯 ONNX Runtime 推理，CPU 即可实时。

## 许可

MIT
