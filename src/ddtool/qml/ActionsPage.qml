import QtQuick
import QtQuick.Controls.Basic as Basic
import QtQuick.Layouts

ColumnLayout {
    id: view
    property string selectedKey: ""
    property bool creating: false
    property bool showDetails: workbench.layoutValue("detailsHidden") === 0
    property var items: workbench.actionItems
    readonly property var selected: items.find(item => item.key === selectedKey) || null
    readonly property bool readOnly: selected !== null && selected.preset
    readonly property var filtered: items.filter(item => {
        const query = search.text.trim().toLocaleLowerCase()
        return (item.name + " " + item.group + " " + item.shell).toLocaleLowerCase().includes(query)
    })
    spacing: 15

    function setFields() {
        const item = selected
        location.text = item ? item.location : ""
        command.text = item && !item.builtin ? item.command : ""
        shell.currentIndex = workbench.mac ? 0 : item && item.shell === "powershell" ? 1 : 0
        terminal.currentIndex = item ? Math.max(0, terminal.indexOfValue(item.terminal)) : 0
        keepTerminal.checked = item ? item.keepTerminal : false
    }
    function select(key) {
        creating = false
        selectedKey = key
        setFields()
    }
    function createAction() {
        creating = true
        showDetails = true
        selectedKey = ""
        setFields()
        location.forceActiveFocus()
    }
    function persist() {
        workbench.saveLayoutValue("detailsHidden", showDetails ? 0 : 1)
        if (showDetails) workbench.saveLayoutValue("details", Math.round(details.width))
    }
    Component.onCompleted: if (items.length) select(items[0].key)
    Connections {
        target: workbench
        function onActionsChanged() {
            if (!view.creating && !view.selected && view.items.length)
                view.select(view.items[0].key)
        }
    }

    RowLayout {
        Layout.fillWidth: true
        Section {
            Layout.fillWidth: true
            title: "快捷操作"
            description: "整理本地命令和系统动作，工作台与托盘共享同一份配置。"
        }
        WorkButton { text: view.showDetails ? "隐藏详情" : "显示详情"; onClicked: view.showDetails = !view.showDetails }
        WorkButton { text: "+ 新建操作"; primary: true; onClicked: view.createAction() }
    }

    Basic.SplitView {
        id: panes
        Layout.fillWidth: true
        Layout.fillHeight: true
        orientation: Qt.Horizontal
        handle: Rectangle { implicitWidth: 9; color: Basic.SplitHandle.pressed ? Theme.accent : "transparent" }

        Rectangle {
            Basic.SplitView.fillWidth: true
            Basic.SplitView.minimumWidth: 250
            color: Theme.panel
            border.color: Theme.line
            radius: 10
            ColumnLayout {
                anchors.fill: parent
                anchors.margins: 13
                spacing: 10
                RowLayout {
                    Field { id: search; Layout.fillWidth: true; placeholderText: "搜索名称、分组或 Shell"; Accessible.name: "搜索快捷操作" }
                    Text { text: view.filtered.length + " 项"; color: Theme.muted; font.pixelSize: 12 }
                }
                Rectangle { Layout.fillWidth: true; height: 1; color: Theme.line }
                ListView {
                    id: list
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    model: view.filtered
                    clip: true
                    spacing: 3
                    Basic.ScrollBar.vertical: Basic.ScrollBar { }
                    delegate: Basic.ItemDelegate {
                        id: row
                        required property var modelData
                        width: list.width
                        height: Theme.rowHeight
                        text: modelData.name
                        hoverEnabled: true
                        activeFocusOnTab: true
                        onClicked: view.select(modelData.key)
                        background: Rectangle {
                            radius: 6
                            color: view.selectedKey === row.modelData.key ? Theme.accentWash : row.hovered ? Theme.hover : "transparent"
                            border.color: row.visualFocus ? Theme.accent : "transparent"
                        }
                        contentItem: RowLayout {
                            spacing: 9
                            Rectangle {
                                Layout.preferredWidth: 27
                                Layout.preferredHeight: 27
                                radius: 6
                                color: Theme.inset
                                Text { anchors.centerIn: parent; text: row.modelData.builtin ? "◆" : "›_"; color: Theme.accent; font.family: Theme.mono; font.pixelSize: 12 }
                            }
                            ColumnLayout {
                                Layout.fillWidth: true
                                spacing: 0
                                Text { Layout.fillWidth: true; text: row.modelData.name; textFormat: Text.PlainText; color: Theme.ink; elide: Text.ElideRight; font.pixelSize: 13 }
                                Text { Layout.fillWidth: true; text: row.modelData.group; textFormat: Text.PlainText; color: Theme.muted; elide: Text.ElideRight; font.pixelSize: 11; visible: !Theme.compact }
                            }
                            Text { text: row.modelData.preset ? "内置" : row.modelData.shell.toUpperCase(); color: Theme.muted; font.pixelSize: 11 }
                        }
                        TapHandler {
                            acceptedButtons: Qt.RightButton
                            onTapped: {
                                view.select(row.modelData.key)
                                actionMenu.popup()
                            }
                        }
                        TapHandler {
                            enabled: workbench.mac
                            acceptedButtons: Qt.LeftButton
                            acceptedModifiers: Qt.MetaModifier
                            onTapped: {
                                view.select(row.modelData.key)
                                actionMenu.popup()
                            }
                        }
                        Keys.onPressed: event => {
                            if (event.key === Qt.Key_Menu || (event.key === Qt.Key_F10 && event.modifiers & Qt.ShiftModifier)) {
                                view.select(row.modelData.key)
                                actionMenu.popup(row, row.width / 2, row.height)
                                event.accepted = true
                            }
                        }
                    }
                    Text {
                        anchors.centerIn: parent
                        visible: list.count === 0
                        text: search.text ? "没有匹配的操作" : "还没有操作，点击上方新建。"
                        color: Theme.muted
                        font.pixelSize: 13
                    }
                }
            }
        }

        Rectangle {
            id: details
            visible: view.showDetails
            Basic.SplitView.minimumWidth: 270
            Basic.SplitView.preferredWidth: Math.max(270, workbench.layoutValue("details"))
            Basic.SplitView.maximumWidth: 620
            color: Theme.panel
            border.color: Theme.line
            radius: 10
            ColumnLayout {
                anchors.fill: parent
                anchors.margins: 15
                spacing: 8
                visible: view.creating || view.selected !== null
                RowLayout {
                    Layout.fillWidth: true
                    Text { Layout.fillWidth: true; text: view.creating ? "配置新操作" : "操作详情"; color: Theme.ink; font.pixelSize: 17; font.weight: Font.DemiBold }
                    WorkButton { text: "运行"; visible: view.selected !== null; enabled: !workbench.busy; primary: true; onClicked: workbench.runAction(view.selectedKey) }
                }
                Text { text: "名称 / 分组路径"; color: Theme.muted; font.pixelSize: 12 }
                Field { id: location; Layout.fillWidth: true; readOnly: view.readOnly; placeholderText: "例如：开发工具/打开文档"; Accessible.name: "操作名称及分组路径" }
                RowLayout {
                    visible: !view.selected || !view.selected.builtin
                    Text { text: "Shell"; color: Theme.muted; font.pixelSize: 12 }
                    Choice {
                        id: shell
                        Layout.fillWidth: true
                        enabled: !view.readOnly
                        Accessible.name: "Shell"
                        model: workbench.mac ? [{"label": "zsh", "key": "zsh"}] : [{"label": "CMD", "key": "cmd"}, {"label": "PowerShell", "key": "powershell"}]
                    }
                }
                Rectangle {
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    Layout.minimumHeight: 75
                    visible: !view.selected || !view.selected.builtin
                    radius: 7
                    color: Theme.inset
                    border.color: command.activeFocus ? Theme.accent : Theme.line
                    Basic.ScrollView {
                        anchors.fill: parent
                        anchors.margins: 2
                        clip: true
                        Basic.TextArea {
                            id: command
                            readOnly: view.readOnly
                            placeholderText: "输入要运行的本地命令"
                            placeholderTextColor: Theme.muted
                            color: Theme.ink
                            selectionColor: Theme.accent
                            selectedTextColor: Theme.onAccent
                            textFormat: TextEdit.PlainText
                            font.family: Theme.mono
                            font.pixelSize: 13
                            wrapMode: TextEdit.WrapAnywhere
                            padding: 10
                            background: null
                            Accessible.name: "操作命令"
                        }
                    }
                }
                Rectangle {
                    Layout.fillWidth: true
                    Layout.preferredHeight: builtinText.implicitHeight + 27
                    visible: view.selected !== null && view.selected.builtin
                    color: Theme.accentWash
                    radius: 7
                    ColumnLayout {
                        id: builtinText
                        anchors.fill: parent
                        anchors.margins: 13
                        spacing: 5
                        Text { text: "◆  系统能力"; color: Theme.accent; font.pixelSize: 13; font.weight: Font.DemiBold }
                        Text {
                            Layout.fillWidth: true
                            text: view.selected && view.selected.command === "ddtool:keep-awake"
                                  ? "打开电源与锁屏，选择防睡眠时长、黑屏选项和到期动作。"
                                  : "从现在起 1 小时后自动锁屏，再次运行会重新计时。"
                            color: Theme.muted
                            font.pixelSize: 13
                            wrapMode: Text.Wrap
                        }
                    }
                }
                Item { Layout.fillHeight: true; visible: view.selected !== null && view.selected.builtin }
                Toggle { id: keepTerminal; text: "在外部终端中运行"; enabled: !view.readOnly; visible: !view.selected || !view.selected.builtin }
                Choice {
                    id: terminal
                    Layout.fillWidth: true
                    enabled: !view.readOnly
                    visible: workbench.mac && keepTerminal.visible && keepTerminal.checked
                    Accessible.name: "终端应用"
                    model: [{"label": "自动（优先 Ghostty）", "key": "auto"}, {"label": "Ghostty", "key": "ghostty"},
                            {"label": "Terminal", "key": "terminal"}, {"label": "iTerm2", "key": "iterm2"}]
                }
                RowLayout {
                    Layout.fillWidth: true
                    visible: !view.readOnly
                    WorkButton { text: "删除"; danger: true; quiet: true; visible: !view.creating; onClicked: view.askDelete() }
                    Item { Layout.fillWidth: true }
                    WorkButton {
                        text: "保存操作"
                        primary: true
                        onClicked: {
                            const key = workbench.saveAction(view.selectedKey, location.text, command.text, shell.currentValue, terminal.currentValue, keepTerminal.checked)
                            if (key) view.select(key)
                        }
                    }
                }
            }
        }
    }

    function askDelete() {
        deletion.actionKey = selectedKey
        deletion.message = "删除「" + selected.name + "」后，托盘中的入口也会移除。"
        deletion.open()
    }
    Prompt {
        id: deletion
        property string actionKey
        title: "删除快捷操作？"
        danger: true
        confirmText: "删除"
        onAccepted: workbench.deleteAction(actionKey)
    }
    Basic.Menu {
        id: actionMenu
        width: 166
        background: Rectangle { color: Theme.panel; border.color: Theme.line; radius: 8 }
        delegate: Basic.MenuItem {
            id: menuItem
            contentItem: Text { text: menuItem.text; color: Theme.ink; verticalAlignment: Text.AlignVCenter; opacity: menuItem.enabled ? 1 : 0.38 }
            background: Rectangle { color: menuItem.highlighted || menuItem.hovered ? Theme.hover : "transparent"; radius: 4 }
        }
        Basic.Action { text: "运行"; enabled: !workbench.busy; onTriggered: workbench.runAction(view.selectedKey) }
        Basic.Action { text: "查看详情"; onTriggered: view.showDetails = true }
        Basic.Action { text: "上移"; enabled: !view.readOnly; onTriggered: workbench.moveAction(view.selectedKey, -1) }
        Basic.Action { text: "下移"; enabled: !view.readOnly; onTriggered: workbench.moveAction(view.selectedKey, 1) }
        Basic.Action { text: "删除"; enabled: !view.readOnly; onTriggered: view.askDelete() }
    }
}
