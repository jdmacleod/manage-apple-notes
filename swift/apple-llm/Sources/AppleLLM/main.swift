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

import AppleLLMCore
import Foundation
import FoundationModels

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
        exit(ExitCode.unavailable)
    }

    let inputData = FileHandle.standardInput.readDataToEndOfFile()
    let input: Input
    do {
        input = try JSONDecoder().decode(Input.self, from: inputData)
    } catch {
        fputs("error: failed to decode input JSON: \(error)\n", stderr)
        exit(ExitCode.generalError)
    }

    // Cap response tokens conservatively — total context is 4096 (system + user + response).
    // The system prompt alone is typically 1000–1500 tokens; leave headroom for the response.
    let options = GenerationOptions(maximumResponseTokens: cappedResponseTokens(requested: input.max_tokens))

    // First attempt — full content.
    do {
        let session = LanguageModelSession { input.system }
        let response = try await session.respond(to: input.user, options: options)
        print(response.content)
        return
    } catch {
        let desc = "\(error)"
        if isContextOverflowError(desc) {
            fputs(
                "error: context window exceeded (4096 tokens total).\n"
                    + "  Set batch_size: 1 in settings.local.yaml when using the apple provider.\n",
                stderr
            )
            exit(ExitCode.contextOverflow)
        }
        guard isLocaleError(desc) else {
            fputs("error: generation failed: \(error)\n", stderr)
            exit(ExitCode.generalError)
        }
        // Fall through to retry with stripped content.
    }

    // Retry — strip non-ASCII from both the system prompt and note body, then try again.
    // Notes that contain pasted foreign-language text (recipes, quotes, etc.) often
    // trigger the locale filter even when the title and most of the content are English.
    // The system prompt must also be stripped: it contains taxonomy folder names injected
    // by Python, which may include non-ASCII characters (accented names, CJK paths, etc.).
    let strippedSystem = stripToASCII(input.system)
    let strippedUser = stripToASCII(input.user)

    guard hasEnoughContent(strippedUser) else {
        // Too little ASCII content left to classify meaningfully.
        fputs("error: unsupported language or locale (insufficient ASCII content after stripping)\n", stderr)
        exit(ExitCode.unsupportedLocale)
    }

    do {
        let retrySession = LanguageModelSession { strippedSystem }
        let retryResponse = try await retrySession.respond(to: strippedUser, options: options)
        print(retryResponse.content)
    } catch {
        fputs("error: unsupported language or locale\n", stderr)
        exit(ExitCode.unsupportedLocale)
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
            exit(ExitCode.success)
        } else {
            fputs("error: macOS 26 or later is required for Apple Intelligence\n", stderr)
            exit(ExitCode.unavailable)
        }
    }
}
dispatchMain()
