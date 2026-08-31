# 豆荚工具（DDTool）

一个运行在 Windows 系统托盘或 macOS 菜单栏的轻量工具箱，面向 Android 调试和日常快捷操作。

## 功能

- 镜像手机：使用 `scrcpy` 显示并控制 Android 手机
- 安装手机 MCP：通过 `adb forward` 映射手机端口，并写入 Cursor、Claude Code 和 Codex 配置
- 共享网络：使用 `gnirehtet` 通过 USB 将电脑网络共享给手机
- 推迟锁屏：一小时后自动锁定电脑，可重复点击重新计时
- 快捷操作：维护多级菜单并运行 CMD、PowerShell 或 zsh 命令
- 配置管理：导入、导出配置以及登录时自动启动

## 支持平台

| 能力 | Windows | macOS |
| --- | --- | --- |
| 托盘/菜单栏 | 支持 | 支持 |
| scrcpy 镜像 | 内置 Windows 版本 | 使用 Homebrew/系统安装版本 |
| ADB 与 MCP | 支持 | 支持 |
| gnirehtet 共享网络 | 支持 | 需要安装 macOS 版本 |
| 快捷命令 | CMD / PowerShell | zsh / Terminal |
| 开机启动 | 注册表启动项 | LaunchAgent |

macOS 支持 Apple Silicon。Intel Mac 可在 Intel runner 上使用同一构建配置生成对应架构的应用。

## 开发运行

需要 Python 3.11 或更高版本。

### Windows

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
$env:PYTHONPATH = ".\src"
.\.venv\Scripts\python.exe -m ddtool
```

### macOS

先安装外部工具：

```bash
brew install --cask android-platform-tools
brew install scrcpy gnirehtet
```

然后运行：

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
PYTHONPATH=src .venv/bin/python -m ddtool
```

从 Finder 启动时，程序也会查找 `/opt/homebrew/bin` 和 `/usr/local/bin`。

## 配置位置

- Windows：`%APPDATA%\DDTool\config.json`
- macOS：`~/Library/Application Support/DDTool/config.json`
- 其他 Unix：`$XDG_CONFIG_HOME/ddtool/config.json` 或 `~/.ddtool/config.json`

默认配置：

```json
{
  "scrcpy_path": "scrcpy",
  "scrcpy_args": [],
  "gnirehtet_path": "gnirehtet",
  "forward_local_port": 19999,
  "forward_phone_port": 9999,
  "mcp_server_name": "phone-mcp"
}
```

自定义路径可以填写绝对路径。快捷操作保存在同一配置目录的 `quick_actions.json`。

## 构建

Windows：

```powershell
.\scripts\build.ps1
```

产物为 `dist\豆荚工具.exe`。

macOS：

```bash
chmod +x scripts/build-macos.sh
./scripts/build-macos.sh
```

产物为 `dist/豆荚工具.app` 和 `dist/豆荚工具.dmg`。PyInstaller 不支持跨平台打包，因此 macOS 应用必须在 macOS 或项目自带的 GitHub Actions runner 上构建。

当前自动构建的 macOS 包未签名。公开分发时应配置 Apple Developer ID，对 `.app` 签名并提交 Apple notarization。

## 测试

```bash
PYTHONPATH=src python -m unittest discover -s tests -v
python -m compileall -q src
```

## 项目结构

```text
src/ddtool/
├── tray_app.py       # 菜单栏与托盘入口
├── platform.py       # 平台检测及公共平台辅助函数
├── autostart.py      # Windows 注册表 / macOS LaunchAgent
├── system_lock.py    # 延迟锁屏
├── phone_mirror.py   # scrcpy
├── phone_forward.py  # ADB 映射与 MCP 配置
├── phone_network.py  # gnirehtet 网络共享
├── quick_actions.py  # 快捷操作管理和执行
└── config.py         # 配置读写
```

## 开源协议

[MIT](LICENSE)
