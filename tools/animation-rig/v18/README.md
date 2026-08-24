# Version 18 staged animations

This directory contains the source art and Blender rigs for the accepted
`worried` and `critical` Fallout 2 theme animations plus the accepted static
`dead` source master.

The accepted v16 `good` master is the identity and style reference. ImageGen is
used only for the registered `worried` and `critical` state masters and clean
body plates; Blender renders all animation frames deterministically from those
fixed pixels.

The seated X-eyed `dead` state uses one static runtime image and has no
animation rig or timer. Its accepted RGBA master is byte-identical to the
runtime frame.

The repository keeps the four `.blend` rigs, scripts, configuration, registered
source art, and compact motion/mesh JSON fixtures. Generated Blender frame
dumps, duplicate sprite exports, `.blend1` backups, and review previews are
ignored. `verify_previews.py` validates the shipped theme frames directly, so a
clean checkout does not depend on local render output.
