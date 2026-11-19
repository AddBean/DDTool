# 豆荚工具（DDTool）

一个运行在 Windows 系统托盘或 macOS 菜单栏的轻量工具箱，面向 Android 调试和日常快捷操作。

## 工作台

- Windows 和 macOS 共用自定义 Qt Quick 界面，支持深浅主题、三种强调色、紧凑列表、可折叠侧栏和可拖拽的详情分栏。
- 按 `Ctrl+K`（macOS：`⌘K`）搜索动作或页面。快捷操作列表内右键可运行、排序或删除自定义动作；托盘和工作台共用同一份动作配置。
- 运行动态记录设备反馈及外部命令的发起状态。关闭窗口回到托盘，从托盘菜单或工作台的退出快捷键结束进程。

## 系统右键快捷入口

1. 从稳定位置运行打包版（macOS 请先将应用移到「应用程序」）。在工作台打开「系统右键」，启用入口、修改菜单名称，点击「保存并应用」。注册仅作用于当前用户，不需要管理员权限。
2. 可直达一个功能，也可显示自选列表。支持快捷操作、手机工具、电源与锁屏、运行动态、设置和打开本次文件夹；打开功能页不会自动执行脚本或触发锁屏。
3. Windows 支持桌面空白处、文件夹空白处和单个文件夹项。Windows 11 上如未直接看到入口，请先点「显示更多选项」。macOS 在 Finder 中右键点选一个文件夹后，从「快捷操作」或「服务」进入，不支持空白处；如未显示，请检查「系统设置」中的快捷操作／服务开关。
4. 搬动应用后重新保存可更新启动路径；移除应用前可关闭入口并保存。源码运行不注册系统菜单。安卓编译不包含在本版。

## 功能

- 镜像手机：使用 `scrcpy` 显示并控制 Android 手机
- 安装手机 MCP：通过 `adb forward` 映射手机端口，并写入 Cursor、Claude Code 和 Codex 配置
- 共享网络：使用 `gnirehtet` 通过 USB 将电脑网络共享给手机
- 推迟锁屏：一小时后自动锁定电脑，可重复点击重新计时
- 防睡眠：指定时长阻止自动睡眠/锁屏（适合长时间后台下载），可勾选允许黑屏（鼠标唤醒但不锁屏），到期后可恢复默认、锁屏或关机
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
工作台的主题和布局单独保存在 `workbench.ini`，不修改原配置或导出格式。

## 构建

Windows：

```powershell
.\scripts\build.ps1
```

产物为 `dist\DDTool-Windows-x64.zip`。解压完整目录后运行 `DDTool\DDTool.exe`，不要只拷贝 EXE。

macOS：

```bash
chmod +x scripts/build-macos.sh
./scripts/build-macos.sh
```

产物为 `dist/豆荚工具.app` 和 `dist/豆荚工具.dmg`。PyInstaller 不支持跨平台打包，因此 macOS 应用必须在 macOS 或项目自带的 GitHub Actions runner 上构建。

当前自动构建的 macOS 包未使用 Developer ID 签名或公证。公开分发前应完成两项配置。

## 发布版本

推送符合 `v*` 的 Git Tag 后，GitHub Actions 会自动：

1. 在 Windows 和 Apple Silicon macOS 上运行测试并打包；
2. 生成 `DDTool-Windows-x64.zip` 和 `DDTool-macOS-arm64.dmg`；
3. 计算 SHA-256 校验文件；
4. 创建 GitHub Release，并上传安装包和校验文件。

推荐使用发布脚本，它会检查版本格式、工作区和当前分支：

```powershell
# Windows
.\scripts\release.ps1 v1.0.0
```

```bash
# macOS
./scripts/release.sh v1.0.0
```

也可以手动执行 `git tag -a v1.0.0 -m "Release v1.0.0"`，再执行 `git push origin v1.0.0`。

## 测试

```bash
PYTHONPATH=src python -m unittest discover -s tests -v
python -m compileall -q src
```

## 项目结构

```text
src/ddtool/
├── tray_app.py       # Qt 生命周期、单实例和托盘入口
├── workbench.py      # 连接 QML 和 Python 服务的应用状态与操作
├── shell_shortcuts.py # 系统入口配置和启动协议；平台注册在 *_shortcuts.py
├── qml/              # 自定义主题、组件与工作台页面
├── platform.py       # 平台检测及公共平台辅助函数
├── autostart.py      # Windows 注册表 / macOS LaunchAgent
├── system_lock.py    # 延迟锁屏
├── keep_awake.py     # 防睡眠与到期动作
├── phone_mirror.py   # scrcpy
├── phone_forward.py  # ADB 映射与 MCP 配置
├── phone_network.py  # gnirehtet 网络共享
├── quick_actions.py  # 快捷操作 / 系统命令管理和执行
└── config.py         # 配置读写
```

## 开源协议

[MIT](LICENSE)
