# voice-input-macos

按住 Right Option 说话，松开文字上屏。

**状态：代码完成但未上机验证。** 主要维护精力在 [`../windows/`](../windows/)。

## 系统要求

- macOS 13+
- Python 3.10+
- 有麦克风
- Accessibility 权限（System Settings → Privacy & Security → Accessibility）

## 安装

```bash
cd macos
./scripts/setup-macos.sh
```

脚本做：建 venv → 装 sherpa-onnx / PyObjC / sounddevice / pynput / pyperclip → 下 Paraformer-zh 模型 → 拷默认配置。

## 启动

```bash
.venv/bin/python -m voice_input_macos
```

菜单栏会出现 `MIC` 图标，按住 **Right Option** 说话。

## 配置

在 `~/Library/Application Support/voice-input/config.toml`：

```toml
[hotkey]
ptt = "right_option"   # caps_lock 在 macOS 上不可用（toggle 语义）

[inject]
method = "paste"       # 需要 Accessibility 权限
```

## 为什么不测

Linux pivot 之后主力做 Windows，mac 端只做了代码移植。要上机用的话需要本地跑一次验证流程：浮窗是否出现、热键是否响应、Cmd+V 是否粘到目标窗口等。欢迎 PR。
