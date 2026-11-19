import QtQuick
import QtQuick.Controls.Basic as Basic
import QtQuick.Layouts

Basic.ScrollView {
    id: page
    contentWidth: availableWidth
    clip: true
    Basic.ScrollBar.horizontal.policy: Basic.ScrollBar.AlwaysOff
    readonly property var config: workbench.shellConfig
    property var selected: []
    property string feedback: ""
    property bool failed: false
    readonly property var modes: [{"key": "chooser", "label": "显示快捷列表"}].concat(workbench.shellTargets)

    function reset() {
        enabledToggle.checked = config.enabled
        menuLabel.text = config.label
        behavior.currentIndex = modes.findIndex(item => item.key === config.mode)
        selected = config.targets.slice()
    }

    function toggleTarget(key, checked) {
        selected = checked ? selected.concat([key]) : selected.filter(item => item !== key)
    }

    Component.onCompleted: reset()

    ColumnLayout {
        width: page.availableWidth
        spacing: 14
        Section {
            Layout.fillWidth: true
            title: "系统右键"
            description: workbench.mac
                ? "从 Finder 所选文件夹的快捷操作或服务菜单进入工作台。"
                : "从桌面空白处、文件夹空白处或选中的文件夹进入工作台。"
        }
        Rectangle {
            Layout.fillWidth: true
            implicitHeight: launchContent.implicitHeight + 30
            visible: workbench.shellSource !== "" && page.config.enabled
            color: Theme.accentWash
            border.color: Theme.line
            radius: 9
            ColumnLayout {
                id: launchContent
                anchors.left: parent.left
                anchors.right: parent.right
                anchors.top: parent.top
                anchors.margins: 15
                spacing: 8
                Text { text: "来自系统右键 · " + workbench.shellSource; color: Theme.accent; font.pixelSize: 12; textFormat: Text.PlainText }
                Text {
                    Layout.fillWidth: true
                    text: workbench.shellDirectory || "未收到可用文件夹；仍可打开工作台功能。"
                    color: Theme.ink; textFormat: Text.PlainText; wrapMode: Text.WrapAnywhere
                    font.family: Theme.mono; font.pixelSize: 13
                }
                Flow {
                    Layout.fillWidth: true
                    spacing: 6
                    Repeater {
                        model: page.config.targets.map(key => workbench.shellTargets.find(item => item.key === key))
                        WorkButton {
                            required property var modelData
                            text: modelData.label
                            enabled: modelData.key !== "folder" || workbench.shellDirectory !== ""
                            onClicked: workbench.openShellTarget(modelData.key)
                        }
                    }
                }
            }
        }
        Rectangle {
            Layout.fillWidth: true
            implicitHeight: form.implicitHeight + 32
            radius: 9
            color: Theme.panel
            border.color: Theme.line
            ColumnLayout {
                id: form
                anchors.left: parent.left
                anchors.right: parent.right
                anchors.top: parent.top
                anchors.margins: 16
                spacing: 9
                RowLayout {
                    Layout.fillWidth: true
                    Toggle {
                        id: enabledToggle
                        text: "启用系统右键入口"
                        enabled: workbench.shellCanInstall
                    }
                    Item { Layout.fillWidth: true }
                    Text {
                        text: page.config.enabled ? "已启用" : "未启用"
                        color: page.config.enabled ? Theme.accent : Theme.muted
                        font.pixelSize: 12
                    }
                }
                Text {
                    Layout.fillWidth: true
                    text: !workbench.shellSupported ? "当前系统不支持系统菜单注册。" : !workbench.shellCanInstall
                        ? "源码模式仅预览；请用打包版注册系统入口。"
                        : workbench.mac ? "Finder 仅支持所选文件夹，不支持空白处；必要时到系统设置启用此快捷操作。"
                        : "Windows 11 可能需要先选择“显示更多选项”。"
                    color: Theme.muted; wrapMode: Text.Wrap; font.pixelSize: 13
                }
                Text { text: "系统菜单名称"; color: Theme.ink; font.pixelSize: 13 }
                Field {
                    id: menuLabel
                    Layout.fillWidth: true
                    maximumLength: 36
                    Accessible.name: "系统菜单名称"
                }
                Text { text: "点击后"; color: Theme.ink; font.pixelSize: 13 }
                Choice {
                    id: behavior
                    Layout.fillWidth: true
                    Accessible.name: "点击系统菜单后的行为"
                    model: page.modes
                }
                Text { visible: behavior.currentValue === "chooser"; text: "快捷列表 · 勾选要展示的功能"; color: Theme.ink; font.pixelSize: 13 }
                GridLayout {
                    visible: behavior.currentValue === "chooser"
                    Layout.fillWidth: true
                    columns: width < 450 ? 1 : 2
                    columnSpacing: 12
                    rowSpacing: 3
                    Repeater {
                        model: workbench.shellTargets
                        Toggle {
                            required property var modelData
                            Layout.fillWidth: true
                            text: modelData.label
                            Accessible.description: modelData.detail
                            checked: page.selected.indexOf(modelData.key) !== -1
                            onToggled: page.toggleTarget(modelData.key, checked)
                        }
                    }
                }
                Text {
                    Layout.fillWidth: true
                    visible: page.feedback !== ""
                    text: page.feedback
                    textFormat: Text.PlainText
                    color: page.failed ? Theme.error : Theme.accent
                    font.pixelSize: 13
                    wrapMode: Text.Wrap
                    Accessible.role: Accessible.StaticText
                }
                RowLayout {
                    WorkButton {
                        objectName: "saveShellShortcuts"
                        text: "保存并应用"
                        onClicked: {
                            const error = workbench.saveShellConfig({"enabled": enabledToggle.checked, "label": menuLabel.text,
                                                                  "mode": behavior.currentValue, "targets": page.selected})
                            page.failed = error !== ""
                            page.feedback = error || (enabledToggle.checked ? "系统入口已更新。" : "设置已保存，系统入口未启用。")
                            if (!error) page.reset()
                        }
                    }
                    WorkButton {
                        text: "还原未保存的更改"
                        quiet: true
                        onClicked: { page.reset(); page.feedback = "" }
                    }
                }
            }
        }
    }
}
