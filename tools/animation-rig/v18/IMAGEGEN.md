# ImageGen provenance

The built-in ImageGen tool was used for static, preview-only master art. It was
not used to generate animation frames.

## Worried master

- Identity/style reference: the accepted v16 `good` master.
- Pose reference: the previous runtime `worried/16.png`, used only for intent.
- Prompt intent: preserve the exact character, proportions, palette, ink line,
  crop, and baseline; show an anxious wrist check with two connected arms and
  small sweat drops; transparent square canvas; no text, logo, props, or new
  costume details.

## Critical master

- Identity/style reference: the accepted v16 `good` master.
- Pose reference: the previous runtime `critical/16.png`, used only for intent.
- Prompt intent: preserve the exact character and rendering; show a controlled
  sideways lean with one hand supporting the torso and the other arm hanging;
  no injury, blood, text, logo, props, or costume changes.

## Clean body plates

Each accepted master was edited once to remove only its arms and reconstruct
the covered jacket/torso. The result is composited only inside the local repair
region; all master pixels outside that region remain unchanged.

## Dead master

- Identity/style reference: the accepted v16 `good` master.
- Emotion reference: the previous seated X-eyed runtime art.
- Prompt intent: preserve the exact character, palette, costume, line weight,
  and harmless X-eye/tongue expression while drawing one anatomically connected
  seated body with bent legs and relaxed arms.
- The selected ImageGen result is stored as
  `source/raw/dead-static-imagegen-v1.png`. ImageGen rendered its checkerboard
  as RGB pixels, so the connected exterior background was removed
  deterministically with ImageMagick 6.9.12 using a 16% flood-fill from `(0,0)`;
  the result was resized to 512×512 with Lanczos.
- `source/master/dead-static-v1.png` is the accepted RGBA result and is
  byte-identical to the single runtime `dead/16.png` frame.
