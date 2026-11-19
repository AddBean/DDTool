import QtQuick
import QtQuick.Controls.Basic as Basic
import QtQuick.Layouts
import QtQuick.Window

Basic.ApplicationWindow {
    id: window
    objectName: "ddtoolWorkbench"
    title: "豆荚工具"
    flags: Qt.Window | Qt.FramelessWindowHint
    minimumWidth: 800
    minimumHeight: 535
    width: Math.min(Math.max(minimumWidth, workbench.layoutValue("width")), Math.max(minimumWidth, Screen.desktopAvailableWidth))
    height: Math.min(Math.max(minimumHeight, workbench.layoutValue("height")), Math.max(minimumHeight, Screen.desktopAvailableHeight))
    color: Theme.canvas
    property bool canHide: false
    property string page: "actions"
    property bool collapsed: workbench.layoutValue("collapsed") !== 0
    readonly property var pages: [
        {"key": "actions", "label": "快捷操作", "icon": "›_"},
        {"key": "devices", "label": "手机工具", "icon": "▯"},
        {"key": "power", "label": "电源与锁屏", "icon": "◔"},
        {"key": "activity", "label": "运行动态", "icon": "≡"},
        {"key": "context", "label": "系统右键", "icon": "↗"},
        {"key": "settings", "label": "设置", "icon": "⊡"}
    ]
    signal quitRequested()

    function persist() {
        if (visibility === Window.Windowed) {
            workbench.saveLayoutValue("width", width)
            workbench.saveLayoutValue("height", height)
        }
        workbench.saveLayoutValue("collapsed", collapsed ? 1 : 0)
        actionPage.persist()
    }
    function toggleMaximized() {
        if (visibility === Window.Maximized) showNormal()
        else { persist(); showMaximized() }
    }
    function openPalette() {
        commandSearch.text = ""
        results.currentIndex = 0
        commandPalette.open()
    }
    onWidthChanged: if (visible && visibility === Window.Windowed) saveTimer.restart()
    onHeightChanged: if (visible && visibility === Window.Windowed) saveTimer.restart()
    onClosing: close => {
        persist()
        if (canHide) {
            close.accepted = false
            hide()
        } else {
            quitRequested()
        }
    }

    Binding { target: Theme; property: "dark"; value: workbench.theme === "dark" }
    Binding { target: Theme; property: "accentName"; value: workbench.accent }
    Binding { target: Theme; property: "compact"; value: workbench.compact }
    Timer { id: saveTimer; interval: 350; onTriggered: window.persist() }
    Shortcut { sequence: "Ctrl+K"; onActivated: window.openPalette() }
    Shortcut { sequences: [StandardKey.Close]; onActivated: window.close() }
    Shortcut { sequences: [StandardKey.Quit]; onActivated: { window.persist(); window.quitRequested() } }

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: 1
        spacing: 0
        Rectangle {
            Layout.fillWidth: true
            Layout.preferredHeight: 53
            color: Theme.panel
            Rectangle { anchors.bottom: parent.bottom; width: parent.width; height: 1; color: Theme.line }
            MouseArea {
                anchors.fill: parent
                onPressed: window.startSystemMove()
                onDoubleClicked: window.toggleMaximized()
            }
            RowLayout {
                anchors.fill: parent
                anchors.leftMargin: 13
                anchors.rightMargin: 10
                spacing: 8
                Rectangle {
                    Layout.preferredWidth: 27
                    Layout.preferredHeight: 27
                    radius: 8
                    color: Theme.accent
                    Text { anchors.centerIn: parent; text: "D"; color: Theme.onAccent; font.pixelSize: 16; font.bold: true }
                }
                Text { text: "豆荚工具"; color: Theme.ink; font.pixelSize: 14; font.weight: Font.DemiBold }
                Text { text: "/  工作台"; color: Theme.muted; font.pixelSize: 12 }
                Item { Layout.fillWidth: true }
                WorkButton {
                    Layout.preferredWidth: 154
                    text: "搜索操作       " + (workbench.mac ? "⌘ K" : "Ctrl K")
                    Accessible.name: "打开命令面板"
                    onClicked: window.openPalette()
                }
                Item { Layout.preferredWidth: 10 }
                WorkButton { text: "—"; quiet: true; Accessible.name: "最小化"; onClicked: window.showMinimized() }
                WorkButton { text: window.visibility === Window.Maximized ? "❐" : "□"; quiet: true; Accessible.name: "切换最大化"; onClicked: window.toggleMaximized() }
                WorkButton { text: "×"; quiet: true; Accessible.name: window.canHide ? "关闭窗口并驻留托盘" : "关闭窗口"; onClicked: window.close() }
            }
        }
        RowLayout {
            Layout.fillWidth: true
            Layout.fillHeight: true
            spacing: 0
            Rectangle {
                Layout.preferredWidth: window.collapsed || window.width < 910 ? 58 : 172
                Layout.fillHeight: true
                color: Theme.panel
                Rectangle { anchors.right: parent.right; width: 1; height: parent.height; color: Theme.line }
                ColumnLayout {
                    anchors.fill: parent
                    anchors.margins: 9
                    spacing: 5
                    RowLayout {
                        Layout.fillWidth: true
                        Text { Layout.fillWidth: true; visible: window.width >= 910 && !window.collapsed; leftPadding: 8; text: "工作区"; color: Theme.muted; font.pixelSize: 11; font.weight: Font.DemiBold }
                        WorkButton { text: "≡"; quiet: true; Accessible.name: "切换侧栏"; enabled: window.width >= 910; onClicked: { window.collapsed = !window.collapsed; window.persist() } }
                    }
                    Repeater {
                        model: window.pages
                        delegate: Basic.ItemDelegate {
                            id: nav
                            required property var modelData
                            Layout.fillWidth: true
                            implicitHeight: 43
                            text: modelData.label
                            Accessible.name: modelData.label
                            hoverEnabled: true
                            activeFocusOnTab: true
                            onClicked: window.page = modelData.key
                            background: Rectangle {
                                radius: 6
                                color: window.page === nav.modelData.key ? Theme.accentWash : nav.hovered ? Theme.hover : "transparent"
                                border.color: nav.visualFocus ? Theme.accent : "transparent"
                                Rectangle {
                                    visible: window.page === nav.modelData.key
                                    anchors.left: parent.left
                                    anchors.verticalCenter: parent.verticalCenter
                                    width: 2; height: 19; radius: 1; color: Theme.accent
                                }
                            }
                            contentItem: RowLayout {
                                spacing: 7
                                Text { text: nav.modelData.icon; font.family: Theme.mono; color: Theme.accent; Layout.preferredWidth: 17; font.pixelSize: 15 }
                                Text { Layout.fillWidth: true; visible: !window.collapsed && window.width >= 910; text: nav.modelData.label; color: Theme.ink; font.pixelSize: 13 }
                            }
                            Basic.ToolTip.visible: hovered && (window.collapsed || window.width < 910)
                            Basic.ToolTip.delay: 500
                            Basic.ToolTip.text: modelData.label
                        }
                    }
                    Item { Layout.fillHeight: true }
                    Text {
                        Layout.leftMargin: 8
                        visible: window.width >= 910 && !window.collapsed
                        text: "DDTOOL  /  DESKTOP"
                        font.family: Theme.mono
                        font.pixelSize: 10
                        color: Theme.muted
                    }
                }
            }
            StackLayout {
                Layout.fillWidth: true
                Layout.fillHeight: true
                Layout.margins: 20
                currentIndex: Math.max(0, window.pages.findIndex(item => item.key === window.page))
                ActionsPage { id: actionPage }
                DevicesPage { onShowActivity: window.page = "activity" }
                PowerPage { }
                ActivityPage { }
                ContextPage { }
                SettingsPage { }
            }
        }
        Rectangle {
            Layout.fillWidth: true
            Layout.preferredHeight: 35
            color: Theme.panel
            Rectangle { width: parent.width; height: 1; color: Theme.line }
            RowLayout {
                anchors.fill: parent
                anchors.leftMargin: 12
                anchors.rightMargin: 12
                spacing: 8
                Rectangle { width: 6; height: 6; radius: 3; color: workbench.latestError ? Theme.error : workbench.busy ? "#edbb75" : Theme.accent }
                Text {
                    Layout.fillWidth: true
                    text: workbench.latest
                    textFormat: Text.PlainText
                    color: workbench.latestError ? Theme.error : Theme.muted
                    elide: Text.ElideRight
                    font.pixelSize: 12
                }
                WorkButton { text: "运行动态 ↗"; quiet: true; implicitHeight: 28; onClicked: window.page = "activity" }
            }
        }
    }

    Basic.Dialog {
        id: commandPalette
        objectName: "commandPalette"
        anchors.centerIn: Basic.Overlay.overlay
        width: Math.min(530, window.width - 70)
        modal: true
        padding: 13
        onOpened: commandSearch.forceActiveFocus()
        background: Rectangle { color: Theme.panel; border.color: Theme.line; radius: 10 }
        Basic.Overlay.modal: Rectangle { color: "#83090d0e" }
        contentItem: ColumnLayout {
            spacing: 8
            Field {
                id: commandSearch
                Layout.fillWidth: true
                placeholderText: "输入名称搜索，回车执行，Esc 关闭"
                Accessible.name: "命令面板搜索"
                onTextChanged: results.currentIndex = 0
                onAccepted: results.choose()
                Keys.onDownPressed: results.incrementCurrentIndex()
                Keys.onUpPressed: results.decrementCurrentIndex()
            }
            ListView {
                id: results
                Layout.fillWidth: true
                Layout.preferredHeight: 245
                clip: true
                model: window.pages.map(item => ({"name": item.label, "group": "前往页面", "key": item.key, "page": true}))
                    .concat(workbench.actionItems).filter(item => (item.name + " " + item.group).toLocaleLowerCase().includes(commandSearch.text.trim().toLocaleLowerCase()))
                function choose() {
                    const item = model[currentIndex]
                    if (!item) return
                    commandPalette.close()
                    if (item.page) window.page = item.key
                    else workbench.runAction(item.key)
                }
                delegate: Basic.ItemDelegate {
                    id: result
                    required property int index
                    required property var modelData
                    width: results.width
                    height: 36
                    text: modelData.name
                    onClicked: { results.currentIndex = index; results.choose() }
                    contentItem: RowLayout {
                        Text { Layout.fillWidth: true; text: result.modelData.name; textFormat: Text.PlainText; color: Theme.ink; elide: Text.ElideRight }
                        Text { text: result.modelData.group; textFormat: Text.PlainText; color: Theme.muted; font.pixelSize: 12 }
                    }
                    background: Rectangle { color: results.currentIndex === result.index ? Theme.accentWash : result.hovered ? Theme.hover : "transparent"; radius: 5 }
                }
                Text { anchors.centerIn: parent; visible: results.count === 0; text: "没有匹配结果"; color: Theme.muted }
            }
        }
    }

    Repeater {
        model: [Qt.LeftEdge, Qt.RightEdge, Qt.TopEdge, Qt.BottomEdge,
                Qt.LeftEdge | Qt.TopEdge, Qt.RightEdge | Qt.TopEdge,
                Qt.LeftEdge | Qt.BottomEdge, Qt.RightEdge | Qt.BottomEdge]
        delegate: MouseArea {
            required property int modelData
            readonly property bool leftEdge: (modelData & Qt.LeftEdge) !== 0
            readonly property bool rightEdge: (modelData & Qt.RightEdge) !== 0
            readonly property bool topEdge: (modelData & Qt.TopEdge) !== 0
            readonly property bool bottomEdge: (modelData & Qt.BottomEdge) !== 0
            readonly property bool horizontalEdge: leftEdge || rightEdge
            readonly property bool verticalEdge: topEdge || bottomEdge
            readonly property int thickness: 5
            z: horizontalEdge && verticalEdge ? 3 : 2
            x: leftEdge ? 0 : rightEdge ? window.width - width : thickness
            y: topEdge ? 0 : bottomEdge ? window.height - height : thickness
            width: horizontalEdge ? thickness : window.width - thickness * 2
            height: verticalEdge ? thickness : window.height - thickness * 2
            visible: window.visibility === Window.Windowed
            cursorShape: horizontalEdge && verticalEdge ? (leftEdge === topEdge ? Qt.SizeFDiagCursor : Qt.SizeBDiagCursor)
                       : horizontalEdge ? Qt.SizeHorCursor : Qt.SizeVerCursor
            onPressed: window.startSystemResize(modelData)
        }
    }
}
