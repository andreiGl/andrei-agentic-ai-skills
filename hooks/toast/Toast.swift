import AppKit

// Toast popup: small non-activating panel in the top-right corner.
// Usage: Toast "<title>" "<subtitle>"
// Auto-dismisses after 20 s; click anywhere on it to dismiss early.
// Does not steal keyboard focus. Claude-styled: cream panel,
// terracotta accent bar, Claude app icon.

let args = CommandLine.arguments
guard args.count >= 2 else { exit(1) }
let title = args[1]
let subtitle = args.count >= 3 ? args[2] : ""

// Claude brand palette
let cream = NSColor(calibratedRed: 0.941, green: 0.933, blue: 0.898, alpha: 1)      // #F0EEE5
let creamDark = NSColor(calibratedRed: 0.161, green: 0.157, blue: 0.141, alpha: 1)  // dark mode
let terracotta = NSColor(calibratedRed: 0.851, green: 0.467, blue: 0.341, alpha: 1) // #D97757

let app = NSApplication.shared
app.setActivationPolicy(.accessory)

let width: CGFloat = 360
let height: CGFloat = 78
let panel = NSPanel(
    contentRect: NSRect(x: 0, y: 0, width: width, height: height),
    styleMask: [.borderless, .nonactivatingPanel],
    backing: .buffered, defer: false)
panel.level = .floating
panel.isOpaque = false
panel.backgroundColor = .clear
panel.hasShadow = true
panel.hidesOnDeactivate = false
panel.collectionBehavior = [.canJoinAllSpaces, .fullScreenAuxiliary]

let box = NSView(frame: NSRect(x: 0, y: 0, width: width, height: height))
box.wantsLayer = true
let isDark = NSApp.effectiveAppearance.bestMatch(from: [.darkAqua, .aqua]) == .darkAqua
box.layer?.backgroundColor = (isDark ? creamDark : cream).cgColor
box.layer?.cornerRadius = 14
box.layer?.cornerCurve = .continuous
box.layer?.masksToBounds = true
box.layer?.borderWidth = 1
box.layer?.borderColor = NSColor.separatorColor.withAlphaComponent(0.6).cgColor
panel.contentView = box

// Terracotta accent bar on the left edge.
let accent = NSView()
accent.wantsLayer = true
accent.layer?.backgroundColor = terracotta.cgColor
box.addSubview(accent)
accent.translatesAutoresizingMaskIntoConstraints = false
NSLayoutConstraint.activate([
    accent.leadingAnchor.constraint(equalTo: box.leadingAnchor),
    accent.topAnchor.constraint(equalTo: box.topAnchor),
    accent.bottomAnchor.constraint(equalTo: box.bottomAnchor),
    accent.widthAnchor.constraint(equalToConstant: 4),
])

// Claude app icon; icns sits next to this binary.
let iconView = NSImageView()
let iconPath = URL(fileURLWithPath: CommandLine.arguments[0])
    .deletingLastPathComponent().appendingPathComponent("claude.icns").path
let icon = NSImage(contentsOfFile: iconPath) ?? NSApp.applicationIconImage
iconView.image = icon
box.addSubview(iconView)
iconView.translatesAutoresizingMaskIntoConstraints = false
NSLayoutConstraint.activate([
    iconView.leadingAnchor.constraint(equalTo: box.leadingAnchor, constant: 16),
    iconView.centerYAnchor.constraint(equalTo: box.centerYAnchor),
    iconView.widthAnchor.constraint(equalToConstant: 30),
    iconView.heightAnchor.constraint(equalToConstant: 30),
])

// Event line + session title to the right of the icon.
let eyebrow = NSTextField(labelWithString: subtitle.isEmpty ? "Claude Code" : "Claude Code  -  \(subtitle)")
eyebrow.font = .systemFont(ofSize: 11, weight: .medium)
eyebrow.textColor = .secondaryLabelColor

let titleField = NSTextField(labelWithString: title)
titleField.font = .systemFont(ofSize: 13, weight: .semibold)
titleField.lineBreakMode = .byWordWrapping
titleField.maximumNumberOfLines = 2
titleField.preferredMaxLayoutWidth = width - 32 - 30 - 12

let stack = NSStackView(views: [eyebrow, titleField])
stack.orientation = .vertical
stack.alignment = .leading
stack.spacing = 3
box.addSubview(stack)
stack.translatesAutoresizingMaskIntoConstraints = false
NSLayoutConstraint.activate([
    stack.leadingAnchor.constraint(equalTo: iconView.trailingAnchor, constant: 12),
    stack.trailingAnchor.constraint(lessThanOrEqualTo: box.trailingAnchor, constant: -16),
    stack.centerYAnchor.constraint(equalTo: box.centerYAnchor),
])

// Click anywhere on the toast to dismiss it.
let click = NSClickGestureRecognizer(target: app, action: #selector(NSApplication.terminate(_:)))
box.addGestureRecognizer(click)

// Position at top-right of the main screen.
if let screen = NSScreen.main {
    let frame = screen.visibleFrame
    panel.setFrameOrigin(NSPoint(
        x: frame.maxX - width - 16,
        y: frame.maxY - height - 16))
}

Timer.scheduledTimer(withTimeInterval: 20.0, repeats: false) { _ in
    NSApp.terminate(nil)
}

panel.orderFrontRegardless()
app.run()
