#!/usr/bin/env python3
"""Load extension stylesheets with GNOME Shell's St.Theme parser."""

from __future__ import annotations

import json
import os
import re
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SHARED = Path(__file__).resolve().parents[3] / "shared"
STYLESHEETS = (
    ROOT / "stylesheet.css",
    SHARED / "themes" / "fallout-2" / "theme.css",
    SHARED / "themes" / "fallout-3" / "theme.css",
)


def locate_typelib(name: str) -> Path:
    candidates: list[Path] = []
    for library_root in (Path("/usr/lib"), Path("/usr/lib64")):
        if library_root.is_dir():
            candidates.extend(library_root.rglob(name))
    if not candidates:
        raise RuntimeError(f"required GNOME Shell typelib was not found: {name}")
    return sorted(candidates)[-1]


def main() -> int:
    st_typelib = locate_typelib("St-*.typelib")
    match = re.fullmatch(r"St-(.+)\.typelib", st_typelib.name)
    if not match:
        raise RuntimeError(f"unexpected St typelib name: {st_typelib.name}")
    abi = match.group(1)
    meta_typelib = locate_typelib(f"Meta-{abi}.typelib")

    missing = [str(path) for path in STYLESHEETS if not path.is_file()]
    if missing:
        raise RuntimeError("missing stylesheets: " + ", ".join(missing))

    environment = os.environ.copy()
    typelib_dirs = [str(st_typelib.parent), str(meta_typelib.parent)]
    if environment.get("GI_TYPELIB_PATH"):
        typelib_dirs.append(environment["GI_TYPELIB_PATH"])
    environment["GI_TYPELIB_PATH"] = os.pathsep.join(typelib_dirs)
    library_dirs = [str(st_typelib.parent)]
    if environment.get("LD_LIBRARY_PATH"):
        library_dirs.append(environment["LD_LIBRARY_PATH"])
    environment["LD_LIBRARY_PATH"] = os.pathsep.join(library_dirs)

    paths = json.dumps([str(path) for path in STYLESHEETS])
    javascript = (
        "const {Gio, St} = imports.gi; "
        f"for (const path of {paths}) {{ "
        "const theme = new St.Theme(); "
        "theme.load_stylesheet(Gio.File.new_for_path(path)); "
        "print(`St.Theme loaded ${path}`); "
        "}"
    )
    subprocess.run(
        ["gjs", "-c", javascript],
        cwd=ROOT,
        env=environment,
        check=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
