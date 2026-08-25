.PHONY: check check-shared check-gnome check-macos pack pack-gnome pack-macos pack-all install uninstall clean

check: check-shared check-gnome

check-shared:
	python3 tools/validate_shared.py
	python3 tools/validate_macos_source.py

check-gnome:
	$(MAKE) -C apps/gnome check

check-macos:
	$(MAKE) -C apps/macos check

pack: pack-gnome

pack-gnome:
	$(MAKE) -C apps/gnome pack

pack-macos:
	$(MAKE) -C apps/macos pack

pack-all: pack-gnome pack-macos

install:
	./install.sh

uninstall:
	./uninstall.sh

clean:
	$(MAKE) -C apps/gnome clean
	$(MAKE) -C apps/macos clean
	$(MAKE) -C tools/animation-rig/v16 clean
	rm -rf "$(CURDIR)/build" "$(CURDIR)/dist"
	rm -rf "$(CURDIR)/tools/animation-rig/v18/previews"
	rm -rf \
		"$(CURDIR)/tools/animation-rig/v18/render/critical" \
		"$(CURDIR)/tools/animation-rig/v18/render/worried" \
		"$(CURDIR)/tools/animation-rig/v18/render/critical-back/raw" \
		"$(CURDIR)/tools/animation-rig/v18/render/critical-back/sprites" \
		"$(CURDIR)/tools/animation-rig/v18/render/critical-front/raw" \
		"$(CURDIR)/tools/animation-rig/v18/render/critical-front/sprites" \
		"$(CURDIR)/tools/animation-rig/v18/render/worried-back/raw" \
		"$(CURDIR)/tools/animation-rig/v18/render/worried-back/sprites" \
		"$(CURDIR)/tools/animation-rig/v18/render/worried-front/raw" \
		"$(CURDIR)/tools/animation-rig/v18/render/worried-front/sprites"
	rm -f \
		"$(CURDIR)/tools/animation-rig/v18/rigs/critical-back.blend1" \
		"$(CURDIR)/tools/animation-rig/v18/rigs/critical-front.blend1" \
		"$(CURDIR)/tools/animation-rig/v18/rigs/worried-back.blend1" \
		"$(CURDIR)/tools/animation-rig/v18/rigs/worried-front.blend1"
	find "$(CURDIR)/apps" "$(CURDIR)/tools" -type d -name __pycache__ -prune -exec rm -rf {} +
