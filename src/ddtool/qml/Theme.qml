pragma Singleton
import QtQuick

QtObject {
    property bool dark: true
    property string accentName: "mint"
    property bool compact: false
    readonly property color canvas: dark ? "#101416" : "#edf0ed"
    readonly property color panel: dark ? "#171c1e" : "#f7f9f6"
    readonly property color inset: dark ? "#101517" : "#ffffff"
    readonly property color hover: dark ? "#222a2c" : "#e8eeea"
    readonly property color line: dark ? "#303a3c" : "#ccd6d0"
    readonly property color ink: dark ? "#edf3ef" : "#162421"
    readonly property color muted: dark ? "#a6b5b0" : "#4d635b"
    readonly property color accent: accentName === "blue" ? (dark ? "#9ec9ff" : "#194f9b")
                                    : accentName === "amber" ? (dark ? "#ffd291" : "#7c4b0d")
                                    : (dark ? "#a9e4b6" : "#205e3d")
    readonly property color onAccent: dark ? "#101b17" : "#ffffff"
    readonly property color accentWash: Qt.tint(panel, Qt.rgba(accent.r, accent.g, accent.b, 0.14))
    readonly property color error: dark ? "#ffb0a9" : "#a42e27"
    readonly property int rowHeight: compact ? 38 : 49
    readonly property string mono: Qt.platform.os === "osx" ? "Menlo" : "Consolas"
}
