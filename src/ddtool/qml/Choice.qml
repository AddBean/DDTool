import QtQuick
import QtQuick.Controls.Basic as Basic

Basic.ComboBox {
    id: control
    implicitHeight: 36
    textRole: "label"
    valueRole: "key"
    leftPadding: 10
    rightPadding: 28
    contentItem: Text {
        text: control.displayText
        textFormat: Text.PlainText
        color: Theme.ink
        font.pixelSize: 13
        verticalAlignment: Text.AlignVCenter
        elide: Text.ElideRight
    }
    indicator: Icon {
        x: control.width - width - 9
        anchors.verticalCenter: parent.verticalCenter
        name: "chevron-down"
        tint: Theme.muted
    }
    background: Rectangle {
        radius: 7
        color: Theme.inset
        border.color: control.visualFocus ? Theme.accent : Theme.line
    }
    delegate: Basic.ItemDelegate {
        id: option
        required property int index
        required property var modelData
        width: control.width
        text: modelData.label
        highlighted: control.highlightedIndex === index
        contentItem: Text {
            text: option.text
            textFormat: Text.PlainText
            color: Theme.ink
            verticalAlignment: Text.AlignVCenter
            elide: Text.ElideRight
        }
        background: Rectangle { color: option.highlighted || option.hovered ? Theme.hover : Theme.panel }
    }
    popup.background: Rectangle { color: Theme.panel; border.color: Theme.line; radius: 7 }
}
