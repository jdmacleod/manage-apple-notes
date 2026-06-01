# apple-llm — Swift CLI bridge for Apple's FoundationModels framework
# Self-documenting: run 'make' or 'make help' to list available targets.
# From the repo root: make -C swift/apple-llm [target]
.DEFAULT_GOAL := help

BINARY      := apple-llm
RELEASE_DIR := .build/release
DEBUG_DIR   := .build/debug

.PHONY: help build debug test clean smoke

help: ## Show available targets
	@echo
	@echo "Usage: make [target]"
	@echo
	@awk -F ':.*## ' '/^[A-Za-z0-9_.-]+:.*## /{printf "  %-8s %s\n", $$1, $$2}' Makefile | sort
	@echo

build: ## Compile the release binary → .build/release/apple-llm
	swift build -c release

debug: ## Compile a debug binary with symbols → .build/debug/apple-llm
	swift build

test: ## Run the Swift test suite
	swift test

clean: ## Remove all build artefacts (.build/)
	swift package clean

smoke: build ## Build then run a quick end-to-end smoke test (requires Apple Intelligence)
	@echo '{"system":"You are a helpful assistant.","user":"Reply with the single word: OK","max_tokens":10}' \
		| ./$(RELEASE_DIR)/$(BINARY)
