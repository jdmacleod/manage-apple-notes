import XCTest
@testable import AppleLLMCore

// MARK: — ExitCode

final class ExitCodeTests: XCTestCase {
    func testValues() {
        XCTAssertEqual(ExitCode.success, 0)
        XCTAssertEqual(ExitCode.generalError, 1)
        XCTAssertEqual(ExitCode.unavailable, 2)
        XCTAssertEqual(ExitCode.contextOverflow, 3)
        XCTAssertEqual(ExitCode.unsupportedLocale, 4)
    }

    func testValuesAreDistinct() {
        let codes: [Int32] = [
            ExitCode.success, ExitCode.generalError, ExitCode.unavailable,
            ExitCode.contextOverflow, ExitCode.unsupportedLocale,
        ]
        XCTAssertEqual(codes.count, Set(codes).count)
    }
}

// MARK: — Input

final class InputTests: XCTestCase {
    func testDecodeFullPayload() throws {
        let json = #"{"system":"sys","user":"usr","max_tokens":512}"#.data(using: .utf8)!
        let input = try JSONDecoder().decode(Input.self, from: json)
        XCTAssertEqual(input.system, "sys")
        XCTAssertEqual(input.user, "usr")
        XCTAssertEqual(input.max_tokens, 512)
    }

    func testDecodeWithoutMaxTokens() throws {
        let json = #"{"system":"s","user":"u"}"#.data(using: .utf8)!
        let input = try JSONDecoder().decode(Input.self, from: json)
        XCTAssertNil(input.max_tokens)
    }

    func testDecodeEmptyStrings() throws {
        let json = #"{"system":"","user":""}"#.data(using: .utf8)!
        let input = try JSONDecoder().decode(Input.self, from: json)
        XCTAssertEqual(input.system, "")
        XCTAssertEqual(input.user, "")
    }

    func testDecodeInvalidJSONThrows() {
        let json = "not json".data(using: .utf8)!
        XCTAssertThrowsError(try JSONDecoder().decode(Input.self, from: json))
    }

    func testDecodeMissingRequiredFieldThrows() {
        let json = #"{"system":"s"}"#.data(using: .utf8)!
        XCTAssertThrowsError(try JSONDecoder().decode(Input.self, from: json))
    }

    func testMemberwiseInitWithMaxTokens() {
        let input = Input(system: "a", user: "b", max_tokens: 100)
        XCTAssertEqual(input.system, "a")
        XCTAssertEqual(input.user, "b")
        XCTAssertEqual(input.max_tokens, 100)
    }

    func testMemberwiseInitDefaultMaxTokens() {
        let input = Input(system: "a", user: "b")
        XCTAssertNil(input.max_tokens)
    }
}

// MARK: — sanitizeForAppleIntelligence

final class SanitizeForAppleIntelligenceTests: XCTestCase {
    func testPureASCIIPassesThrough() {
        XCTAssertEqual(sanitizeForAppleIntelligence("hello world"), "hello world")
    }

    func testAccentedLatinNormalized() {
        // é/ü/ñ etc. decompose to base + combining mark; the combining mark is stripped.
        XCTAssertEqual(sanitizeForAppleIntelligence("café"), "cafe")
        XCTAssertEqual(sanitizeForAppleIntelligence("résumé"), "resume")
        XCTAssertEqual(sanitizeForAppleIntelligence("naïve"), "naive")
    }

    func testCJKTransliteratedToASCII() {
        // kCFStringTransformToLatin romanises CJK; result must be non-empty pure ASCII.
        let result = sanitizeForAppleIntelligence("日本語")
        XCTAssertFalse(result.isEmpty, "CJK should transliterate to non-empty romanisation")
        XCTAssertFalse(
            result.unicodeScalars.contains { $0.value > 0x7E },
            "result must be pure ASCII"
        )
    }

    func testMixedContentTransliteratesCJKPreservesLatin() {
        let result = sanitizeForAppleIntelligence("Hello 日本語 world")
        XCTAssert(result.hasPrefix("Hello "), "Latin words must survive unchanged")
        XCTAssert(result.hasSuffix(" world"), "Latin words must survive unchanged")
        XCTAssertNotEqual(result, "Hello world", "CJK must produce transliterated content, not empty")
        XCTAssertFalse(result.unicodeScalars.contains { $0.value > 0x7E })
    }

    func testTypographicCharsConvertedToASCII() {
        // Curly quotes, em dash, and ellipsis inserted by Apple autocorrect.
        XCTAssertEqual(sanitizeForAppleIntelligence("\u{2018}quoted\u{2019}"), "'quoted'")
        XCTAssertEqual(sanitizeForAppleIntelligence("\u{201C}quoted\u{201D}"), "\"quoted\"")
        XCTAssertEqual(sanitizeForAppleIntelligence("cost\u{2013}benefit"), "cost-benefit")
        XCTAssertEqual(sanitizeForAppleIntelligence("really\u{2026}"), "really...")
    }

    func testCurlyApostrophePreservesWord() {
        // U+2019 is the curly apostrophe Apple autocorrect uses in contractions.
        XCTAssertEqual(sanitizeForAppleIntelligence("it\u{2019}s great"), "it's great")
    }

    func testEmDashPreservedAsHyphen() {
        XCTAssertEqual(sanitizeForAppleIntelligence("a\u{2014}b"), "a-b")
    }

