# DDTool QML Workbench Implementation Plan

**Goal:** Replace Tkinter and pystray with a branded Windows/macOS workbench without changing existing quick-action data or system capabilities.

**Architecture:** A Python QObject bridge exposes application state and an asynchronous operation queue to QML. Existing task and device services remain Python modules and report results without importing any GUI framework. A Qt tray menu uses the same bridge as the workbench.

**Tech Stack:** Python, PySide6 Essentials, Qt Quick Controls with a custom theme, PyInstaller, GitHub Actions.

- [x] Identify existing configuration, quick-action, device and power boundaries.
- [x] Remove Tk dialogs and add a UI-independent reporting interface to the existing services.
- [x] Build a QML workbench with actions, devices, power controls, activity, appearance settings and keyboard search.
- [x] Retain the JSON format, menu hierarchy, login launch and import/export; verify duration and end-action controls.
- [x] Bundle QML assets and verify the local macOS package.
- [ ] Verify downloadable artifacts and packaged startup on both GitHub Actions runners.

Phase one does not register Explorer/Finder entries or add Android builds. Existing commands launched in external terminals are tracked as launches, not as captured or completed command jobs.
