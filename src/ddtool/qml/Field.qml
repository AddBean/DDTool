import QtQuick
import QtQuick.Controls.Basic as Basic

Basic.TextField {
    id: field
    implicitHeight: 37
    leftPadding: 11
    rightPadding: 11
    color: Theme.ink
    placeholderTextColor: Theme.muted
    selectionColor: Theme.accent
    selectedTextColor: Theme.onAccent
    font.pixelSize: 13
    background: Rectangle {
        radius: 7
        color: Theme.inset
        border.color: field.activeFocus ? Theme.accent : Theme.line
    }
}
