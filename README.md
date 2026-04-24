# voice-input

按住热键说话，松开文字上屏。跨平台语音输入工具，本地离线识别（Paraformer-zh，80MB）。

## 三个平台各走各的

代码按平台分开，每个目录独立自洽：

| 平台 | 目录 | 状态 |
|---|---|---|
| **Windows** | [`windows/`](windows/) | ✅ **主力维护** — PySide6 GUI，托盘 + 毛玻璃浮窗，CapsLock PTT |
| **Linux** (IBus) | [`linux/`](linux/) | 🧊 冻结 — Ubuntu 24.04 + GNOME + Wayland 可用，不再主动演进 |
| **macOS** | [`macos/`](macos/) | 🧊 冻结 — 代码完成但未上机验证 |

共用部分在 [`shared/`](shared/)（录音、STT、配置 helper）。安装脚本会自动把 `shared/` 复制进对应平台的 `src/` 下。

## 快速入口

```bash
# Windows 用户 (双击即可):
cd windows
scripts\install.bat

# Linux 用户:
cd linux
./scripts/install.sh

# macOS 用户 (未验证):
cd macos
./scripts/setup-macos.sh
```

具体使用说明请看对应平台目录下的 `README.md`。

## 为什么做这个

给 Claude Code 终端之类的场景做中文语音输入，避开了：
- 云 API 费用和数据上传
- TSF / IME 复杂度（Windows / macOS）
- Fcitx5 / X11 兼容折腾（Linux 只支持 GNOME Wayland）

## 许可

MIT
