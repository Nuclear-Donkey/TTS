# IBus Voice Input — 设计文档

**日期**：2026-04-22
**目标**：Ubuntu 24.04 (GNOME + Wayland) 下的全局语音输入法，给任何文本框（尤其 Claude Code 终端）用说话代替打字。

## 1. 目标与非目标

### 目标
- 在任意 GTK / Qt / Electron / 浏览器 / 终端 窗口中，按住热键说话，松开后文字落到光标处。
- 本地离线识别，中文为主。
- 短句（<10s）延迟 ≤1 秒出字；长句（30s）不崩溃。
- 零 sudo 安装，用户级部署。

### 非目标（v1 不做）
- 流式实时逐字上屏。
- 语音命令模式（"提交"、"撤销"）。
- 多说话人识别 / 说话人分离。
- 标点符号后处理润色（直接用 Paraformer 自带标点）。
- 离线唤醒词 / VAD 自动触发。
- 全局热键（不切到本引擎也能用）— 需要 GNOME shell extension，留到 v2。

## 2. 技术选型

| 维度 | 选型 | 理由 |
|---|---|---|
| 语言 | Python 3.10+ | IBus 官方 GI 绑定最完整；tomllib 内置；快速迭代 |
| 输入法框架 | IBus | GNOME + Wayland 下唯一干净的全局文本注入路径 |
| STT 引擎 | sherpa-onnx + Paraformer-zh | 纯 ONNX Runtime 推理，无 PyTorch 依赖，CPU 实时，中文 SOTA，带标点输出 |
| 录音 | `arecord` subprocess (alsa-utils) | 零 pip 依赖；PipeWire 经由 ALSA 兼容层自动路由；无需 sudo 装 libportaudio2 |
| 包管理 | `uv` + `pyproject.toml` | 快；本地 venv；无系统污染 |
| 配置 | TOML | Python 3.11 内置 `tomllib` |

**目标模型**：`sherpa-onnx-paraformer-zh-2024-03-09`（int8 量化版本），模型文件约 230 MB。
- 主下载源：`https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models/sherpa-onnx-paraformer-zh-2024-03-09.tar.bz2`
- 国内镜像：ModelScope `https://www.modelscope.cn/models/pengzhendong/sherpa-onnx-paraformer-zh-2024-03-09`
- 校验：下载后验证 SHA256（脚本内硬编码）避免损坏

**硬件前提**：Intel i7-13700 / 30 GB RAM / 无独显。Paraformer int8 在 CPU 单线程 RTF ≈ 0.1（10 秒音频 1 秒识别完）。

## 3. 架构

### 进程模型
单进程 Python 服务 `voice_ibus`，由 IBus daemon 按需启动。模型进程内常驻（首次加载 1-2 秒，此后每次识别 200-500 ms 冷热差异可忽略）。

### 组件边界

```
┌─────────────────────────────────────────────┐
│               IBus Daemon                   │
└────────┬────────────────────────────────────┘
         │ D-Bus (ibus 协议)
         ▼
┌─────────────────────────────────────────────┐
│  voice_ibus.__main__                        │
│   └── voice_ibus.engine.VoiceEngine         │
│        ├── Recorder  ──→ PCM bytes          │
│        └── Stt       ──→ 识别文本            │
└─────────────────────────────────────────────┘
```

| 模块 | 路径 | 职责 | 依赖 IBus？ |
|---|---|---|---|
| `engine` | `src/voice_ibus/engine.py` | IBus.Engine 子类；状态机；aux 面板 | 是 |
| `recorder` | `src/voice_ibus/recorder.py` | PCM 录音：`start()` / `stop() -> bytes` | 否 |
| `stt` | `src/voice_ibus/stt.py` | `recognize(pcm_bytes) -> str` | 否 |
| `config` | `src/voice_ibus/config.py` | TOML 读取，提供默认值 | 否 |
| `__main__` | `src/voice_ibus/__main__.py` | 连 IBus bus，注册 engine factory | 是 |

**隔离性质**：`recorder`、`stt`、`config` 可不依赖 IBus 单独跑，便于单测和在命令行里手工调试（`python -m voice_ibus.stt foo.wav`）。

## 4. 状态机与数据流

引擎状态：`IDLE` / `RECORDING` / `PROCESSING` / `ERROR`。

