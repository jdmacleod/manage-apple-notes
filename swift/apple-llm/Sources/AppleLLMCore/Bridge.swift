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

/// Strip all non-ASCII characters from `text` and collapse whitespace into single spaces.
public func stripToASCII(_ text: String) -> String {
    text.unicodeScalars
        .filter { $0.value < 0x80 }
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
public func cappedResponseTokens(requested: Int?, ceiling: Int = 800) -> Int {
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
