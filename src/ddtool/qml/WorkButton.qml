import QtQuick
import QtQuick.Controls.Basic as Basic

Basic.Button {
    id: control
    property bool primary: false
    property bool quiet: false
    property bool danger: false
    implicitHeight: Theme.compact ? 32 : 36
    implicitWidth: Math.max(36, label.implicitWidth + 24)
    opacity: enabled ? 1 : 0.48
    hoverEnabled: true
    focusPolicy: Qt.StrongFocus
    contentItem: Text {
        id: label
        text: control.text
        textFormat: Text.PlainText
        color: control.primary ? Theme.onAccent : control.danger ? Theme.error : Theme.ink
        font.pixelSize: 13
        font.weight: control.primary ? Font.DemiBold : Font.Normal
        horizontalAlignment: Text.AlignHCenter
        verticalAlignment: Text.AlignVCenter
    }
    background: Rectangle {
        radius: 7
        color: control.primary ? (control.down ? Qt.darker(Theme.accent, 1.12) : Theme.accent)
              : control.down || control.hovered ? Theme.hover : control.quiet ? "transparent" : Theme.panel
        border.color: control.visualFocus ? Theme.accent : control.primary || control.quiet ? "transparent" : Theme.line
        border.width: control.visualFocus ? 2 : 1
    }
}