```
  IDLE ──[PTT press]──→ RECORDING ──[PTT release]──→ PROCESSING
   ▲                        │                          │
   │                        │ [focus_out]              │
   │                        ▼                          │
   │                     IDLE（丢弃 PCM）              │
   │                                                    │
   └────────[commit_text 完成 / error]─────────────────┘
```

**正常数据流**：

```
1. 用户 Super+Space 切到 "Voice" engine
2. 焦点入文本框 → engine.focus_in()
3. 用户按住 CapsLock
   → engine.process_key_event(CapsLock, press)
   → recorder.start()
   → engine.update_auxiliary_text("● 录音中")
4. 用户松开 CapsLock
   → engine.process_key_event(CapsLock, release)
   → pcm = recorder.stop()
   → engine.update_auxiliary_text("⏳ 识别中")
5. `threading.Thread(target=stt.recognize, args=(pcm,))` 跑 STT，回调通过 `GLib.idle_add` 回到主线程
6. 主线程 `engine.commit_text(IBus.Text.new_from_string(text))`
7. `engine.hide_auxiliary_text()` → IDLE
```

**关键细节**：
- `process_key_event` 在按键注入给目标应用前被调用；对 CapsLock 返回 `True` 表示吞掉按键（防止 GNOME 切大写锁状态）。
- IBus 跑 GLib mainloop，不能用 asyncio；STT 放独立线程，结果通过 `GLib.idle_add(callback, text)` 回到主线程再调 `commit_text`（IBus API 不线程安全，必须主线程调）。
- 录音用 `subprocess.Popen(["arecord", "-f", "S16_LE", "-r", "16000", "-c", "1", "-t", "raw", "-D", "default"])`，PCM 从 stdout 读到 `bytearray`；停止时发 SIGTERM 后读完剩余缓冲。

## 5. 热键

| 键 | 作用 | 备注 |
|---|---|---|
| Super+Space | 切到/离开 Voice engine | IBus 原生行为 |
| CapsLock（按住） | Push-to-talk | 引擎激活期间 CapsLock 不再切大写锁 |
| Esc（录音中） | 取消本次录音 | 返回 IDLE，不 commit |

CapsLock 由 v1.0 的配置文件暴露出来，用户可改为 `F9` / `RightCtrl` / `RightAlt`。单修饰键（左 Ctrl 等）不推荐。

## 6. 错误处理

| 场景 | 行为 |
|---|---|
| 启动时无麦克风 | 日志 + `notify-send`；engine 仍启动，PTT 时 aux 报 "✗ 无麦克风" |
| 模型加载失败 | 日志 + `notify-send`；每次 PTT 显示 "✗ 模型未就绪"；不 crash |
| 录音中 PipeWire 断开 | 丢弃本次；aux 报错；下次 PTT 尝试重连 |
| STT 返回空串 | 不 commit；aux "（无语音）" 显示 1 秒后清 |
| STT 抛异常 | 日志全栈；aux "✗ 识别失败"；PCM 存 `/tmp/ibus-voice-failed-<ts>.wav` 便于复现 |
| 录音中 focus_out | 打断录音，丢弃 PCM，状态回 IDLE |
| PROCESSING 期间 PTT 再按 | 忽略；aux "⏳ 稍等" |

**日志**：`~/.cache/ibus-voice/service.log`，按日滚动，保留 7 天。级别默认 INFO，`VOICE_IBUS_DEBUG=1` 切 DEBUG。

## 7. 配置

`~/.config/ibus-voice/config.toml`（首次运行从 resources/default-config.toml 复制）：

```toml
[hotkey]
ptt = "CapsLock"          # 可选：F9, RightCtrl, RightAlt
cancel = "Escape"

[audio]
device = ""                # 空 = PipeWire 默认
sample_rate = 16000

[stt]
model_dir = "~/.local/share/ibus-voice/models/paraformer-zh-int8"
num_threads = 4

[ui]
show_aux = true            # 是否显示状态浮条
```

## 8. 目录布局

