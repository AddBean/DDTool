import QtQuick
import QtQuick.Controls.Basic as Basic

Basic.CheckBox {
    id: control
    implicitHeight: 31
    spacing: 8
    padding: 0
    contentItem: Text {
        leftPadding: control.indicator.width + control.spacing
        text: control.text
        textFormat: Text.PlainText
        color: Theme.ink
        font.pixelSize: 13
        verticalAlignment: Text.AlignVCenter
    }
    indicator: Rectangle {
        width: 19
        height: 19
        anchors.verticalCenter: parent.verticalCenter
        radius: 5
        color: control.checked ? Theme.accent : Theme.inset
        border.color: control.checked || control.visualFocus ? Theme.accent : Theme.line
        border.width: control.visualFocus ? 2 : 1
        Text {
            anchors.centerIn: parent
            text: control.checked ? "✓" : ""
            color: Theme.onAccent
            font.bold: true
        }
    }
}
