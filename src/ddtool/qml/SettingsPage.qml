import QtQuick
import QtQuick.Dialogs
import QtQuick.Layouts

ColumnLayout {
    spacing: 15
    Section {
        Layout.fillWidth: true
        title: "工作台设置"
        description: "外观和布局仅在本机保存，与快捷操作配置分开。"
    }
    Rectangle {
        Layout.fillWidth: true
        Layout.preferredHeight: appearance.implicitHeight + 34
        color: Theme.panel
        border.color: Theme.line
        radius: 10
        ColumnLayout {
            id: appearance
            anchors.fill: parent
            anchors.margins: 17
            spacing: 10
            Text { text: "外观"; color: Theme.ink; font.pixelSize: 17; font.weight: Font.DemiBold }
            RowLayout {
                Text { Layout.preferredWidth: 70; text: "主题"; color: Theme.muted }
                WorkButton { text: "深色"; primary: workbench.theme === "dark"; onClicked: workbench.setAppearance("dark", workbench.accent, workbench.compact) }
                WorkButton { text: "浅色"; primary: workbench.theme === "light"; onClicked: workbench.setAppearance("light", workbench.accent, workbench.compact) }
            }
            RowLayout {
                Text { Layout.preferredWidth: 70; text: "强调色"; color: Theme.muted }
                Repeater {
                    model: [{"key": "mint", "label": "豆绿"}, {"key": "blue", "label": "雾蓝"}, {"key": "amber", "label": "琥珀"}]
                    WorkButton {
                        required property var modelData
                        text: modelData.label
                        primary: workbench.accent === modelData.key
                        onClicked: workbench.setAppearance(workbench.theme, modelData.key, workbench.compact)
                    }
                }
            }
            Toggle { text: "使用紧凑列表"; checked: workbench.compact; onToggled: workbench.setAppearance(workbench.theme, workbench.accent, checked) }
        }
    }
    Rectangle {
        Layout.fillWidth: true
        Layout.preferredHeight: storage.implicitHeight + 34
        color: Theme.panel
        border.color: Theme.line
        radius: 10
        ColumnLayout {
            id: storage
            anchors.fill: parent
            anchors.margins: 17
            spacing: 10
            Text { text: "启动与配置"; color: Theme.ink; font.pixelSize: 17; font.weight: Font.DemiBold }
            Toggle { text: "登录后启动并驻留托盘"; checked: workbench.autostartEnabled; onToggled: workbench.setAutostart(checked) }
            RowLayout {
                WorkButton { text: "打开配置目录"; onClicked: workbench.openConfigDirectory() }
                WorkButton { text: "导出 JSON"; onClicked: exportFile.open() }
                WorkButton { text: "导入 JSON"; enabled: !workbench.busy; onClicked: importFile.open() }
            }
        }
    }
    Item { Layout.fillHeight: true }
    FileDialog {
        id: exportFile
        title: "导出豆荚工具配置"
        fileMode: FileDialog.SaveFile
        defaultSuffix: "json"
        nameFilters: ["JSON (*.json)"]
        onAccepted: workbench.exportConfig(selectedFile)
    }
    FileDialog {
        id: importFile
        title: "导入豆荚工具配置"
        nameFilters: ["JSON (*.json)"]
        onAccepted: importPrompt.open()
    }
    Prompt {
        id: importPrompt
        title: "导入配置？"
        message: "导入会覆盖文件中包含的配置或快捷操作。导入不会执行命令，请在运行前检查命令内容。"
        confirmText: "导入"
        onAccepted: workbench.importConfig(importFile.selectedFile)
    }
}
