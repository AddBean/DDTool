import QtQuick
import QtQuick.Layouts

ColumnLayout {
    id: view
    signal showActivity()
    spacing: 15
    Section {
        Layout.fillWidth: true
        title: "手机工具"
        description: "通过 USB 连接 Android 设备。请先开启 USB 调试并在手机上授权。"
    }
    Repeater {
        model: [
            {"tag": "01 / SCRCPY", "title": "手机镜像", "description": "在电脑上显示并操作连接的 Android 手机。", "button": "启动镜像", "key": "mirror"},
            {"tag": "02 / ADB", "title": "手机 MCP", "description": "映射手机端口，并写入 Cursor、Claude Code 和 Codex 配置。", "button": "安装 MCP", "key": "mcp"},
            {"tag": "03 / GNIREHTET", "title": "共享网络", "description": "通过 USB 把电脑网络共享给手机。", "button": "启动共享", "key": "network"}
        ]
        delegate: Rectangle {
            id: device
            required property var modelData
            Layout.fillWidth: true
            Layout.preferredHeight: body.implicitHeight + 27
            color: Theme.panel
            border.color: Theme.line
            radius: 9
            RowLayout {
                id: body
                anchors.fill: parent
                anchors.margins: 14
                spacing: 10
                ColumnLayout {
                    Layout.fillWidth: true
                    spacing: 4
                    Text { text: device.modelData.tag; font.family: Theme.mono; color: Theme.accent; font.pixelSize: 11 }
                    Text { text: device.modelData.title; color: Theme.ink; font.pixelSize: 16; font.weight: Font.DemiBold }
                    Text { Layout.fillWidth: true; wrapMode: Text.Wrap; text: device.modelData.description; color: Theme.muted; font.pixelSize: 12 }
                }
                WorkButton { text: "停止共享"; visible: device.modelData.key === "network"; enabled: !workbench.busy; onClicked: workbench.runDevice("stop-network") }
                WorkButton { text: device.modelData.button; enabled: !workbench.busy; primary: true; onClicked: workbench.runDevice(device.modelData.key) }
            }
        }
    }
    WorkButton { text: "查看运行动态 →"; onClicked: view.showActivity() }
    Item { Layout.fillHeight: true }
}
