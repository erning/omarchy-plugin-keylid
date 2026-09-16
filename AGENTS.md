# Keylid 开发指南

Keylid 是独立的 Omarchy 状态栏插件，用于切换 MacBook 内置键盘的启用状态。先读 [README.md](README.md) 了解使用方式，再按下面的文件分工定位代码。

## 项目约定

- 插件 ID、QML `moduleName` 和 IPC target 统一为 `erning.keylid`，显示名称为 `Keylid`。仓库或开发目录的名称不决定插件 ID。
- 保持独立插件；使用原生指示器的视觉和交互方式，不合并进 `omarchy.indicators`。
- 当前实现面向 Omarchy 4.0、Quickshell 0.3.1 和 Hyprland 0.56 的 Lua 配置 API。升级兼容性时先核对目标版本的本机源码或官方文档。
- 后端仅依赖 Python 3 标准库和 `hyprctl`，无需 root 权限；没有构建步骤或依赖安装步骤。
- 保持无常驻辅助进程的实现：状态由 Omarchy shell 内的 QML 服务保存，Python 命令执行一次就退出。卸载恢复只做尽力尝试，不为此引入守护进程、会话锁或重试机制。
- 现有 README、代码注释和界面文案使用英文，修改时保持一致。

## 文件分工

| 文件 | 职责 |
| --- | --- |
| `manifest.json` | 声明 `bar-widget` 和 `service` 两个入口，默认放在状态栏中央 |
| `Widget.qml` | 展示图标、悬停显隐和点击操作，通过 `bar.shell.serviceFor("erning.keylid")` 获取共享服务 |
| `Service.qml` | 保存共享状态、按需启动命令并读取 JSON 结果，处理配置重载、IPC 和卸载恢复 |
| `backend.py` | 执行一次 `enable` 或 `disable` 操作，输出 JSON 后退出 |
| `tests/test_backend.py` | 使用模拟 `hyprctl` 验证设备范围、单次命令、错误处理和手动恢复 |
| `tests/qml_smoke.py` | 离屏加载真实 Omarchy QML 组件，验证显隐、服务联动和销毁后的恢复 |

## 必须保留的行为

- 只控制 `hyprctl devices -j` 的 `keyboards` 列表中名称精确等于 `apple-inc.-apple-internal-keyboard-/-trackpad` 的设备。名称虽含 `trackpad`，目标仍是键盘；不要扩大为 Apple 设备或名称前缀匹配。
- 使用 `hyprctl eval` 调用 `hl.device({ name = ..., enabled = ... })`。不要换回旧版 Hyprland 的配置语法，也不要写持久禁用规则。
- 每次加载 QML 服务都先启用键盘，不持久化禁用状态。收到 `configreloaded` 时重新应用当前选择；有错误时优先启用。
- 所有显示器上的组件共享一个 QML 服务；不要在每个 `Widget.qml` 中单独启动命令或保存切换状态。
- 左键切换，右键启用；有错误时点击优先尝试启用。忙碌时禁止重复点击。
- 键盘启用且无错误时，图标随中央区域悬停显示，隐藏后不占布局空间；键盘禁用或发生错误时保持可见。
- 使用原生 `BarIndicator` 获得字体、间距和强调色，保留 `centerSectionRevealHeld`、`centerHoverRevealSuppressed` 及悬停延迟逻辑。不要改回尺寸更大的 `BarIconButton`。

## 后端的关键约束

- `Service.qml` 用 `Process` 执行 `python3 -B backend.py enable|disable`，收集 JSON 并在进程退出后更新状态。空闲时没有 Python 或 `hyprctl` 进程，也没有定时轮询。
- 禁用前先检查设备列表中的精确名称；启用时先发出恢复命令，再查询设备列表，避免查询失败阻止恢复。
- 命令超时或报错不证明设备没有发生变化。后端结果中的 `disabled: null` 表示状态未知；QML 保留错误提示，下一次点击优先启用。
- `hyprctl` 退出码为 0 时也可能在标准输出中报告 Lua 错误；必须同时验证回复为 `ok`。
- Hyprland 0.56.2 的设备列表不提供键盘启用状态。QML 中的 `disabled` 用于界面显示和配置重载，表示最后确认的设置；有错误时状态可能未知。界面状态不是独立读取的硬件状态。
- `Service.qml` 的请求异步完成，忙碌期间只为 `reapply` 保留待处理标记。IPC 调用返回成功不代表键盘操作完成，应继续查看 `busy` 和 `error`。
- 正常卸载通过 `Quickshell.execDetached` 直接发出一次 `hyprctl` 启用命令，不依赖可能已被删除的插件目录。此处的设备名称需与 `backend.py` 中的 `DEVICE` 保持一致。
- Quickshell 销毁 `Process` 时可能强制结束正在运行的命令。卸载与命令重叠、shell 崩溃或 Hyprland 无响应时，不保证恢复；保留手动恢复入口，不额外实现跨进程协调。

## 验证

从仓库根目录运行：

```bash
omarchy plugin validate .
python3 -B -m unittest discover -s tests -v
python3 -B tests/qml_smoke.py
git diff --check
```

后端测试需要 Linux 和 Python 3。QML 冒烟测试还需要 `quickshell`，并从 `/usr/share/omarchy/shell/Ui` 和 `Commons` 加载本机组件；测试脚本自行设置离屏渲染和模拟会话。两套测试都替换了 `hyprctl`，不会禁用真实键盘。

后端改动运行后端测试；QML、进程生命周期或接口改动同时运行 QML 冒烟测试；清单改动运行插件校验。纯文档修改检查内容和空白即可。新增测试应覆盖行为或失败场景，不要把真实键盘禁用作为自动测试步骤。

## 本机安装与调试

安装、禁用和卸载命令见 README。开发安装可通过 `~/.config/omarchy/plugins/erning.keylid` 符号链接指向仓库；修改前用 `readlink` 核对，移动开发目录时同步检查链接目标。

涉及桌面配置、安装或重载时，使用可用的 `omarchy` skill。`/usr/share/omarchy/` 只作为源码参考，不修改包管理器维护的文件；用户配置位于 `~/.config/omarchy/`。

修改代码后先尝试：

```bash
omarchy shell shell rescanPlugins
```

本机曾出现重新扫描后仍使用旧 QML 的情况。确需重启时，先用 `omarchy shell lock status` 检查 `secure` 和 `requested`；只有确认未锁屏且未请求锁屏时才执行 `omarchy restart shell`。不要绕过重启命令的锁屏保护，也不要用会重置配置的 `omarchy refresh shell` 代替重启。

常用 IPC：

```bash
omarchy shell erning.keylid status
omarchy shell erning.keylid enable
omarchy shell erning.keylid toggle
```

`toggle` 会实际改变键盘状态，仅在需要实机验证时使用。插件不可用时，可在仓库根目录运行 `python3 backend.py enable` 恢复。操作只影响当前 Hyprland 会话，不影响 Linux 控制台或其他登录会话。

目前没有实现 `omarchy toggle builtin-keyboard` 集成。Omarchy 的通用 `toggle` 只操作状态标记，不会自动调用此插件；对外控制入口是 `omarchy shell erning.keylid ...`。

查阅原生组件时，优先看本机 `/usr/share/omarchy/shell/Ui/BarIndicator.qml`、`plugins/bar/widgets/Indicators.qml` 和 `plugins/bar/indicators/StayAwake.qml`。`omarchy.indicators` 的内部列表加载固定路径下的组件，不是任意插件 ID 的容器。
