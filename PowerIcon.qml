import QtQuick
// Control paths match foamy-weather's settings and back buttons.

Item {
  id: root
  // Source resolution must not feed back into a layout's implicit size.
  implicitWidth: 18
  implicitHeight: 18
  property string name: "settings"
  readonly property var paths: ({
    "battery-low": '<rect x="2" y="6" width="18" height="12" rx="2"/><path d="M22 10v4M6 10v4"/>',
    "battery-full": '<rect x="2" y="6" width="18" height="12" rx="2"/><path d="M22 10v4M6 10v4M10 10v4M14 10v4M18 10v4"/>',
    "battery-medium": '<rect x="2" y="6" width="18" height="12" rx="2"/><path d="M22 10v4M6 10v4M10 10v4"/>',
    "battery-charging": '<path d="M6 6H4a2 2 0 0 0-2 2v8a2 2 0 0 0 2 2h3M15 6h3a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2h-3M22 10v4M11 6l-4 6h6l-4 6"/>',
    "plug": '<path d="M12 22v-5M9 8V2M15 8V2M7 8h10v4a5 5 0 0 1-10 0Z"/>',
    "leaf": '<path d="M11 20A7 7 0 0 1 9.8 6.1C15.5 5 17 4.5 19 2c1 2 2 4.2 2 8 0 5.5-4.8 10-10 10ZM2 22c0-6 6-11 11-14"/>',
    "scale": '<path d="m16 16 3-8 3 8c-1.7 1.3-4.3 1.3-6 0ZM2 16l3-8 3 8c-1.7 1.3-4.3 1.3-6 0ZM7 21h10M12 3v18M3 7l3-1c4 1 8 1 12-1l3 1"/>',
    "gauge": '<path d="m12 14 4-4M3.3 19a10 10 0 1 1 17.4 0Z"/>',
    "refresh-cw": "<path d=\"M3 12a9 9 0 0 1 9-9 9.75 9.75 0 0 1 6.74 2.74L21 8\"></path><path d=\"M21 3v5h-5\"></path><path d=\"M21 12a9 9 0 0 1-9 9 9.75 9.75 0 0 1-6.74-2.74L3 16\"></path><path d=\"M8 16H3v5\"></path>",
    "refresh": '<path d="M20 7v5h-5M4 17v-5h5"/><path d="M6.1 6.1A8 8 0 0 1 20 12M4 12a8 8 0 0 0 13.9 5.9"/>',
    "external-link": '<path d="M15 3h6v6M10 14 21 3M21 14v5a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5"/>',
    "app-window": '<rect x="2" y="4" width="20" height="16" rx="2"/><path d="M2 8h20M6 4v4"/>',
    "check": '<path d="m20 6-11 11-5-5"/>',
    "arrow-left": '<path d="m12 19-7-7 7-7M5 12h14"/>',
    "chevron-down": '<path d="m6 9 6 6 6-6"/>',
    "chevron-right": '<path d="m9 6 6 6-6 6"/>',
    "settings": '<path d="m10 3-.6 2.3-2 .9-2.1-.7-2 3.5 1.6 1.7v2.6L3.3 15l2 3.5 2.1-.7 2 .9L10 21h4l.6-2.3 2-.9 2.1.7 2-3.5-1.6-1.7v-2.6L20.7 9l-2-3.5-2.1.7-2-.9L14 3Z"/><circle cx="12" cy="12" r="3"/>'
  })
  property color color: "white"
  property real strokeWidth: 1.7
  Image {
  anchors.fill: parent
  sourceSize.width: Math.ceil(width * 2)
  sourceSize.height: Math.ceil(height * 2)
  fillMode: Image.PreserveAspectFit
  // Inline SVG keeps the original stroke geometry and follows the active theme.
  source: "data:image/svg+xml;charset=utf-8," + encodeURIComponent(
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="'
    + color.toString() + '" stroke-width="' + strokeWidth
    + '" stroke-linecap="round" stroke-linejoin="round">'
    + (paths[name] || paths.settings) + '</svg>')
}
}
