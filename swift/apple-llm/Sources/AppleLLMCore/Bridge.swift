// Pure-logic helpers shared between the apple-llm executable and the test suite.
// No FoundationModels dependency — everything here compiles without Apple Intelligence.
import Foundation

// MARK: — Exit codes

public enum ExitCode {
    public static let success: Int32 = 0
    public static let generalError: Int32 = 1
    public static let unavailable: Int32 = 2
    public static let contextOverflow: Int32 = 3
    public static let unsupportedLocale: Int32 = 4
}

// MARK: — Input

/// JSON payload received on stdin.
public struct Input: Decodable, Sendable {
    public let system: String
    public let user: String
    public let max_tokens: Int?

    public init(system: String, user: String, max_tokens: Int? = nil) {
        self.system = system
        self.user = user
        self.max_tokens = max_tokens
    }
}

// MARK: — Helpers

/// Normalize characters to the ASCII subset Apple Intelligence can process.
///
/// Three-pass approach:
///
/// 1. Replace common typographic Unicode with ASCII equivalents (curly quotes,
///    em/en dash, ellipsis).  Apple's own autocorrect inserts these into normal
///    English notes, so without this step "it's" splits at the apostrophe.
///
/// 2. Transliterate any non-Latin script to Latin romanisation via
///    `kCFStringTransformToLatin` (CJK → pinyin/romaji, Arabic → romanised,
///    etc.), then strip diacritics via `kCFStringTransformStripCombiningMarks`
///    so "café" → "cafe", "résumé" → "resume", "東京" → "Dong Jing".
///
/// 3. Filter the result to printable ASCII (U+0020-U+007E) plus standard
///    whitespace (tab/newline/CR); collapse whitespace runs into single spaces.
public func sanitizeForAppleIntelligence(_ text: String) -> String {
    if text.isEmpty { return text }

    // Pass 1 — typographic normalisation
    var result = text
        .replacingOccurrences(of: "\u{2018}", with: "'")   // ' LEFT SINGLE QUOTATION MARK
        .replacingOccurrences(of: "\u{2019}", with: "'")   // ' RIGHT SINGLE QUOTATION MARK
        .replacingOccurrences(of: "\u{201C}", with: "\"")  // " LEFT DOUBLE QUOTATION MARK
        .replacingOccurrences(of: "\u{201D}", with: "\"")  // " RIGHT DOUBLE QUOTATION MARK
        .replacingOccurrences(of: "\u{2013}", with: "-")   // – EN DASH
        .replacingOccurrences(of: "\u{2014}", with: "-")   // — EM DASH
        .replacingOccurrences(of: "\u{2026}", with: "...") // … HORIZONTAL ELLIPSIS

    // Pass 2 — script transliteration + diacritic stripping
    let ms = NSMutableString(string: result) as CFMutableString
    CFStringTransform(ms, nil, kCFStringTransformToLatin, false)
    CFStringTransform(ms, nil, kCFStringTransformStripCombiningMarks, false)
    result = ms as String

    // Pass 3 — filter to printable ASCII + standard whitespace; collapse runs
    return result.unicodeScalars
        .filter {
            let v = $0.value
            return (v >= 0x20 && v <= 0x7E) || v == 0x09 || v == 0x0A || v == 0x0D
        }
        .map { Character($0) }
        .reduce(into: "") { $0.append($1) }
        .components(separatedBy: .whitespacesAndNewlines)
        .filter { !$0.isEmpty }
        .joined(separator: " ")
}

/// Returns `true` when `text` contains at least `minimumWords` whitespace-delimited tokens.
public func hasEnoughContent(_ text: String, minimumWords: Int = 5) -> Bool {
    text.split(separator: " ").count >= minimumWords
}

/// Returns `min(requested ?? ceiling, ceiling)` — safe response token budget.
///
/// Ceiling is set to 1600 rather than the obvious 4096 because the total
/// FoundationModels context is 4096 tokens (system + user + response combined).
/// A typical system prompt consumes 1200–1500 tokens, leaving roughly 2500 for
/// user content + response.  1600 gives comfortable headroom for a discover batch
/// of 5 notes (response ~900 tokens) while staying well within the 4096 ceiling.
/// The old 800-token ceiling caused mid-JSON truncation on discover batches and
/// "no JSON object found" parse errors.
public func cappedResponseTokens(requested: Int?, ceiling: Int = 1600) -> Int {
    min(requested ?? ceiling, ceiling)
}

/// Returns `true` when an error description indicates a context-window overflow.
public func isContextOverflowError(_ description: String) -> Bool {
    description.contains("exceededContextWindowSize") || description.contains("contextWindowSize")
}

/// Returns `true` when an error description indicates an unsupported language or locale.
public func isLocaleError(_ description: String) -> Bool {
    description.contains("unsupportedLanguageOrLocale")
}