    func testMultipleWhitespaceCollapsed() {
        XCTAssertEqual(sanitizeForAppleIntelligence("a  b\n\tc"), "a b c")
    }

    func testLeadingTrailingWhitespaceRemoved() {
        XCTAssertEqual(sanitizeForAppleIntelligence("  hello  "), "hello")
    }

    func testEmptyStringReturnsEmpty() {
        XCTAssertEqual(sanitizeForAppleIntelligence(""), "")
    }

    func testEmojiStripped() {
        XCTAssertEqual(sanitizeForAppleIntelligence("hello \u{1F389} world"), "hello world")
    }

    func testNumbersAndPunctuationPreserved() {
        XCTAssertEqual(sanitizeForAppleIntelligence("note #42: cost $9.99"), "note #42: cost $9.99")
    }
}

// MARK: — hasEnoughContent

final class HasEnoughContentTests: XCTestCase {
    func testExactlyFiveWordsReturnsTrue() {
        XCTAssertTrue(hasEnoughContent("one two three four five"))
    }

    func testFourWordsReturnsFalse() {
        XCTAssertFalse(hasEnoughContent("one two three four"))
    }

    func testEmptyStringReturnsFalse() {
        XCTAssertFalse(hasEnoughContent(""))
    }

    func testSingleWordReturnsFalse() {
        XCTAssertFalse(hasEnoughContent("hello"))
    }

    func testManyWordsReturnsTrue() {
        XCTAssertTrue(hasEnoughContent("a b c d e f g h i j"))
    }

    func testCustomMinimumSatisfied() {
        XCTAssertTrue(hasEnoughContent("one two", minimumWords: 2))
    }

    func testCustomMinimumNotSatisfied() {
        XCTAssertFalse(hasEnoughContent("one", minimumWords: 2))
    }

    func testCustomMinimumOfOne() {
        XCTAssertTrue(hasEnoughContent("hello", minimumWords: 1))
    }

    func testCustomMinimumZeroAlwaysTrue() {
        XCTAssertTrue(hasEnoughContent("", minimumWords: 0))
    }
}

// MARK: — cappedResponseTokens

final class CappedResponseTokensTests: XCTestCase {
    // Default ceiling is 1600 (raised from 800 to avoid mid-JSON truncation on discover
    // batches, which can need 900+ tokens for 5 notes × 3 themes × 6 fields each).
    func testNilRequestedUsesCeiling() {
        XCTAssertEqual(cappedResponseTokens(requested: nil), 1600)
    }

    func testBelowCeilingPassesThrough() {
        XCTAssertEqual(cappedResponseTokens(requested: 400), 400)
    }

    func testAboveCeilingClampedToCeiling() {
        XCTAssertEqual(cappedResponseTokens(requested: 4096), 1600)
    }

    func testAtCeilingUnchanged() {
        XCTAssertEqual(cappedResponseTokens(requested: 1600), 1600)
    }

    func testBelowCeilingStillPassesThrough() {
        XCTAssertEqual(cappedResponseTokens(requested: 800), 800)
    }

    func testCustomCeilingClampsAbove() {
        XCTAssertEqual(cappedResponseTokens(requested: 1000, ceiling: 500), 500)
    }

    func testCustomCeilingPassesBelowThrough() {
        XCTAssertEqual(cappedResponseTokens(requested: 200, ceiling: 500), 200)
    }

    func testNilWithCustomCeilingUsesCeiling() {
        XCTAssertEqual(cappedResponseTokens(requested: nil, ceiling: 512), 512)
    }

    func testZeroRequestedReturnsZero() {
        XCTAssertEqual(cappedResponseTokens(requested: 0), 0)
    }
}

// MARK: — isContextOverflowError

final class IsContextOverflowErrorTests: XCTestCase {
    func testExceededContextWindowSizeMatches() {
        XCTAssertTrue(isContextOverflowError("exceededContextWindowSize"))
    }

    func testContextWindowSizeMatches() {
        XCTAssertTrue(isContextOverflowError("error: contextWindowSize limit reached"))
    }

    func testBothKeywordsMatch() {
        XCTAssertTrue(isContextOverflowError("error: exceededContextWindowSize (contextWindowSize=4096)"))
    }

    func testUnrelatedErrorDoesNotMatch() {
        XCTAssertFalse(isContextOverflowError("unsupportedLanguageOrLocale"))
    }

    func testEmptyStringDoesNotMatch() {
        XCTAssertFalse(isContextOverflowError(""))
    }

    func testPartialKeywordDoesNotMatch() {
        XCTAssertFalse(isContextOverflowError("contextWindow"))
    }
}

// MARK: — isLocaleError

final class IsLocaleErrorTests: XCTestCase {
    func testUnsupportedLanguageOrLocaleMatches() {
        XCTAssertTrue(isLocaleError("unsupportedLanguageOrLocale"))
    }

    func testLocaleErrorEmbeddedInLongerDescriptionMatches() {
        XCTAssertTrue(isLocaleError("FoundationModels.LanguageModelError: unsupportedLanguageOrLocale"))
    }

    func testContextOverflowErrorDoesNotMatch() {
        XCTAssertFalse(isLocaleError("exceededContextWindowSize"))
    }

    func testEmptyStringDoesNotMatch() {
        XCTAssertFalse(isLocaleError(""))
    }

    func testPartialKeywordDoesNotMatch() {
        XCTAssertFalse(isLocaleError("unsupportedLanguage"))
    }
}
