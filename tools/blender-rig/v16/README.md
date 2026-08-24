# Vault Boy Blender rig prototype

This directory contains the editable, build-time sources for the version 16
animation prototype. Nothing below this directory is included in the runtime
extension ZIP.

The model is built procedurally in Blender 5.2 LTS from one shared mesh and one
armature. ImageGen outputs in `references/` are modeling references only; they
are never used as animation frames.

## Build and preview

```bash
make -C tools/blender-rig/v16 preview
```

The command creates `vault-boy-v16.blend`, renders the `good` action at
2048x2048 with transparent film, downsamples the sprites to 512x512, and writes
review artifacts to `previews/`.

Runtime files under `themes/` are intentionally not touched by this prototype.

