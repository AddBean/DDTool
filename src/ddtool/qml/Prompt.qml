import QtQuick
import QtQuick.Controls.Basic as Basic
import QtQuick.Layouts

Basic.Dialog {
    id: prompt
    property string message: ""
    property string confirmText: "确认"
    property bool danger: false
    anchors.centerIn: Basic.Overlay.overlay
    width: 400
    modal: true
    padding: 18
    background: Rectangle { color: Theme.panel; border.color: Theme.line; radius: 11 }
    header: Text {
        leftPadding: 18
        topPadding: 18
        text: prompt.title
        color: Theme.ink
        font.pixelSize: 18
        font.weight: Font.DemiBold
    }
    contentItem: ColumnLayout {
        spacing: 18
        Text {
            Layout.fillWidth: true
            text: prompt.message
            textFormat: Text.PlainText
            color: Theme.muted
            font.pixelSize: 13
            wrapMode: Text.Wrap
        }
        RowLayout {
            Layout.alignment: Qt.AlignRight
            WorkButton { text: "取消"; focus: true; onClicked: prompt.reject() }
            WorkButton { text: prompt.confirmText; primary: !prompt.danger; danger: prompt.danger; onClicked: prompt.accept() }
        }
    }
    Basic.Overlay.modal: Rectangle { color: "#83090d0e" }
}
