import QtQuick
import QtQuick.Layouts

ColumnLayout {
    property alias title: heading.text
    property alias description: subheading.text
    spacing: 5
    Text {
        id: heading
        Layout.fillWidth: true
        textFormat: Text.PlainText
        font.pixelSize: 27
        font.weight: Font.DemiBold
        color: Theme.ink
    }
    Text {
        id: subheading
        Layout.fillWidth: true
        textFormat: Text.PlainText
        font.pixelSize: 13
        color: Theme.muted
        wrapMode: Text.Wrap
    }
}
