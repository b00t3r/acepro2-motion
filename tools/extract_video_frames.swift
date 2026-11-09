import Foundation
import AVFoundation
import ImageIO
import UniformTypeIdentifiers

// Offline sampling of a copied test clip; no camera access or video changes.
let arguments = CommandLine.arguments
guard arguments.count == 3 else { fatalError("Usage: extract_video_frames.swift input.mp4 output-directory") }
let asset = AVURLAsset(url: URL(fileURLWithPath: arguments[1]))
let output = URL(fileURLWithPath: arguments[2], isDirectory: true)
try FileManager.default.createDirectory(at: output, withIntermediateDirectories: true)
let duration = asset.duration.seconds
guard duration.isFinite && duration > 0 else { fatalError("Invalid video duration") }
let generator = AVAssetImageGenerator(asset: asset)
generator.appliesPreferredTrackTransform = true
generator.maximumSize = CGSize(width: 960, height: 540)
generator.requestedTimeToleranceBefore = .zero
generator.requestedTimeToleranceAfter = .zero
print("Duration: \(duration) seconds")
for requested in [0.1, 0.5, 1.0, 1.5, 2.0, 2.5, 3.0] where requested < duration {
    var actual = CMTime.zero
    let frame = try generator.copyCGImage(at: CMTime(seconds: requested, preferredTimescale: 600), actualTime: &actual)
    let destination = output.appendingPathComponent(String(format: "frame_%04d.png", Int(requested * 1000)))
    guard let writer = CGImageDestinationCreateWithURL(destination as CFURL, UTType.png.identifier as CFString, 1, nil) else {
        fatalError("Cannot create output image")
    }
    CGImageDestinationAddImage(writer, frame, nil)
    guard CGImageDestinationFinalize(writer) else { fatalError("Cannot save output image") }
    print(String(format: "Requested %.3f, actual %.3f", requested, actual.seconds))
}
