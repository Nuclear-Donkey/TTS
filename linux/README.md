# voice-ibus

Linux 语音输入法。给任意应用（Claude Code 终端、浏览器、编辑器、GNOME 文件对话框）用说话代替打字。

**当前状态**：v0.1 - 按住 CapsLock 说话，松开文字直接上屏。仅中文（Paraformer-zh）。仅 Wayland + GNOME + IBus 环境。

## 特性

- 本地离线识别，零 API 费用，零数据上传
- CPU-only，Intel i5+ 即可实时（RTF ≈ 0.01 实测 i7-13700）
- 通过 IBus 做全局输入法，无需自建全局热键/剪贴板 hack
- 单文件配置 TOML，热键可自定义（v1.0 仅 CapsLock）
- 代码 < 600 行，依赖仅 `sherpa-onnx` + `numpy` + 系统 `arecord`

## 系统要求

- Linux + Wayland + GNOME（已验证 Ubuntu 24.04）
- IBus ≥ 1.5（`sudo apt install ibus python3-ibus-1.0 python3-gi gir1.2-ibus-1.0 alsa-utils`）
- PipeWire 或 PulseAudio（GNOME 默认都有）
- `uv`（[install](https://github.com/astral-sh/uv)）
- ~80 MB 磁盘（模型）+ ~300 MB 内存运行时

## 安装

```bash
cd /home/zs/buzhiAI/TTS

# 1. venv + 依赖（一次性）
uv venv --system-site-packages
uv pip install -e .

# 2. 下模型 + 装 IBus 组件（要一次 sudo）
./scripts/install.sh
```

安装脚本会：
- 生成 `/usr/share/ibus/component/voice.xml`（需要 sudo，IBus 只认系统路径）
- 下载 Paraformer-zh small 模型到 `~/.local/share/ibus-voice/models/`（~80 MB）
- 拷贝默认配置到 `~/.config/ibus-voice/config.toml`
- 重启 IBus daemon

## 启用

1. 打开 **GNOME Settings → Keyboard → Input Sources**
2. 点 **+ Add an Input Source** → 选 **Chinese (中文)** → 找 **🎤 Voice**
3. `Super+Space` 切到 Voice
4. 光标落在任何文本框 → 按住 **CapsLock** 说话 → 松开 → 文字上屏

底部 aux 面板会显示状态：
- `🎤 按住 CapsLock 说话` — 空闲
- `● 录音中… 松开结束` — 正在收音
- `⏳ 识别中…` — 处理
- `✓ 你刚说的话` — 成功上屏
- `✗ …` — 错误（看日志）

## 配置

编辑 `~/.config/ibus-voice/config.toml`：

```toml
[hotkey]
ptt = "CapsLock"           # v0.1 仅支持 CapsLock
cancel = "Escape"

[audio]
device = "default"         # ALSA PCM 设备（"default" = PipeWire）
sample_rate = 16000

[stt]
model_dir = "~/.local/share/ibus-voice/models/paraformer-zh"
num_threads = 4

[ui]
show_aux = true
```

改完重启 IBus：`ibus restart`。

## 排错

**按住 CapsLock 切了大写锁没录音**
→ Mutter 某些版本会抢在 IBus 前处理 CapsLock。临时方案：`setxkbmap -option caps:none`（禁用 CapsLock 锁功能后重新登录），未来版本会提供配置改 PTT 键。

**`voice` 没出现在 GNOME 设置里**
→ `ibus list-engine --name-only | grep voice`。空的话看 `~/.cache/ibus-voice/service.log` 和 `journalctl --user -n 50 | grep -i ibus`。

**按 CapsLock 没反应**
→ 确认右上角切换到 Voice 了（图标是 🎤 或 "zh"）。aux 面板不显示不代表没工作，先试着说话看有没有上屏。

**识别不准**
→ 用完整 `sherpa-onnx-paraformer-zh-2024-03-09` 模型（217 MB）：`.venv/bin/python scripts/download-model.py --force`（去掉 `--small`）。

**模型下载失败（被墙）**
→ `.venv/bin/python scripts/download-model.py --url https://<your-mirror>/sherpa-onnx-paraformer-zh-small-2024-03-09.tar.bz2`

## 卸载

```bash
./scripts/uninstall.sh
# 要完全清理：
rm -rf ~/.local/share/ibus-voice ~/.config/ibus-voice ~/.cache/ibus-voice
```

## 调试

```bash
# 看实时日志
tail -f ~/.cache/ibus-voice/service.log

# 重启 daemon 并加调试日志
ibus exit; VOICE_IBUS_DEBUG=1 ibus-daemon -dxv

# 手动跑 STT 识别一个 wav
.venv/bin/python -m voice_ibus.stt your.wav

# 跑测试
PYTHONPATH=src .venv/bin/pytest tests/ -v
```

## 架构

```
GNOME ←keypress── IBus daemon ──D-Bus──→ voice_ibus.__main__
                                               ↓
                            VoiceEngine (GLib main thread)
                              ├─ Recorder (arecord subprocess)
                              └─ STT worker thread
                                   └─ ParaformerStt (sherpa-onnx)
                                        └─ GLib.idle_add → commit_text
```

设计文档：`docs/superpowers/specs/2026-04-22-ibus-voice-input-design.md`

## 非目标

- 流式实时上屏（按住→松开后一次出字，不是边说边出）
- 语音命令（"换行"、"撤销" 等）
- 多说话人、离线唤醒词
- X11 支持（Wayland 独占）
- Fcitx5、Windows、macOS

## 许可

MIT
