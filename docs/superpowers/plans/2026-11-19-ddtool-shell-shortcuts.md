# Shell Shortcuts Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let users opt into a system context-menu shortcut that opens a selected DDTool function or a configurable list.

**Architecture:** Declare safe targets and their configuration independently of the OS. Keep user-scoped registration in platform adapters and forward folder activations to the existing workbench instance using local IPC.

**Tech Stack:** Python, Qt/QML, Windows registry, macOS Automator Quick Actions.

- [ ] Validate configuration, local launch messages and directory context in `src/ddtool/shell_shortcuts.py`.
- [ ] Add per-user registration in `src/ddtool/windows_shortcuts.py` and `src/ddtool/macos_shortcuts.py`, without running arbitrary user commands.
- [ ] Wire cold and warm activation in `src/ddtool/tray_app.py`; add the configuration and chooser UI in `src/ddtool/qml/ContextPage.qml`.
- [ ] Run `PYTHONPATH=src .venv/bin/python -m unittest discover -s tests`, the QML smoke test, and a staged macOS workflow smoke test; document native-menu coverage and remaining manual checks.
