// OCR a PNG with macOS Vision and print every recognised line. Used by privacy.js to prove that hidden data is not in a screenshot.
//   swiftc -O ocr.swift -o /tmp/cs-ocr && /tmp/cs-ocr screenshot.png
import Foundation
import Vision
import AppKit

guard CommandLine.arguments.count > 1, let img = NSImage(contentsOfFile: CommandLine.arguments[1]),
      let cg = img.cgImage(forProposedRect: nil, context: nil, hints: nil) else { FileHandle.standardError.write("cannot read image\n".data(using: .utf8)!); exit(2) }
let req = VNRecognizeTextRequest()
req.recognitionLevel = .accurate
req.usesLanguageCorrection = false
// tall full-page screenshots: slice into overlapping bands so small text is recognised
let h = cg.height, w = cg.width, band = 1400, overlap = 120
var y = 0
while y < h {
    let hh = min(band, h - y)
    if let crop = cg.cropping(to: CGRect(x: 0, y: y, width: w, height: hh)) {
        let handler = VNImageRequestHandler(cgImage: crop, options: [:])
        try? handler.perform([req])
        for obs in req.results ?? [] { if let t = obs.topCandidates(1).first { print(t.string) } }
    }
    if y + hh >= h { break }
    y += band - overlap
}
