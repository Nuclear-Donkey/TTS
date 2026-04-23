# voice-input for Windows

按住 **Right Alt** 说话，松开后识别出的中文自动粘贴到当前光标位置。Claude Code CLI、PowerShell、Edge、VSCode、Office 全通用。本地离线识别（Paraformer-zh，~80 MB）。

## 给小白用户（直接用 .exe）

1. 从 [Releases](../../releases) 下载最新 `voice-input.exe`
2. **双击运行**
3. 首次启动：自动弹进度条下载识别模型（~80 MB，一次即可），完成后在桌面生成 `voice-input.lnk` 快捷方式
4. 右下角托盘出现麦克风图标 ✅
5. 光标落到任何文本框，按住 **Right Alt** 说话 → 松开 → 文字自动粘贴

### 界面

- **屏幕顶部**会出现一个毛玻璃悬浮小条显示状态：
  - 🔴 `录音中…`
  - 🟡 `识别中…`
  - 🟡 `✓ 你刚说的话`（1 秒后自动消失）
- **右下角托盘**可点开菜单：切换麦克风、打开配置、打开日志、退出

### 系统要求

- Windows 10 / 11
- 有麦克风
- 首次启动要联网（下载 80MB 模型）；之后完全离线

### 推荐：以管理员身份运行

部分提权窗口（任务管理器、某些游戏启动器）会吞掉热键。右键快捷方式 → 属性 → 兼容性 → 勾"以管理员身份运行"即可永久解决。

## 常见问题

**热键按了没反应**
- 检查右下角托盘图标是否还在（程序是否在跑）
- 以管理员身份重新启动
- 打开托盘右键菜单 → "打开日志文件夹"，看 `service.log` 有无报错

**识别文字没粘进来**
- 当前窗口是否支持 Ctrl+V？先在记事本里试
- 改配置文件里 `paste_delay = 0.1` 再重启

**识别结果不准 / 出现无意义字**
- 麦克风音量低：日志里看 `(silent RMS=xxx)`。系统设置 → 声音 → 输入，选对设备且拉到 80%+
- 换更准的完整版模型：删除 `%LOCALAPPDATA%\voice-input\models\paraformer-zh`，用高级模式手动下载 217MB full 版

**想换 PTT 键**
托盘 → 打开配置文件，改 `[hotkey] ptt`，保存后右键托盘退出、再启动。

```toml
[hotkey]
ptt = "right alt"    # 可选：caps lock / right ctrl / f9 / pause / scroll lock
```

**想开机自启**
右键桌面快捷方式 → 复制 → 按 `Win+R` 输入 `shell:startup` → 把快捷方式粘进去

## 彻底卸载

1. 右键托盘 → 退出
2. 删除 `voice-input.exe` 和桌面/开始菜单里的快捷方式
3. 删除以下两个文件夹（可选，含模型和配置）：
   - `%LOCALAPPDATA%\voice-input\`
   - `%APPDATA%\voice-input\`

---

## 开发者：从源码构建 .exe

```bat
git clone <repo> && cd TTS
scripts\setup.bat        :: 建 venv + 装运行时依赖
scripts\build-exe.bat    :: 装 PyInstaller/PyQt6/Pillow 并编译,输出 dist\voice-input.exe
```

构建配置在 `voice-input-win.spec`。单文件 exe 约 180–220 MB（含 Qt + sherpa-onnx 运行时）。

### 直接从源码运行（开发用）

```bat
scripts\setup.bat
.venv\Scripts\python -m pip install PyQt6
.venv\Scripts\python -m voice_input_win
```

### 目录布局

```
src\voice_input_win\
  ├── __main__.py           # Qt 入口
  ├── floating_window.py    # PyQt6 毛玻璃浮窗
  ├── tray.py               # 系统托盘
  ├── first_run.py          # 首次启动:下载模型+创建快捷方式
  ├── model_downloader.py   # 模型下载(可导入,带进度回调)
  ├── hotkey.py             # keyboard 库 + 状态机
  ├── injector.py           # pyperclip + Ctrl+V 粘贴
  ├── recorder.py           # sounddevice 录音
  ├── stt.py                # sherpa-onnx Paraformer
  ├── config.py / paths.py  # TOML 配置 + Windows 路径
```

## 架构说明

不是 Windows IME（TSF 太复杂），而是"全局热键 + 剪贴板 Ctrl+V"。优点：所有应用兼容。缺点：短暂占用剪贴板（程序会异步恢复原内容）。

STT 走 sherpa-onnx ONNX Runtime 推理，CPU 即可实时。UI 走 PyQt6（毛玻璃浮窗 + 系统托盘）。进程模型：Qt 主线程跑 UI，`keyboard` 库后台线程监听热键，识别在独立 worker 线程，状态变化通过 Qt signal 跨线程分发。

## 许可

MIT
