from __future__ import annotations

from dataclasses import dataclass
from tkinter import Text, Toplevel, ttk

from ddtool.platform import IS_MACOS


@dataclass(frozen=True, slots=True)
class DialogPalette:
    window: str
    text: str
    secondary_text: str
    field: str
    selected: str
    selected_text: str


def macos_palette() -> DialogPalette:
    """Return dynamic AppKit colors understood by Aqua Tk."""
    return DialogPalette(
        window="systemWindowBackgroundColor",
        text="systemLabelColor",
        secondary_text="systemSecondaryLabelColor",
        field="systemTextBackgroundColor",
        selected="systemSelectedTextBackgroundColor",
        selected_text="systemSelectedTextColor",
    )


def hide_dock_icon() -> None:
    """Keep this status-bar utility out of the Dock and app switcher."""
    if not IS_MACOS:
        return
    from AppKit import NSApplication, NSApplicationActivationPolicyAccessory

    NSApplication.sharedApplication().setActivationPolicy_(
        NSApplicationActivationPolicyAccessory
    )


def configure_dialog(dialog: Toplevel) -> DialogPalette | None:
    """Apply native, appearance-aware styles to a macOS utility dialog."""
    if not IS_MACOS:
        return None
    palette = macos_palette()
    dialog.configure(background=palette.window)
    style = ttk.Style(dialog)
    if "aqua" in style.theme_names():
        style.theme_use("aqua")
    style.configure("DDTool.TFrame", background=palette.window)
    style.configure(
        "DDTool.TLabel", background=palette.window, foreground=palette.text
    )
    style.configure(
        "DDTool.Secondary.TLabel",
        background=palette.window,
        foreground=palette.secondary_text,
    )
    style.configure(
        "DDTool.TCheckbutton", background=palette.window, foreground=palette.text
    )
    style.configure(
        "DDTool.TRadiobutton", background=palette.window, foreground=palette.text
    )
    style.configure(
        "DDTool.Treeview",
        rowheight=28,
        background=palette.field,
        fieldbackground=palette.field,
        foreground=palette.text,
        borderwidth=0,
    )
    style.map(
        "DDTool.Treeview",
        background=[("selected", palette.selected)],
        foreground=[("selected", palette.selected_text)],
    )
    return palette


def configure_command_text(text: Text, palette: DialogPalette | None) -> None:
    if palette is None:
        return
    text.configure(
        background=palette.field,
        foreground=palette.text,
        insertbackground=palette.text,
        selectbackground=palette.selected,
        selectforeground=palette.selected_text,
        highlightthickness=1,
        relief="flat",
    )
