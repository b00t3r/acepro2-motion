// Export a local copy for Motion Photo size/compatibility testing.
import Foundation
import AVFoundation

guard CommandLine.arguments.count == 3 else {
    fatalError("Usage: export_motion_video.swift input.mp4 output.mp4")
}
let input = URL(fileURLWithPath: CommandLine.arguments[1])
let output = URL(fileURLWithPath: CommandLine.arguments[2])
guard !FileManager.default.fileExists(atPath: output.path) else {
    fatalError("Refusing to overwrite output")
}
let asset = AVURLAsset(url: input)
guard let exporter = AVAssetExportSession(asset: asset, presetName: AVAssetExportPreset1920x1080) else {
    fatalError("1080p export unavailable")
}
exporter.outputURL = output
exporter.outputFileType = .mp4
exporter.shouldOptimizeForNetworkUse = true
let finished = DispatchSemaphore(value: 0)
exporter.exportAsynchronously { finished.signal() }
finished.wait()
guard exporter.status == .completed else {
    fatalError("Export failed: \(String(describing: exporter.error))")
}
let result = AVURLAsset(url: output)
for track in result.tracks {
    print("\(track.mediaType.rawValue): \(track.naturalSize), estimated bitrate \(track.estimatedDataRate)")
}
print("Duration: \(result.duration.seconds) seconds")
let bytes = try FileManager.default.attributesOfItem(atPath: output.path)[.size]!
print("Output bytes: \(bytes)")