```
/home/zs/buzhiAI/TTS/
├── pyproject.toml
├── README.md
├── docs/superpowers/specs/2026-04-22-ibus-voice-input-design.md
├── src/voice_ibus/
│   ├── __init__.py
│   ├── __main__.py
│   ├── engine.py
│   ├── recorder.py
│   ├── stt.py
│   └── config.py
├── resources/
│   ├── voice.xml
│   ├── ibus-voice.desktop
│   └── default-config.toml
├── scripts/
│   ├── install.sh
│   ├── uninstall.sh
│   └── download-model.py
└── tests/
    ├── fixtures/*.wav
    ├── test_stt.py
    ├── test_recorder.py
    └── test_engine.py
```

## 9. 安装与部署

**用户级安装**，无需 sudo：

```
~/.local/share/ibus/component/voice.xml          # IBus 发现入口
~/.local/share/ibus-voice/models/…                # Paraformer 模型
~/.config/ibus-voice/config.toml                  # 用户配置
~/.cache/ibus-voice/service.log                   # 日志
```

`voice.xml` 中的 `<exec>` 字段指向项目 venv 的 Python：
```xml
<exec>/home/zs/buzhiAI/TTS/.venv/bin/python -m voice_ibus --ibus</exec>
```

**install.sh 做的事**：
1. `uv sync`（建 .venv，装依赖）
2. `python scripts/download-model.py`（下载 Paraformer 到 `~/.local/share/ibus-voice/models/`，已存在则跳过）
3. 生成 `voice.xml` 到 `~/.local/share/ibus/component/`
4. `ibus restart`
5. 提示用户到 `gnome-control-center region`（或 IBus 首选项）添加 "Voice"

**uninstall.sh**：删上面四个路径，重启 IBus。

## 10. 测试策略

### 单元（无 IBus）
- `test_stt.py`：3-5 个预录短 wav（fixtures/），断言识别结果字符级相似度 ≥85% (difflib.SequenceMatcher.ratio)。
- `test_recorder.py`：mock `sounddevice.InputStream`，喂假 callback，验证 start/stop 返回的 PCM 长度与格式。
- `test_config.py`：默认值、缺字段、非法字段。

### 集成（mock IBus）
- `test_engine.py`：`unittest.mock` 替换 `IBus.Engine` 基类和 `commit_text`；驱动状态机覆盖 IDLE→REC→PROC→IDLE 及所有错误分支。

### 手动验收清单（v1 发布前必过）
- [ ] gnome-terminal 里 `claude` 交互能上屏
- [ ] Firefox 地址栏能上屏
- [ ] VSCode 编辑区能上屏
- [ ] GNOME 文件对话框"文件名"能上屏
- [ ] 5 秒短句延迟 <1 秒出字
- [ ] 30 秒长句不卡死且正确出字
- [ ] 拔 USB 麦克风再插回还能工作
- [ ] CapsLock 作为 PTT 时不会触发大写锁
- [ ] Esc 能取消录音且不 commit

## 11. 里程碑

| 阶段 | 交付 |
|---|---|
| M1 — 引擎骨架 | 空 engine 能被 IBus 发现并切换；aux 能显示 hello |
| M2 — 录音通路 | CapsLock 按住录音，松开保存 wav 到 /tmp |
| M3 — STT 接入 | 录完即识别，识别结果写日志 |
| M4 — 文本落屏 | 识别结果通过 commit_text 上屏；错误分支完整 |
| M5 — 打包安装 | install.sh / uninstall.sh / 模型下载脚本 |
| M6 — 验收 | 手动验收清单全过，写 README |

## 12. 已知风险与应对

| 风险 | 应对 |
|---|---|
| CapsLock 吞键在某些应用不生效 | 配置层暴露，用户可改 F9 |
| Paraformer 对英文术语（API、git 命令）识别差 | v1 不处理；v2 加热词表（sherpa-onnx 支持） |
| 第一次识别冷启动慢 | 启动时做一次 dummy 识别预热 |
| 模型下载被墙 | download-model.py 支持 `--mirror` 切到国内镜像（魔搭/huggingface 镜像） |
| IBus engine 崩溃拉起循环 | 错误全部 catch 在 engine 边界，避免进程退出；只让 D-Bus 连接断才重启 |

## 13. 非功能要求

- 内存：常驻 <500 MB（模型本身 ~250 MB）
- CPU 空闲：<1%
- 识别时 CPU：单次短句峰值 <200%（2 核）
- 安装脚本全程无交互（除了首次模型下载显示进度）
