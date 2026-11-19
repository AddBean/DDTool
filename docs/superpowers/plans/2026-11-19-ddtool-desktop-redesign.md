# DDTool 桌面界面与系统右键改造计划

**目标：** 保持豆荚工具作为轻量托盘应用的使用习惯，新增现代任务工作台，并让用户从系统文件夹右键发起可追踪的本地任务。

**架构：** 保留 Python 及现有设备、网络和电源能力；把任务定义、运行和入口拆开。托盘、主窗口、命令行与系统菜单调用同一套任务逻辑，Windows 和 macOS 分别实现系统入口。

**首选技术栈：** Python + PySide6 Qt Widgets；发布继续以现有 PyInstaller、Windows 和 macOS CI 为基线，先验证再切换。

## 现状与技术选型

- `src/ddtool/tray_app.py` 把隐藏的 Tk 主窗口、pystray、平台事件循环、控制器和配置操作串在一起；现有 macOS UI 辅助代码在 `src/ddtool/macos_ui.py`。升级 UI 应替换这层，而不是长期开两个 GUI 事件循环。
- `src/ddtool/quick_actions.py` 同时负责动作模型、JSON、菜单树、命令启动和 Tk 窗口。它已有应用内右键和终端选项，但没有系统文件管理器入口；现有执行路径没有把选中的目录作为统一任务上下文。
- `src/ddtool/phone_mirror.py`、`src/ddtool/phone_forward.py`、`src/ddtool/phone_network.py`、`src/ddtool/keep_awake.py` 和 `src/ddtool/autostart.py` 只迁移必要的 UI 边界。先查清各控制器的 Tk 回调、线程和关闭依赖，不假设它们可直接换壳。

| 方案 | 优点 | 代价与取舍 |
| --- | --- | --- |
| Tkinter + pystray | 改动最少，足够做任务内核和系统菜单验证 | 可以交付功能，但继续用现有 UI 做工作台，意味着仍要维护现有的样式和双事件循环适配；适合过渡或优先压低改造成本 |
| PySide6 + Qt Widgets | 复用 Python；用 `QSystemTrayIcon` 与工作台共享 Qt 事件循环；适合原生菜单、表格、编辑表单和日志视图 | 需要验证发行包体积、驻留内存、冷启动、macOS 托盘体验，以及所用 Qt 模块的许可与分发义务；**推荐** |
| Tauri + Web UI，Python sidecar | 如果未来明确需要复用 Web 界面，有更大的前端复用空间 | 要额外维护 Rust/前端构建、sidecar 生命周期与进程通信；仍需两端系统菜单适配。不为视觉升级单独引入 |
| 分别做 Windows/macOS 原生应用 | 平台交互可分别深度定制 | 双份 UI、集成和回归成本；只有产品长期聚焦单平台或系统集成成为核心卖点时再考虑 |

Qt 试验包必须在两端实测，而不是只验证开发机能运行。用同一机器对比旧、新版本的产物大小、冷启动、空闲内存和退出行为；若新增成本不符合轻量工具定位，先用旧 UI 交付系统菜单和任务内核。

## 界面与交互

- **托盘 / 菜单栏：** 保留投屏、防睡眠等高频入口；增加「打开工作台」「最近任务」「退出」。关窗口回托盘，并明确区分隐藏和退出。
- **快捷操作工作台：** 左侧「快捷操作 / 手机工具 / 运行记录 / 设置」，中央以可搜索列表为主，右侧编辑动作。可配置名称、模板、适用目录、目标平台、是否显示在系统菜单，并预览实际执行的命令、目录与入口状态。
- **运行记录：** 显示项目目录、运行中／成功／失败／已取消、耗时与日志；支持复制错误、取消运行、定位本次产物。没有找到新产物时不把旧 APK 当作本次结果。
- **视觉方向：** 紧凑的开发工具工作台，跟随系统浅色／深色，使用中性底色、一个青色强调色和独立状态色；系统字体、日志等宽字体，保留清晰的键盘焦点和状态文字，不用大面积渐变或堆叠卡片。

## 右键能力边界

| 场景 | Windows | macOS |
| --- | --- | --- |
| 对选中的项目文件夹点击右键 | MVP：每用户注册经典 Shell 静态入口；Windows 11 按「显示更多选项」交付验证 | MVP：用户启用一个 Finder「快速操作」，例如「用豆荚工具运行…」，接收所选文件夹 |
| 文件夹窗口空白处 | 单独注册和验证目录背景入口；传当前目录，不传上一次选择 | MVP 不承诺；改用选中文件夹、拖入工作台或打开已收藏项目 |
| 桌面空白处 | 单独验证桌面背景入口；建议只显示「打开工作台」，不显示目录构建任务 | MVP 不承诺；菜单栏作为等价入口 |
| 更深层系统集成 | 首层菜单有明确需求再验证 `IExplorerCommand` + App Identity，分别验证文件夹和背景场景 | 不把 Finder Sync 当作通用菜单注入器；该扩展面向同步场景和受监控目录 |

