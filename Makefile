UUID := agents-tray-limits@realleo
BUILD_DIR := build
STAGE_DIR := $(BUILD_DIR)/stage
DIST_DIR := dist
ZIP_NAME := $(UUID).zip
ZIP := $(DIST_DIR)/$(ZIP_NAME)
CHECKSUM := $(ZIP).sha256

.PHONY: check pack install uninstall clean

check:
	python3 -m py_compile bin/agents-tray-limits-helper.py tools/check_css.py tools/stage_release.py tools/render_vault_boy_animation.py tools/animation-rig/v16/prepare_shoulder_fix.py tools/animation-rig/v16/verify_master_good.py
	python3 -m json.tool metadata.json >/dev/null
	glib-compile-schemas --strict --dry-run schemas
	node --check extension.js
	node --check prefs.js
	node --check themeLogic.js
	node --check profileLogic.js
	node --check themeLoader.js
	@if [ -f i18n.js ]; then node --check i18n.js; fi
	@if [ -d locales ]; then find locales -type f -name '*.js' -exec node --check {} +; fi
	@if [ -d locales ]; then for catalog in locales/*.json; do [ ! -e "$$catalog" ] || python3 -m json.tool "$$catalog" >/dev/null; done; fi
	gjs -m tests/test_i18n.js
	gjs -m tests/test_theme.js
	gjs -m tests/test_profiles.js
	python3 tools/check_css.py
	python3 -m unittest discover -s tests -p 'test_*.py'
	python3 tools/render_vault_boy_animation.py --statuses worried critical dead --verify themes/fallout-2/assets/animation >/dev/null
	AGENTS_TRAY_RIG_CONFIG=perspective-preview-config-v6.json python3 tools/animation-rig/v16/verify_master_good.py --sprites-dir themes/fallout-2/assets/animation/good --motion-file tools/animation-rig/v16/fixtures/master-good-v6-motion.json >/dev/null

pack: check
	python3 tools/stage_release.py "$(STAGE_DIR)"
	glib-compile-schemas --strict "$(STAGE_DIR)/schemas"
	mkdir -p "$(DIST_DIR)"
	rm -f "$(ZIP)" "$(CHECKSUM)"
	cd "$(STAGE_DIR)" && zip -q -r -9 "../../$(ZIP)" .
	cd "$(DIST_DIR)" && sha256sum "$(ZIP_NAME)" > "$(ZIP_NAME).sha256"
	cd "$(DIST_DIR)" && sha256sum --check "$(ZIP_NAME).sha256"
	unzip -t "$(ZIP)"
	python3 tools/stage_release.py --verify "$(ZIP)"

install: pack
	./install.sh "$(ZIP)"

uninstall:
	./uninstall.sh

clean:
	rm -rf "$(BUILD_DIR)" "$(DIST_DIR)"
	find . -type d -name __pycache__ -prune -exec rm -rf {} +
