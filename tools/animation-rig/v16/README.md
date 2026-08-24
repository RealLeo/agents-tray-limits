# Version 16 2D skeletal prototype

This directory contains the staged `good`-state prototype for the Fallout 2
theme. It is intentionally isolated from the extension runtime until visual
approval.

The registered character master and the accepted v4 clean plate remain
unchanged. A deterministic v6 preparation step removes only the erroneous
inner shoulder seam and the clean-body shard, producing new staged layers.
Blender deforms the isolated arm as one dense textured mesh. The v6 preview
adds real mesh depth and a calibrated perspective camera: the hand starts
partly hidden behind the body at roughly 70% apparent size, emerges at the left
silhouette, and reaches the registered front-facing bind pose. The upper arm
reaches a stable front plane before the forearm and hand, preventing the late
shoulder-plane flicker present in v5. The 36 ms playback interval keeps all 32
frames while reducing the scene to about 1.12 seconds.
Frame-to-frame redraws, hand swaps, crossfades, optical flow, lighting, and 3D
turntables are not part of this pipeline.

```bash
make prepare
make build
make render
make verify
```

`render` produces 32 source frames at 2048 px and deterministic 512 px
sprites. Review artifacts are written to `previews/master-good-v6/` at 512 px,
98 px, slow speed, as a contact sheet, and as a depth/scale trajectory chart.
`diagnostics` produces the rig and weight-map images. These staged files are
not included in the extension ZIP, and the extension stays on version 15 until
the prototype is approved.
