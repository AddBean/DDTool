import QtQuick
import QtQuick.Layouts

ColumnLayout {
    id: view
    spacing: 15
    Section {
        Layout.fillWidth: true
        title: "电源与锁屏"
        description: "为下载、调试等长时间任务临时保持电脑唤醒。"
    }
    Rectangle {
        Layout.fillWidth: true
        Layout.preferredHeight: body.implicitHeight + 34
        color: Theme.panel
        border.color: Theme.line
        radius: 10
        ColumnLayout {
            id: body
            anchors.fill: parent
            anchors.margins: 17
            spacing: 11
            Text { text: "防睡眠计时"; color: Theme.ink; font.pixelSize: 17; font.weight: Font.DemiBold }
            Text { Layout.fillWidth: true; text: workbench.powerStatus; color: workbench.powerActive ? Theme.accent : Theme.muted; font.pixelSize: 13; wrapMode: Text.Wrap }
            RowLayout {
                Text { text: "时长"; color: Theme.muted; font.pixelSize: 13 }
                Repeater {
                    model: workbench.durations
                    WorkButton {
                        required property var modelData
                        text: modelData.label
                        primary: duration.text === String(modelData.minutes)
                        onClicked: duration.text = String(modelData.minutes)
                    }
                }
                Item { Layout.fillWidth: true }
            }
            RowLayout {
                Layout.fillWidth: true
                Text { text: "自定义分钟"; color: Theme.muted; font.pixelSize: 13 }
                Field {
                    id: duration
                    Layout.preferredWidth: 85
                    text: "60"
                    inputMethodHints: Qt.ImhDigitsOnly
                    validator: IntValidator { bottom: 1; top: workbench.maximumPowerMinutes }
                    Accessible.name: "自定义防睡眠分钟数"
                }
                Text { text: "到期后"; color: Theme.muted; font.pixelSize: 13 }
                Choice { id: endAction; Layout.fillWidth: true; model: workbench.endActions; Accessible.name: "计时结束动作" }
            }
            Toggle { id: allowDisplayOff; text: "允许显示器黑屏" }
            RowLayout {
                WorkButton {
                    text: workbench.powerActive ? "重新计时" : "开始防睡眠"
                    enabled: duration.acceptableInput
                    primary: true
                    onClicked: {
                        if (endAction.currentValue === "shutdown") shutdownPrompt.open()
                        else workbench.startPower(Number(duration.text), endAction.currentValue, allowDisplayOff.checked)
                    }
                }
                WorkButton { text: "停止"; enabled: workbench.powerActive; onClicked: workbench.stopPower() }
            }
        }
    }
    Rectangle {
        Layout.fillWidth: true
        Layout.preferredHeight: postpone.implicitHeight + 30
        color: Theme.panel
        border.color: Theme.line
        radius: 10
        RowLayout {
            id: postpone
            anchors.fill: parent
            anchors.margins: 15
            ColumnLayout {
                Layout.fillWidth: true
                Text { text: "推迟锁屏"; color: Theme.ink; font.pixelSize: 16; font.weight: Font.DemiBold }
                Text { text: "从现在起 1 小时后自动锁屏。再次点击重新计时。"; color: Theme.muted; font.pixelSize: 12 }
            }
            WorkButton { text: "设为 1 小时"; onClicked: workbench.postponeLock() }
        }
    }
    Item { Layout.fillHeight: true }
    Prompt {
        id: shutdownPrompt
        title: "确认定时关机？"
        message: "防睡眠计时结束后会请求系统关机。请先保存工作。"
        confirmText: "开始计时"
        danger: true
        onAccepted: workbench.startPower(Number(duration.text), "shutdown", allowDisplayOff.checked)
    }
}
