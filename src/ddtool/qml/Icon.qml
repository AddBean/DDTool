import QtQuick
import QtQuick.Controls.Basic as Basic

Basic.Button {
    id: control
    property string name: ""
    property int size: 16
    property color tint: Theme.ink
    implicitWidth: size
    implicitHeight: size
    enabled: false
    focusPolicy: Qt.NoFocus
    Accessible.ignored: true
    padding: 0
    background: null
    display: Basic.AbstractButton.IconOnly
    icon.source: name ? Qt.resolvedUrl("icons/" + name + ".svg") : ""
    icon.width: size
    icon.height: size
    icon.color: tint
}
