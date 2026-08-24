BLENDER ?= /snap/blender/current/blender
BLENDER_ENV = XDG_CONFIG_HOME=/tmp/agents-tray-blender-v16-config XDG_CACHE_HOME=/tmp/agents-tray-blender-v16-cache

.PHONY: build render preview verify clean

build:
	$(BLENDER_ENV) $(BLENDER) --background --factory-startup --python build_vault_boy.py -- --build

render: build
	$(BLENDER_ENV) $(BLENDER) --background vault-boy-v16.blend --python build_vault_boy.py -- --render-good
	$(BLENDER_ENV) $(BLENDER) --background vault-boy-v16.blend --python build_vault_boy.py -- --render-turntable --quick

preview: render
	python3 make_previews.py

verify:
	$(BLENDER_ENV) $(BLENDER) --background vault-boy-v16.blend --python verify_blend.py
	python3 verify_prototype.py

clean:
	rm -rf render/good/raw render/good/sprites render/turntable/raw previews/*.gif previews/*.mp4 previews/good-contact-sheet.png
