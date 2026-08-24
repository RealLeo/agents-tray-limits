BLENDER ?= /snap/blender/current/blender
BLENDER_ENV = XDG_CONFIG_HOME=/tmp/agents-tray-blender-config XDG_CACHE_HOME=/tmp/agents-tray-blender-cache SDL_AUDIODRIVER=dummy
RIG_CONFIG = perspective-preview-config-v6.json
RIG_ENV = AGENTS_TRAY_RIG_CONFIG=$(RIG_CONFIG)
BLEND = vault-boy-2d-rig-perspective-v6.blend

.PHONY: prepare build render previews diagnostics verify clean

prepare:
	python3 prepare_shoulder_fix.py
	test -f sources/master-v6/good-clean-body-master-v6.png
	test -f sources/master-v6/good-raise-arm-master-v6.png

build: prepare
	$(RIG_ENV) $(BLENDER_ENV) $(BLENDER) --background --factory-startup --python build_master_rig.py -- --build

render: build
	$(RIG_ENV) $(BLENDER_ENV) $(BLENDER) --background $(BLEND) --python build_master_rig.py -- --render-good
	$(RIG_ENV) python3 make_master_previews.py

previews:
	$(RIG_ENV) python3 make_master_previews.py

diagnostics:
	$(RIG_ENV) $(BLENDER_ENV) $(BLENDER) --background $(BLEND) --python render_master_diagnostics.py

verify:
	$(RIG_ENV) python3 verify_master_good.py
	$(RIG_ENV) python3 verify_clean_plate.py
	$(RIG_ENV) $(BLENDER_ENV) $(BLENDER) --background $(BLEND) --python verify_master_blend.py

clean:
	rm -rf render/master-good-v6 previews/master-good-v6 $(BLEND)