首版优先做**固定的系统入口 + 动态的应用内动作列表**，避免每改一个动作就修改系统配置。Windows 可额外提供固定的「编译安卓（Debug）」入口；macOS 可在验证安装方式后提供独立快速操作。需要最少点击时，先验证这两个直达入口，再决定是否提供逐动作发布。静态入口不承诺能按项目标记实时隐藏；执行前的目录校验不可省略。右键集成默认关闭，启用前解释安装内容，关闭或卸载时只清理由应用创建的入口。

## 分阶段交付

### A. 先打通任务内核与安卓编译

- [ ] 在 `src/ddtool/action_store.py` 分离 JSON 读写与动作模型；保留现有 ID、排序、菜单目录、shell、终端选项和导入导出语义。为新字段做版本化、写入前备份，并用旧配置样本验证升级后结果一致。
- [ ] 在 `src/ddtool/task_runner.py` 定义任务输入：动作 ID、来源和目录；受控模板明确 `程序 + 参数 + cwd`，保留旧终端命令为兼容模式，不自动暴露给系统右键。`src/ddtool/__main__.py` 新增类似 `run-action android-debug --cwd <目录>` 的入口；先解析 CLI，再按需加载 UI。
- [ ] 在 `src/ddtool/android_build.py` 实现显式选择且已信任的项目目录：检查平台对应的 Gradle Wrapper 和项目标记，运行 `assembleDebug`；错误提示区分非项目目录、环境缺失、构建失败。首版只覆盖 Debug 构建，不签名、不上传、不安装 APK。
- [ ] 更新 `tests/test_cross_platform.py` 并新增 `tests/test_task_runner.py`：用模拟执行验证路径、环境、退出码及取消；覆盖空格、中文、Windows 命令特殊字符、目录不存在和不受支持的动作。路径只作为 `cwd` 或结构化参数传递，不拼入 shell 文本；Windows `.bat` 使用专用启动适配并单独测试。

### B. 交付真实系统入口

- [ ] 新建 `src/ddtool/shell_integration/windows.py` 与 `src/ddtool/shell_integration/macos.py`，只负责入口的注册状态与请求转发，不在 Explorer/Finder 内跑任务。Windows 验证固定安装路径以及升级、禁用和卸载；macOS 验证用户启用、权限提示、关闭，以及从已打包应用转发所选目录的方式。MVP 不处理多选，给出清晰提示。
- [ ] 系统入口只转发动作 ID 和目录；应用校验存在、类型与信任。Gradle 会运行项目脚本，第一次从未信任目录触发时先提示；外部导入的任意脚本默认不出现在系统菜单中。不使用全局鼠标钩子、管理员权限或网络监听。用用户范围的本地 IPC 将请求交给已有应用实例；冷启动也能打开同一个任务视图。
- [ ] 真实系统验证：Windows 选中文件夹、文件夹空白处与桌面空白处分别测试；macOS 从 Finder 快速操作测试。主程序关闭／已运行都要覆盖；同时验证用户名或目录含空格、中文，以及拒绝权限、移动安装路径、关闭入口和卸载。

### C. 替换 UI 与发布

- [ ] 建立 `src/ddtool/ui/`：`main_window.py` 负责工作台导航，`actions_view.py` 负责编辑及菜单预览，`tasks_view.py` 负责日志状态，`tray.py` 负责托盘。用 Qt 信号回传耗时任务状态，不阻塞托盘；更换 UI 后，移除旧 Tk 窗口与不再使用的事件循环适配。
- [ ] 调整 `requirements.txt`、`DDTool.spec`、`DDTool-macos.spec` 和 `.github/workflows/build.yml`，继续双平台产物与回归。macOS 分发前验证签名和公证；对比包体、冷启动与空闲资源；用旧配置验证快捷操作和开机启动不丢失。
- [ ] 运行 `PYTHONPATH=src python -m unittest discover -s tests -v`，两端执行打包冒烟并手测原有投屏、手机 MCP、共享网络、防睡眠、托盘退出和配置导入导出。验证高 DPI、深浅色和键盘操作，更新 `README.md` 中的右键启用、限制与卸载说明。

**首版验收：** 在支持的系统入口对一个已信任的安卓项目目录发起 Debug 构建，工作台显示正确的目录、实时输出和最终结果；失败可定位原因、任务可取消；关闭右键入口不影响原有工具与配置。

## 官方参考

- Qt for Python：`QSystemTrayIcon`、Licenses Used in Qt for Python。
- Microsoft Learn：Creating Shortcut Menu Handlers；Windows Developer Blog：Extending the Context Menu and Share Dialog in Windows 11。
- Apple Support：Run a shortcut while working on your Mac；Apple Developer：Finder Sync。
- Tauri v2：Embedding External Binaries。
