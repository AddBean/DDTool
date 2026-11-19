import QtQuick
import QtQuick.Controls.Basic as Basic
import QtQuick.Layouts

ColumnLayout {
    id: view
    property string selectedKey: ""
    property bool creating: false
    property string selectedGroup: "u:"
    property var folded: ({})
    property bool showDetails: workbench.layoutValue("detailsHidden") === 0
    property var items: workbench.actionItems
    readonly property var selected: items.find(item => item.key === selectedKey) || null
    readonly property bool readOnly: selected !== null && selected.preset
    readonly property var filtered: workbench.actionTree.filter(item => {
        const query = search.text.trim().toLocaleLowerCase()
        if (query) return (item.name + " " + item.group + " " + (item.shell || "")).toLocaleLowerCase().includes(query)
        let parent = item.parentKey
        const tree = workbench.actionTree
        while (parent) {
            if (folded[parent]) return false
            const node = tree.find(entry => entry.treeKey === parent)
            parent = node ? node.parentKey : ""
        }
        return true
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
    function chooseRow(item) {
        if (item.groupRow) {
            selectedGroup = item.treeKey
            const state = Object.assign({}, folded)
            state[item.treeKey] = !state[item.treeKey]
            folded = state
        } else {
            selectedGroup = item.parentKey
            select(item.key)
        }
    }
    function groupEditor(operation, key, name) {
        groupDialog.operation = operation
        groupDialog.groupKey = key
        groupName.text = name
        groupDialog.open()
        groupName.forceActiveFocus()
    }
    function moveItem(sourceKey, targetKey, placement) {
        const result = workbench.moveTree(sourceKey, targetKey, placement)
        if (!result) return
        if (placement === "inside") {
            const state = Object.assign({}, folded)
            delete state[targetKey]
            folded = state
        }
        const moved = workbench.actionTree.find(item => item.treeKey === result)
        if (moved) selectedGroup = moved.groupRow ? moved.treeKey : moved.parentKey
        const index = filtered.findIndex(item => item.treeKey === result)
        if (index >= 0) list.positionViewAtIndex(index, ListView.Contain)
        if (selected) setFields()
    }
    function canMoveInto(sourceKey, parentKey) {
        return sourceKey !== parentKey && !(sourceKey.startsWith("g:") && parentKey.startsWith(sourceKey + "/"))
    }
    function chooseDestination(sourceKey) {
        const source = workbench.actionTree.find(item => item.treeKey === sourceKey)
        if (!source) return
        moveDialog.sourceKey = sourceKey
        moveDialog.parentKey = source.parentKey
        destination.model = workbench.actionTree.filter(item => item.groupRow && !item.preset
            && view.canMoveInto(sourceKey, item.treeKey)).map(item => ({ key: item.treeKey, label: item.group || item.name }))
        destination.currentIndex = Math.max(0, destination.indexOfValue(source.parentKey))
        moveDialog.open()
        destination.forceActiveFocus()
    }
    function rowMenu(item, row) {
        if (item.groupRow) {
            if (item.preset) return
            groupMenu.itemData = item
            groupMenu.popup(row, row.width / 2, row.height)
        } else {
            select(item.key)
            actionMenu.popup(row, row.width / 2, row.height)
        }
    }
    function createAction() {
        creating = true
        showDetails = true
        selectedKey = ""
        setFields()
        if (selectedGroup.startsWith("g:")) location.text = selectedGroup.substring(2) + "/"
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
            description: "管理自定义操作和内置工具。"
        }
        WorkButton { text: view.showDetails ? "隐藏详情" : "显示详情"; onClicked: view.showDetails = !view.showDetails }
        WorkButton { text: "分组"; iconName: "folder-plus"; onClicked: view.groupEditor("create", "", "") }
        WorkButton { text: "新建操作"; iconName: "plus"; primary: true; onClicked: view.createAction() }
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
                    objectName: "actionTreeList"
                    property string sourceKey: ""
                    property string targetKey: ""
                    property string placement: ""
                    property string dropHint: "拖到自定义分组或操作上"
                    property bool dragging: false
                    property point pressPoint
                    property point pointerPosition
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    model: view.filtered
                    clip: true
                    spacing: 3
                    Basic.ScrollBar.vertical: Basic.ScrollBar { }

                    function rowAt(point) {
                        return itemAt(contentX + point.x, contentY + point.y)
                    }
                    function updateTarget() {
                        targetKey = ""
                        placement = ""
                        dropHint = "松手可取消 · Esc 取消"
                        const point = pointerPosition
                        if (point.x < 0 || point.x >= width || point.y < 0 || point.y >= height) return
                        const row = rowAt(point) || rowAt(Qt.point(point.x, point.y + spacing))
                            || rowAt(Qt.point(point.x, point.y - spacing))
                        if (!row || row.modelData.preset || row.modelData.treeKey === sourceKey) return
                        const item = row.modelData
                        const fraction = mapToItem(row, point.x, point.y).y / row.height
                        const position = item.treeKey === "u:" ? "inside" : item.groupRow
                            ? (fraction < 0.25 ? "before" : fraction > 0.75 ? "after" : "inside")
                            : (fraction < 0.5 ? "before" : "after")
                        if (!view.canMoveInto(sourceKey, position === "inside" ? item.treeKey : item.parentKey)) return
                        targetKey = item.treeKey
                        placement = position
                        dropHint = (position === "inside" ? "移入分组：" : position === "before" ? "插到前面：" : "插到后面：") + item.name
                    }
                    function clearDrag() {
                        sourceKey = ""
                        targetKey = ""
                        placement = ""
                        dragging = false
                    }
                    onModelChanged: clearDrag()

                    Shortcut { sequence: "Escape"; enabled: list.dragging; onActivated: list.clearDrag() }
                    Timer {
                        interval: 16
                        repeat: true
                        running: list.dragging
                        onTriggered: {
                            const point = list.pointerPosition
                            if (point.x < 0 || point.x >= list.width || point.y < 0 || point.y >= list.height) return
                            const edge = Math.min(list.height / 4, 46)
                            const speed = point.y < edge ? -(edge - point.y) : Math.max(0, point.y - (list.height - edge))
                            if (!speed) return
                            const next = Math.max(list.originY, Math.min(list.originY + Math.max(0, list.contentHeight - list.height), list.contentY + speed / 3))
                            if (next === list.contentY) return
                            list.contentY = next
                            list.updateTarget()
                        }
                    }
                    MouseArea {
                        id: dragHandle
                        anchors.top: parent.top
                        anchors.bottom: parent.bottom
                        anchors.right: parent.right
                        anchors.rightMargin: 10
                        width: 44
                        z: 3
                        enabled: !search.text.trim()
                        preventStealing: true
                        cursorShape: list.dragging ? Qt.ClosedHandCursor : overGrip ? Qt.OpenHandCursor : Qt.ArrowCursor
                        hoverEnabled: true
                        readonly property bool overGrip: {
                            const scrollPosition = list.contentY
                            return containsMouse && gripAt(mapToItem(list, mouseX, mouseY), scrollPosition)
                        }

                        function gripAt(point, scrollPosition) {
                            const row = list.itemAt(list.contentX + point.x, scrollPosition + point.y)
                            if (!row || !row.grip.visible) return false
                            const local = list.mapToItem(row.grip, point.x, point.y)
                            return local.x >= 0 && local.x < row.grip.width && local.y >= 0 && local.y < row.grip.height
                        }
                        onPressed: mouse => {
                            const point = mapToItem(list, mouse.x, mouse.y)
                            if ((workbench.mac && mouse.modifiers & Qt.MetaModifier) || !gripAt(point, list.contentY)) {
                                mouse.accepted = false
                                return
                            }
                            list.cancelFlick()
                            list.pressPoint = point
                            list.sourceKey = list.rowAt(point).modelData.treeKey
                        }
                        onPositionChanged: mouse => {
                            if (!pressed || !list.sourceKey) return
                            const point = mapToItem(list, mouse.x, mouse.y)
                            if (!list.dragging && Math.hypot(point.x - list.pressPoint.x, point.y - list.pressPoint.y) < 6) return
                            list.pointerPosition = point
                            list.updateTarget()
                            list.dragging = true
                        }
                        onReleased: mouse => {
                            if (list.dragging) {
                                list.pointerPosition = mapToItem(list, mouse.x, mouse.y)
                                list.updateTarget()
                                if (list.targetKey) Qt.callLater(view.moveItem, list.sourceKey, list.targetKey, list.placement)
                            }
                            list.clearDrag()
                        }
                        onCanceled: list.clearDrag()
                    }
                    delegate: Basic.ItemDelegate {
                        id: row
                        required property var modelData
                        readonly property alias grip: grip
                        readonly property string dropPosition: list.targetKey === modelData.treeKey ? list.placement : ""
                        objectName: "treeDrop:" + modelData.treeKey
                        width: list.width - 10
                        height: Theme.rowHeight
                        rightPadding: 8
                        opacity: list.dragging && list.sourceKey === modelData.treeKey ? 0.5 : 1
                        text: modelData.name
                        hoverEnabled: true
                        activeFocusOnTab: true
                        leftPadding: 8 + Math.min(modelData.depth, 7) * 13
                        onClicked: view.chooseRow(modelData)
                        background: Rectangle {
                            radius: 6
                            color: row.dropPosition === "inside" ? Theme.accentWash : row.modelData.groupRow ? Theme.inset : view.selectedKey === row.modelData.key ? Theme.accentWash : row.hovered ? Theme.hover : "transparent"
                            border.color: row.visualFocus || row.dropPosition === "inside" ? Theme.accent : "transparent"
                        }
                        contentItem: RowLayout {
                            spacing: 9
                            Rectangle {
                                Layout.preferredWidth: 27
                                Layout.preferredHeight: 27
                                radius: 6
                                color: Theme.inset
                                Icon { anchors.centerIn: parent; size: 15; tint: Theme.accent; name: row.modelData.groupRow ? (view.folded[row.modelData.treeKey] ? "chevron-right" : "chevron-down") : row.modelData.builtin ? "shield" : "terminal" }
                            }
                            ColumnLayout {
                                Layout.fillWidth: true
                                spacing: 0
                                Text { Layout.fillWidth: true; text: row.modelData.name; textFormat: Text.PlainText; color: Theme.ink; elide: Text.ElideRight; font.pixelSize: 13; font.weight: row.modelData.groupRow ? Font.DemiBold : Font.Normal }
                                Text { Layout.fillWidth: true; text: row.modelData.group; textFormat: Text.PlainText; color: Theme.muted; elide: Text.ElideRight; font.pixelSize: 11; visible: !row.modelData.groupRow && !Theme.compact }
                            }
                            WorkButton {
                                visible: !row.modelData.groupRow
                                quiet: true
                                text: workbench.shellConfig.targets.includes("action:" + row.modelData.key) ? "取消固定" : "固定到右键"
                                iconName: workbench.shellConfig.targets.includes("action:" + row.modelData.key) ? "pin-off" : "pin"
                                onClicked: view.pin(row.modelData.key)
                            }
                            Rectangle {
                                id: grip
                                objectName: "treeDrag:" + row.modelData.treeKey
                                Layout.preferredWidth: 36
                                Layout.fillHeight: true
                                visible: !row.modelData.preset && row.modelData.treeKey !== "u:" && !search.text.trim()
                                color: row.hovered && dragHandle.overGrip ? Theme.hover : "transparent"
                                radius: 6
                                Icon { name: "grip-vertical"; tint: Theme.muted; anchors.centerIn: parent }
                            }
                        }
                        Rectangle {
                            visible: row.dropPosition === "before" || row.dropPosition === "after"
                            x: row.leftPadding
                            y: row.dropPosition === "before" ? 0 : row.height - height
                            width: row.width - x - 4
                            height: 3
                            radius: 1.5
                            color: Theme.accent
                        }
                        TapHandler {
                            acceptedButtons: Qt.RightButton
                            onTapped: view.rowMenu(row.modelData, row)
                        }
                        TapHandler {
                            enabled: workbench.mac
                            acceptedButtons: Qt.LeftButton
                            acceptedModifiers: Qt.MetaModifier
                            onTapped: view.rowMenu(row.modelData, row)
                        }
                        Keys.onPressed: event => {
                            if (event.key === Qt.Key_Menu || (event.key === Qt.Key_F10 && event.modifiers & Qt.ShiftModifier)) {
                                view.rowMenu(row.modelData, row)
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
                Text {
                    Layout.fillWidth: true
                    text: list.dragging ? list.dropHint : search.text.trim()
                        ? "搜索时可右键选择“移动到分组”。"
                        : "拖动行尾手柄排序，放到分组中间可移入。"
                    textFormat: Text.PlainText
                    elide: Text.ElideRight
                    color: list.dragging && list.targetKey ? Theme.accent : Theme.muted
                    font.pixelSize: 12
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
                        RowLayout {
                            Icon { name: "shield"; size: 15; tint: Theme.accent }
                            Text { text: "系统能力"; color: Theme.accent; font.pixelSize: 13; font.weight: Font.DemiBold }
                        }
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
    function pin(key) {
        const error = workbench.toggleShellPin(key)
        if (error) { notice.message = error; notice.open() }
    }
    Prompt { id: notice; title: "无法固定"; confirmText: "知道了" }
    Basic.Dialog {
        id: groupDialog
        property string operation
        property string groupKey
        anchors.centerIn: Basic.Overlay.overlay
        modal: true
        width: 340
        background: Rectangle { color: Theme.panel; border.color: Theme.line; radius: 10 }
        contentItem: ColumnLayout {
            Text { text: groupDialog.operation === "rename" ? "重命名分组" : "新建分组"; color: Theme.ink; font.pixelSize: 18 }
            Field { id: groupName; Layout.fillWidth: true; placeholderText: "分组名称"; onAccepted: saveGroup.clicked() }
            RowLayout {
                Layout.alignment: Qt.AlignRight
                WorkButton { text: "取消"; onClicked: groupDialog.close() }
                WorkButton {
                    id: saveGroup
                    text: "保存"
                    primary: true
                    onClicked: {
                        const result = workbench.editGroup(groupDialog.groupKey, groupName.text, groupDialog.operation)
                        if (result) { view.selectedGroup = result; groupDialog.close(); if (view.selected) view.setFields() }
                    }
                }
            }
        }
    }
    Basic.Dialog {
        id: moveDialog
        property string sourceKey
        property string parentKey
        anchors.centerIn: Basic.Overlay.overlay
        modal: true
        width: 340
        background: Rectangle { color: Theme.panel; border.color: Theme.line; radius: 10 }
        contentItem: ColumnLayout {
            Text { text: "移动到分组"; color: Theme.ink; font.pixelSize: 18 }
            Choice { id: destination; Layout.fillWidth: true; Accessible.name: "目标分组" }
            RowLayout {
                Layout.alignment: Qt.AlignRight
                WorkButton { text: "取消"; onClicked: moveDialog.close() }
                WorkButton {
                    text: "移动"
                    primary: true
                    enabled: destination.currentIndex >= 0 && destination.currentValue !== moveDialog.parentKey
                    onClicked: {
                        view.moveItem(moveDialog.sourceKey, destination.currentValue, "inside")
                        moveDialog.close()
                    }
                }
            }
        }
    }
    Basic.Menu {
        id: groupMenu
        property var itemData: null
        background: Rectangle { color: Theme.panel; border.color: Theme.line; radius: 8 }
        delegate: Basic.MenuItem {
            id: groupMenuItem
            contentItem: Text { text: groupMenuItem.text; color: Theme.ink; verticalAlignment: Text.AlignVCenter; opacity: groupMenuItem.enabled ? 1 : 0.38 }
            background: Rectangle { color: groupMenuItem.highlighted ? Theme.hover : "transparent"; radius: 4 }
        }
        Basic.Action { text: "新建子分组"; onTriggered: view.groupEditor("create", groupMenu.itemData.treeKey === "u:" ? "" : groupMenu.itemData.treeKey, "") }
        Basic.Action { text: "重命名"; enabled: groupMenu.itemData && groupMenu.itemData.treeKey !== "u:"; onTriggered: view.groupEditor("rename", groupMenu.itemData.treeKey, groupMenu.itemData.name) }
        Basic.Action { text: "移动到分组…"; enabled: groupMenu.itemData && groupMenu.itemData.treeKey !== "u:"; onTriggered: view.chooseDestination(groupMenu.itemData.treeKey) }
        Basic.Action { text: "删除空分组"; enabled: groupMenu.itemData && groupMenu.itemData.treeKey !== "u:"; onTriggered: workbench.editGroup(groupMenu.itemData.treeKey, "", "remove") }
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
        Basic.Action { text: "移动到分组…"; enabled: !view.readOnly; onTriggered: view.chooseDestination("a:" + view.selectedKey) }
        Basic.Action { text: "上移"; enabled: !view.readOnly; onTriggered: workbench.moveAction(view.selectedKey, -1) }
        Basic.Action { text: "下移"; enabled: !view.readOnly; onTriggered: workbench.moveAction(view.selectedKey, 1) }
        Basic.Action { text: "删除"; enabled: !view.readOnly; onTriggered: view.askDelete() }
    }
}
