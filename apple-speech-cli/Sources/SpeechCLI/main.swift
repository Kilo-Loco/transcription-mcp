import Foundation
import Speech
import AVFAudio
import CoreMedia

struct WordResult: Codable, Sendable {
    let word: String
    let start: Double
    let end: Double
    let confidence: Double
}

struct SegmentResult: Codable, Sendable {
    let words: [WordResult]
    let start: Double
    let end: Double
    let text: String
}

struct TranscriptionOutput: Codable, Sendable {
    let segments: [SegmentResult]
    let language: String
    let duration: Double
}

@available(macOS 26.0, *)
func transcribe(fileURL: URL, localeID: String) async throws {
    let locale = Locale(identifier: localeID)

    let transcriber = SpeechTranscriber(
        locale: locale,
        transcriptionOptions: [],
        reportingOptions: [],
        attributeOptions: [.audioTimeRange]
    )

    // Try to ensure the speech model is available.
    // On most systems en-US ships with macOS — only download if truly missing.
    do {
        if let request = try await AssetInventory.assetInstallationRequest(
            supporting: [transcriber]
        ) {
            FileHandle.standardError.write(Data("Downloading speech model for \(localeID)...\n".utf8))
            try await request.downloadAndInstall()
        }
    } catch {
        // Download failed (e.g. entitlements issue in CI). Proceed anyway —
        // the model may already be installed and the check was wrong.
        FileHandle.standardError.write(
            Data("Warning: Could not verify speech model, proceeding anyway: \(error.localizedDescription)\n".utf8)
        )
    }

    let analyzer = SpeechAnalyzer(modules: [transcriber])
    let audioFile = try AVAudioFile(forReading: fileURL)

    let sampleRate = audioFile.processingFormat.sampleRate
    let frameCount = Double(audioFile.length)
    let totalDuration = frameCount / sampleRate

    // Use start(inputAudioFile:finishAfterFile:) instead of analyzeSequence
    // to avoid race condition where short files finalize before results are collected
    try await analyzer.start(inputAudioFile: audioFile, finishAfterFile: true)

    // Collect all results — the sequence completes when the file is fully processed
    var fullText = AttributedString("")
    for try await result in transcriber.results {
        fullText.append(result.text)
        fullText.append(AttributedString(" "))
    }

    // Build words from attributed string runs
    var allWords: [WordResult] = []
    for run in fullText.runs {
        let wordText = String(fullText.characters[run.range]).trimmingCharacters(
            in: .whitespacesAndNewlines
        )
        guard !wordText.isEmpty else { continue }

        let startTime: Double
        let endTime: Double
        if let timeRange = run.audioTimeRange {
            startTime = timeRange.start.seconds
            endTime = (timeRange.start + timeRange.duration).seconds
        } else {
            startTime = 0
            endTime = 0
        }

        allWords.append(WordResult(
            word: wordText,
            start: startTime,
            end: endTime,
            confidence: 1.0
        ))
    }

    // Group words into segments by gaps > 1.0s
    var segments: [SegmentResult] = []
    var currentSegmentWords: [WordResult] = []
    let gapThreshold = 1.0

    for word in allWords {
        if let lastWord = currentSegmentWords.last,
           word.start - lastWord.end > gapThreshold {
            let segText = currentSegmentWords.map(\.word).joined(separator: " ")
            segments.append(SegmentResult(
                words: currentSegmentWords,
                start: currentSegmentWords.first!.start,
                end: currentSegmentWords.last!.end,
                text: segText
            ))
            currentSegmentWords = []
        }
        currentSegmentWords.append(word)
    }

    if !currentSegmentWords.isEmpty {
        let segText = currentSegmentWords.map(\.word).joined(separator: " ")
        segments.append(SegmentResult(
            words: currentSegmentWords,
            start: currentSegmentWords.first!.start,
            end: currentSegmentWords.last!.end,
            text: segText
        ))
    }

    let output = TranscriptionOutput(
        segments: segments,
        language: localeID,
        duration: totalDuration
    )

    let encoder = JSONEncoder()
    encoder.outputFormatting = [.prettyPrinted, .sortedKeys]
    let data = try encoder.encode(output)
    print(String(data: data, encoding: .utf8)!)
}

// MARK: - Entry point using async main

guard CommandLine.arguments.count >= 2 else {
    FileHandle.standardError.write(
        Data("Usage: SpeechCLI <audio-file> [locale]\n".utf8)
    )
    exit(1)
}

let filePath = CommandLine.arguments[1]
let localeID = CommandLine.arguments.count >= 3 ? CommandLine.arguments[2] : "en-US"
let fileURL = URL(fileURLWithPath: filePath)

guard FileManager.default.fileExists(atPath: filePath) else {
    FileHandle.standardError.write(
        Data("Error: File not found: \(filePath)\n".utf8)
    )
    exit(1)
}

if #available(macOS 26.0, *) {
    do {
        try await transcribe(fileURL: fileURL, localeID: localeID)
    } catch {
        FileHandle.standardError.write(
            Data("Error: \(error)\n".utf8)
        )
        exit(1)
    }
} else {
    FileHandle.standardError.write(
        Data("Error: macOS 26.0 or later is required\n".utf8)
    )
    exit(1)
}
