import QtQuick
import QtQuick.Controls.Basic as Basic
import QtQuick.Layouts

ColumnLayout {
    spacing: 15
    RowLayout {
        Layout.fillWidth: true
        Section {
            Layout.fillWidth: true
            title: "运行动态"
            description: "记录本次会话的操作反馈；外部命令仅记录已发起，不跟踪退出状态。"
        }
        WorkButton {
            text: "复制全部"
            enabled: list.count > 0
            onClicked: workbench.copy(workbench.activity.map(entry => entry.time + "  " + entry.text).join("\n"))
        }
        WorkButton { text: "清空"; enabled: list.count > 0; onClicked: workbench.clearActivity() }
    }
    Rectangle {
        Layout.fillWidth: true
        Layout.fillHeight: true
        color: Theme.inset
        border.color: Theme.line
        radius: 10
        ListView {
            id: list
            anchors.fill: parent
            anchors.margins: 12
            clip: true
            spacing: 4
            model: workbench.activity
            Basic.ScrollBar.vertical: Basic.ScrollBar { }
            delegate: Rectangle {
                id: entry
                required property var modelData
                width: list.width - 10
                height: line.implicitHeight + 16
                radius: 6
                color: Theme.panel
                RowLayout {
                    id: line
                    anchors.fill: parent
                    anchors.margins: 8
                    spacing: 12
                    Text { Layout.alignment: Qt.AlignTop; text: entry.modelData.time; font.family: Theme.mono; color: Theme.muted; font.pixelSize: 12 }
                    Text { Layout.alignment: Qt.AlignTop; text: entry.modelData.level === "error" ? "错误" : "信息"; color: entry.modelData.level === "error" ? Theme.error : Theme.accent; font.pixelSize: 12 }
                    Text { Layout.fillWidth: true; text: entry.modelData.text; textFormat: Text.PlainText; color: Theme.ink; font.pixelSize: 13; wrapMode: Text.WrapAnywhere }
                    WorkButton { Layout.alignment: Qt.AlignTop; text: "复制"; quiet: true; onClicked: workbench.copy(entry.modelData.text) }
                }
            }
        }
        Text { anchors.centerIn: parent; visible: list.count === 0; text: "还没有运行动态"; color: Theme.muted; font.pixelSize: 14 }
    }
}
