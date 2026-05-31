// Bridge from Python subprocess to Apple's on-device Foundation Models framework.
//
// Protocol (stdin → stdout):
//   in:  {"system": "...", "user": "...", "max_tokens": 4096}
//   out: plain-text response on stdout
//
// Exit codes:
//   0 — success
//   1 — general error (bad input, unexpected failure)
//   2 — Apple Intelligence unavailable (device/settings)
//   3 — context window exceeded (reduce batch_size in settings.local.yaml)
//   4 — unsupported language or locale (note content not supported by on-device model)

import Foundation
import FoundationModels

struct Input: Decodable {
    let system: String
    let user: String
    let max_tokens: Int?
}

@available(macOS 26, *)
func run() async {
    switch SystemLanguageModel.default.availability {
    case .available:
        break
    case .unavailable(let reason):
        let msg: String
        switch reason {
        case .deviceNotEligible:
            msg = "device not eligible — Apple Intelligence requires an M-series Mac"
        case .appleIntelligenceNotEnabled:
            msg = "Apple Intelligence is not enabled — turn it on in System Settings → Apple Intelligence & Siri"
        case .modelNotReady:
            msg = "Apple Intelligence model is not ready — it may still be downloading"
        @unknown default:
            msg = "Apple Intelligence unavailable (\(reason))"
        }
        fputs("error: \(msg)\n", stderr)
        exit(2)
    }

    let inputData = FileHandle.standardInput.readDataToEndOfFile()
    let input: Input
    do {
        input = try JSONDecoder().decode(Input.self, from: inputData)
    } catch {
        fputs("error: failed to decode input JSON: \(error)\n", stderr)
        exit(1)
    }

    // Cap response tokens conservatively — total context is 4096 (system + user + response).
    // The system prompt alone is typically 1000–1500 tokens; leave headroom for the response.
    let maxResponse = min(input.max_tokens ?? 4096, 800)

    let session = LanguageModelSession {
        input.system
    }

    do {
        let options = GenerationOptions(maximumResponseTokens: maxResponse)
        let response = try await session.respond(to: input.user, options: options)
        print(response.content)
    } catch {
        let desc = "\(error)"
        if desc.contains("exceededContextWindowSize") || desc.contains("contextWindowSize") {
            fputs(
                "error: context window exceeded (4096 tokens total).\n"
                    + "  Set batch_size: 1 in settings.local.yaml when using the apple provider.\n",
                stderr
            )
            exit(3)
        }
        if desc.contains("unsupportedLanguageOrLocale") {
            fputs("error: unsupported language or locale\n", stderr)
            exit(4)
        }
        fputs("error: generation failed: \(error)\n", stderr)
        exit(1)
    }
}

// FoundationModels uses XPC callbacks that require the main run loop to be live.
// Blocking the main thread with a semaphore starves those callbacks, so the async
// Task never fires.  dispatchMain() runs GCD's event loop on the main thread,
// allowing XPC responses through.  Each exit path in run() calls exit() explicitly.
DispatchQueue.main.async {
    Task {
        if #available(macOS 26, *) {
            await run()
            exit(0)
        } else {
            fputs("error: macOS 26 or later is required for Apple Intelligence\n", stderr)
            exit(2)
        }
    }
}
dispatchMain()
