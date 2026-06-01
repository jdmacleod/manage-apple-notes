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

// MARK: — stripToASCII

final class StripToASCIITests: XCTestCase {
    func testPureASCIIPassesThrough() {
        XCTAssertEqual(stripToASCII("hello world"), "hello world")
    }

    func testNonASCIICharactersRemoved() {
        XCTAssertEqual(stripToASCII("café"), "caf")
    }

    func testMixedContentPreservesASCIIWords() {
        XCTAssertEqual(stripToASCII("Hello 日本語 world"), "Hello world")
    }

    func testMultipleWhitespaceCollapsed() {
        XCTAssertEqual(stripToASCII("a  b\n\tc"), "a b c")
    }

    func testLeadingTrailingWhitespaceRemoved() {
        XCTAssertEqual(stripToASCII("  hello  "), "hello")
    }

    func testEmptyStringReturnsEmpty() {
        XCTAssertEqual(stripToASCII(""), "")
    }

    func testAllNonASCIIReturnsEmpty() {
        XCTAssertEqual(stripToASCII("日本語"), "")
    }

    func testEmojiStripped() {
        XCTAssertEqual(stripToASCII("hello 🎉 world"), "hello world")
    }

    func testAccentedLatinStripped() {
        XCTAssertEqual(stripToASCII("résumé"), "rsum")
    }

    func testNumbersAndPunctuationPreserved() {
        XCTAssertEqual(stripToASCII("note #42: cost $9.99"), "note #42: cost $9.99")
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
    func testNilRequestedUsesCeiling() {
        XCTAssertEqual(cappedResponseTokens(requested: nil), 800)
    }

    func testBelowCeilingPassesThrough() {
        XCTAssertEqual(cappedResponseTokens(requested: 400), 400)
    }

    func testAboveCeilingClampedToCeiling() {
        XCTAssertEqual(cappedResponseTokens(requested: 4096), 800)
    }

    func testAtCeilingUnchanged() {
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
