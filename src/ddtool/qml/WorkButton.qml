import QtQuick
import QtQuick.Controls.Basic as Basic

Basic.Button {
    id: control
    property bool primary: false
    property bool quiet: false
    property bool danger: false
    property string iconName: ""
    readonly property color foreground: primary ? Theme.onAccent : danger ? Theme.error : Theme.ink
    implicitHeight: Theme.compact ? 32 : 36
    implicitWidth: Math.max(36, contents.implicitWidth + 24)
    opacity: enabled ? 1 : 0.48
    hoverEnabled: true
    focusPolicy: Qt.StrongFocus
    contentItem: Item {
        Row {
            id: contents
            anchors.centerIn: parent
            spacing: 6
            Icon { anchors.verticalCenter: parent.verticalCenter; name: control.iconName; visible: name !== ""; size: 15; tint: control.foreground }
            Text {
                anchors.verticalCenter: parent.verticalCenter
                visible: control.text !== ""
                text: control.text
                textFormat: Text.PlainText
                color: control.foreground
                font.pixelSize: 13
                font.weight: control.primary ? Font.DemiBold : Font.Normal
            }
        }
    }
    background: Rectangle {
        radius: 7
        color: control.primary ? (control.down ? Qt.darker(Theme.accent, 1.12) : Theme.accent)
              : control.down || control.hovered ? Theme.hover : control.quiet ? "transparent" : Theme.panel
        border.color: control.visualFocus ? Theme.accent : control.primary || control.quiet ? "transparent" : Theme.line
        border.width: control.visualFocus ? 2 : 1
    }
}
