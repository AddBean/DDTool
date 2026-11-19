import QtQuick
import QtQuick.Controls.Basic as Basic
import QtQuick.Dialogs
import QtQuick.Layouts

Basic.ScrollView {
    id: settings
    contentWidth: availableWidth
    clip: true
    Basic.ScrollBar.horizontal.policy: Basic.ScrollBar.AlwaysOff
    ColumnLayout {
    width: settings.availableWidth
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
            Text { text: workbench.autostartStatus; color: Theme.muted; font.pixelSize: 12 }
            RowLayout {
                WorkButton { text: "打开配置目录"; onClicked: workbench.openConfigDirectory() }
                WorkButton { text: "导出 JSON"; onClicked: exportFile.open() }
                WorkButton { text: "导入 JSON"; enabled: !workbench.busy; onClicked: importFile.open() }
            }
        }
    }
    Rectangle {
        Layout.fillWidth: true
        Layout.preferredHeight: updateBox.implicitHeight + 34
        color: Theme.panel; border.color: Theme.line; radius: 10
        ColumnLayout {
            id: updateBox
            anchors.fill: parent
            anchors.margins: 17
            spacing: 10
            Text { text: "应用更新 · " + workbench.appVersion; color: Theme.ink; font.pixelSize: 17; font.weight: Font.DemiBold }
            Toggle { text: "启动后自动检查 GitHub 正式版"; checked: workbench.autoUpdates; onToggled: workbench.setAutoUpdates(checked) }
            Text { Layout.fillWidth: true; text: workbench.updateState.message; textFormat: Text.PlainText; wrapMode: Text.Wrap; color: Theme.muted }
            RowLayout {
                WorkButton { text: "检查更新"; enabled: !workbench.updateState.busy; onClicked: workbench.checkUpdates() }
                WorkButton { text: "下载并校验"; visible: workbench.updateState.available && !workbench.updateState.downloaded; enabled: !workbench.updateState.busy; onClicked: workbench.downloadUpdate() }
                WorkButton { text: "查看已下载文件"; visible: workbench.updateState.downloaded; onClicked: workbench.revealUpdate() }
            }
        }
    }
    }
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
