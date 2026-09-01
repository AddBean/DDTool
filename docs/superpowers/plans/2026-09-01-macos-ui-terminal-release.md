# macOS UI, Terminal, and Release Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make DDTool's macOS editor native-looking in light and dark mode, keep it out of the Dock, support selectable terminal applications, and publish installable DMG/EXE assets.

**Architecture:** Keep zsh as the macOS command shell and persist a separate terminal-application preference on each quick action. Centralize macOS appearance and activation-policy behavior in a small platform UI module, while retaining Windows behavior and backward-compatible JSON loading. Continue publishing raw installer files through the existing GitHub Release job.

**Tech Stack:** Python 3.11+, tkinter/ttk, PyObjC Cocoa, PyInstaller, unittest, GitHub Actions.

---

### Task 1: Terminal application model and execution

**Files:**
- Modify: `src/ddtool/quick_actions.py`
- Test: `tests/test_cross_platform.py`

- [x] **Step 1: Write failing persistence and command-construction tests**

```python
def test_quick_action_defaults_to_automatic_terminal():
    action = QuickAction.from_dict({"name": "检查", "command": "pwd", "shell": "zsh"})
    assert action is not None
    self.assertEqual(action.terminal, TERMINAL_AUTO)

def test_ghostty_launch_arguments():
    self.assertEqual(macos_terminal_launch_args("/tmp/test.command", TERMINAL_GHOSTTY), ["open", "-na", "Ghostty.app", "--args", "-e", "/bin/zsh", "/tmp/test.command"])
```

- [x] **Step 2: Run the focused tests and confirm they fail**

Run: `PYTHONPATH=src .venv/bin/python -m unittest tests.test_cross_platform -v`
Expected: failures for the missing `terminal` field and launch helper.

- [x] **Step 3: Add backward-compatible terminal choices**

```python
TERMINAL_AUTO = "auto"
TERMINAL_GHOSTTY = "ghostty"
TERMINAL_APPLE = "terminal"
TERMINAL_ITERM2 = "iterm2"

@dataclass(slots=True)
class QuickAction:
    # existing fields remain unchanged
    terminal: str = TERMINAL_AUTO
```

Normalize unknown values to `auto`, preserve the field in add/edit/reorder flows, and choose the first installed app for automatic mode.

- [x] **Step 4: Run focused tests**

Run: `PYTHONPATH=src .venv/bin/python -m unittest tests.test_cross_platform -v`
Expected: all terminal model tests pass.

### Task 2: Native macOS editor appearance

**Files:**
- Create: `src/ddtool/macos_ui.py`
- Modify: `src/ddtool/quick_actions.py`
- Modify: `src/ddtool/tray_app.py`
- Test: `tests/test_cross_platform.py`

- [x] **Step 1: Add tests for activation policy and semantic palette selection**

```python
def test_macos_palette_uses_system_colors():
    palette = macos_palette()
    self.assertEqual(palette.window, "systemWindowBackgroundColor")
    self.assertEqual(palette.text, "systemLabelColor")
```

- [x] **Step 2: Implement the macOS UI helper**

```python
@dataclass(frozen=True)
class DialogPalette:
    window: str
    text: str
    secondary_text: str
    field: str
    selected: str

def hide_dock_icon() -> None:
    if IS_MACOS:
        from AppKit import NSApplication, NSApplicationActivationPolicyAccessory
        NSApplication.sharedApplication().setActivationPolicy_(NSApplicationActivationPolicyAccessory)
```

Configure ttk labels, frames, buttons, radio/check controls, tree rows, and the command text editor from system semantic colors rather than hard-coded hex values.

- [x] **Step 3: Rebuild the edit layout**

Use aligned sections for location, command, shell, terminal application, and terminal retention. Present the terminal selector only on macOS, with `自动（优先 Ghostty）`, `Ghostty`, `Terminal`, and `iTerm2`.

- [x] **Step 4: Run all tests and Cocoa lifecycle smoke test**

Run: `PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -v`
Expected: all tests pass.

### Task 3: Build, install, and release v1.0.2

**Files:**
- Verify: `.github/workflows/build.yml`
- Verify: `DDTool-macos.spec`
- Verify: `scripts/build-macos.sh`

- [x] **Step 1: Assert Release asset paths remain raw installers**

Run: `rg -n "DDTool-Windows-x64\\.exe|DDTool-macOS-arm64\\.dmg" .github/workflows/build.yml`
Expected: upload and release steps reference `.exe` and `.dmg`, not archive files.

- [x] **Step 2: Build and install macOS v1.0.2**

Run: `DDTOOL_VERSION=v1.0.2 PYTHON=/opt/homebrew/bin/python3.11 ./scripts/build-macos.sh`
Expected: `dist/豆荚工具.app` and `dist/豆荚工具.dmg` exist and the app version is `1.0.2`.

- [x] **Step 3: Verify native behavior**

Check that the app runs without a Dock icon, opens the editor with system colors, and launches a smoke command using the selected installed terminal.

- [x] **Step 4: Commit and publish**

```bash
git add src/ddtool tests .github DDTool-macos.spec scripts docs
git commit -m "feat: 优化 macOS 编辑界面和终端选择"
git push origin main
./scripts/release.sh v1.0.2
```

- [ ] **Step 5: Verify GitHub Release assets**

Run: `gh release view v1.0.2 --json assets,url`
Expected: `DDTool-macOS-arm64.dmg`, `DDTool-Windows-x64.exe`, and `SHA256SUMS.txt` are published.
