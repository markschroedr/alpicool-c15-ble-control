#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
APP="$ROOT/Alpicool Control.app"
CONTENTS="$APP/Contents"
MACOS="$CONTENTS/MacOS"
BUILD_DIR="$ROOT/.build-app"

mkdir -p "$MACOS" "$ROOT/logs" "$BUILD_DIR"

cat > "$CONTENTS/Info.plist" <<'PLIST'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>CFBundleExecutable</key>
  <string>AlpicoolControl</string>
  <key>CFBundleIdentifier</key>
  <string>com.alpicool.c15-ble-control</string>
  <key>CFBundleName</key>
  <string>Alpicool Control</string>
  <key>CFBundleDisplayName</key>
  <string>Alpicool Control</string>
  <key>CFBundlePackageType</key>
  <string>APPL</string>
  <key>CFBundleVersion</key>
  <string>1</string>
  <key>CFBundleShortVersionString</key>
  <string>0.1</string>
  <key>LSMinimumSystemVersion</key>
  <string>13.0</string>
  <key>NSBluetoothAlwaysUsageDescription</key>
  <string>Alpicool Control uses Bluetooth to read and change the fridge temperature.</string>
  <key>NSBluetoothPeripheralUsageDescription</key>
  <string>Alpicool Control uses Bluetooth to read and change the fridge temperature.</string>
</dict>
</plist>
PLIST

cat > "$BUILD_DIR/AlpicoolControl.swift" <<'SWIFT'
import CoreBluetooth
import Foundation

final class BluetoothPermissionProbe: NSObject, CBCentralManagerDelegate {
    private var manager: CBCentralManager?
    private let deadline: Date

    override init() {
        self.deadline = Date().addingTimeInterval(6)
        super.init()
        self.manager = CBCentralManager(delegate: self, queue: nil)
    }

    func centralManagerDidUpdateState(_ central: CBCentralManager) {
        CFRunLoopStop(CFRunLoopGetMain())
    }

    func waitBriefly() {
        while Date() < deadline {
            CFRunLoopRunInMode(.defaultMode, 0.25, false)
            if manager?.state != .unknown {
                break
            }
        }
    }
}

func appendHandle(_ path: String) -> FileHandle {
    FileManager.default.createFile(atPath: path, contents: nil)
    let handle = try! FileHandle(forWritingTo: URL(fileURLWithPath: path))
    try! handle.seekToEnd()
    return handle
}

let bundleURL = Bundle.main.bundleURL
let rootURL = bundleURL.deletingLastPathComponent()
let root = rootURL.path
let logDir = rootURL.appendingPathComponent("logs").path
try? FileManager.default.createDirectory(atPath: logDir, withIntermediateDirectories: true)

let stdoutHandle = appendHandle("\(logDir)/app.log")
let stderrHandle = appendHandle("\(logDir)/app.err.log")

let stamp = ISO8601DateFormatter().string(from: Date())
stdoutHandle.write("== \(stamp) ==\n".data(using: .utf8)!)

let probe = BluetoothPermissionProbe()
probe.waitBriefly()

let process = Process()
process.executableURL = rootURL.appendingPathComponent("control.sh")
let args = Array(CommandLine.arguments.dropFirst())
process.arguments = args.isEmpty ? ["status"] : args
process.standardOutput = stdoutHandle
process.standardError = stderrHandle

do {
    try process.run()
    process.waitUntilExit()
    exit(process.terminationStatus)
} catch {
    stderrHandle.write("Failed to run control.sh: \(error)\n".data(using: .utf8)!)
    exit(1)
}
SWIFT

/usr/bin/swiftc "$BUILD_DIR/AlpicoolControl.swift" -o "$MACOS/AlpicoolControl" -framework CoreBluetooth
plutil -lint "$CONTENTS/Info.plist" >/dev/null

echo "Built: $APP"
