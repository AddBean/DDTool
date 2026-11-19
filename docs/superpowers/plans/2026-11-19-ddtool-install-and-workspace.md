# DDTool Installation and Workspace Implementation Plan

> **For agentic workers:** Execute and verify each task in order. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship a configurable grouped workbench, safer update discovery and download, per-user login startup status, and native installer artifacts.

**Architecture:** Keep the Qt Quick app and preserve existing action IDs. Separate installation tooling and GitHub downloads from platform shell and workbench state.

**Tech Stack:** PySide6/QML, Python, Inno Setup, pkgbuild, GitHub Actions.

- [x] Generate versioned installer and portable artifacts; add Windows install/uninstall to CI.
- [x] Add background/manual release checks, exact platform selection and size/SHA-256 verification before exposing downloaded files.
- [x] Add persistent nested groups and per-item pins; validate move cycles and require confirmation before shell execution.
- [x] Distinguish registered, broken, disabled, and unknown system login-item states wherever observable.

Signed MSIX/App Installer, Windows 11 primary-menu desktop validation, and notarized macOS delivery require separate platform credentials/validation. Do not report them as delivered by the traditional installers.
