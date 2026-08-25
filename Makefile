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
