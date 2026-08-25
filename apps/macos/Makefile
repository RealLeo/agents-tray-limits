REPO_ROOT := $(abspath ../..)
BUILD_ROOT := $(REPO_ROOT)/build/macos

.PHONY: check build pack clean

check:
	@command -v swift >/dev/null || { echo 'Swift 5.9+ is required for macOS core tests.' >&2; exit 1; }
	swift test
	@if [ "$$(uname -s)" = Darwin ]; then \
		command -v xcodebuild >/dev/null; \
		xcodebuild -scheme AgentsTrayMacApp -configuration Debug -destination 'generic/platform=macOS' -derivedDataPath "$(BUILD_ROOT)/DerivedData" CODE_SIGNING_ALLOWED=NO build; \
	else \
		echo 'AppKit/SwiftUI build skipped: macOS is required.'; \
	fi

build:
	@command -v xcodebuild >/dev/null || { echo 'Xcode is required.' >&2; exit 1; }
	xcodebuild -scheme AgentsTrayMacApp -configuration Debug -destination 'platform=macOS' -derivedDataPath "$(BUILD_ROOT)/DerivedData" CODE_SIGNING_ALLOWED=NO build

pack:
	./scripts/package_release.sh

clean:
	rm -rf "$(BUILD_ROOT)" "$(REPO_ROOT)/dist/Agents-Tray-Limits-macOS.zip" "$(REPO_ROOT)/dist/Agents-Tray-Limits-macOS.zip.sha256"
	rm -rf .build
