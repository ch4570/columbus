# Columbus artwork

The character and README banner were generated for Columbus on 2026-09-07 with the built-in `image_gen.imagegen` tool. No CLI fallback, API-key workflow, external stock image, or existing mascot was used.

| Asset | Dimensions | File size | SHA-256 |
| --- | --- | ---: | --- |
| [Character](columbus-character.png) | 1254 × 1254 | 1,386,101 bytes | `7d8a872a9547909cacb5c81c87dac1d8d8e41bb5e8f7678540fed34dfbbf97da` |
| [README hero](columbus-hero.png) | 2172 × 724 | 2,416,857 bytes | `5e938eca080b3232044acec949a2e9394588dcbc44edb982108b74b0777ac511` |

The character wears a rounded navy navigator's cap and coral tunic, with a brass compass, rolled map, and teal satchel. The hero uses the same character, an ivory map, navy and teal ocean shapes, and routes between code nodes. Its text is **COLUMBUS** and **Navigate your codebase.**

These are illustrations, not benchmark visualizations. Measured charts are generated separately from recorded data.

## Selection and review

Each generated candidate was inspected with `view_image` before the next edit. The selected PNGs were copied into this directory without pixel edits. Original generated files were retained by the tool.

The first character had a pointed hat, so the second pass established a rounded cap and simpler editorial shading. An attempted transparent background produced a baked checkerboard; the subsequent extraction introduced a visible halo. Both background variants were discarded. The delivered character intentionally uses an opaque parchment background, with the complete cap and boots inside comfortable margins. It is **not a transparent cutout**.

The selected character and first hero passed direct visual review: correct title and subtitle, consistent face and outfit, readable compass and scroll, no cropped limbs, and uncluttered composition. Local iteration evidence is recorded in `.omx/state/columbus-art/ralph-progress.json`; scores there are subjective review scores, not a comparison with an external reference or a benchmark.

## Prompt set

The following prompts record the accepted character's development and the banner generation. Intermediate filenames identify the built-in tool's retained source images; only the two selected assets above are distributed.

### Initial character

```text
Use case: logo-brand
Asset type: original software project mascot illustration, square 1024 × 1024 PNG, with genuine transparent background.
Primary request: Create the distinctive Columbus character for COLUMBUS, a tool for navigating software repositories. An approachable and clever adult Renaissance navigator, stylized and friendly, holding a small brass compass in one hand and a rolled parchment map in the other. A substantial rounded dark navy 15th-century cap, dark slightly wavy hair peeking out, expressive arched eyebrows, small warm smile, coral-burgundy tunic, ivory collar, dark navy boots, and a little teal satchel. Soft caricature proportions with a large expressive head and compact body, premium original editorial mascot quality. Columbus concept should read immediately as historical navigator rather than pirate. Show full body with an open curious stance and lively but restrained personality.
Style/medium: polished editorial illustration with bold clean silhouette, subtle paper grain and soft layered shading, restrained flat shapes, a few tasteful ink details; not photorealistic, not 3D, not an imitation of any existing mascot.
Composition/framing: centered single full-body character, taking about 84 percent of height, comfortable clear margins on all sides; clear compass and map; strong small-size legibility.
Color palette: midnight navy #152A3B, deep teal #23616A, parchment ivory #F4EAD8, coral #D46A50, muted brass #CBA866.
Text: none.
Constraints: actual transparent background, preserve alpha; one character only; coherent hands with appropriate fingers and no extra limbs; full cap, boots, compass, and scroll all visible. No flags, weapons, conquest imagery, ships, logos, text, watermarks, decorative frame, or background scene.
```

### Character identity refinement

Reference: the initial generated character, `exec-45c2004f-29d6-4126-a601-a4d7e0cda3cd.png`.

```text
Use case: style-transfer
Asset type: final original COLUMBUS software explorer mascot, square PNG with genuine transparent background.
Input image 1: edit target; preserve the same friendly adult navigator's identity, warm expression, compass, rolled parchment map, outfit colors, satchel, and full-body pose.
Primary edit: change the tricorn-shaped hat to a LOW, SOFT, ROUNDED late-15th-century Renaissance scholar/navigator cap, a navy cloth bonnet with no pointed ends, no triangular pirate silhouette, no feathers and no gold rim. Give the character comfortable transparent margins, about 10 percent above cap and below boots. Simplify the illustration into premium editorial flat-shape art with bold confident contours, large clean color regions, subtle paper grain and very restrained dimensional shading. Preserve the friendly memorable face, readable compass and scroll, and coherent hands.
Color palette: midnight navy, deep teal, parchment ivory, muted brass and coral.
Constraints: keep single complete character and genuine alpha background. No text, flags, weapons, extra limbs, watermark or new objects. Keep the whole character visible with clear padding around all edges.
```

### Selected character background and framing

Reference: the refined character, `exec-7def34d7-de3c-442b-97b5-e6d8150df8ba.png`.
Selected output: `exec-75e9110c-166b-4af3-b727-36dde8adda5c.png`, copied to `columbus-character.png`.

```text
Use case: precise-object-edit
Asset type: square COLUMBUS software mascot portrait, opaque PNG.
Input image 1 is the edit target. Keep the approved single full-body illustrated Renaissance navigator exactly consistent: rounded soft navy cap (never pirate tricorn), friendly face, dark curls, brass compass, parchment scroll, coral-burgundy tunic, ivory collar, teal satchel and navy boots.
Only replace the visible checkerboard background with a completely clean, solid, opaque parchment ivory background (#F4EAD8). There must be no gray and white squares, no black, no glow, no vignette, no cast shadow, no scene. The backdrop should look like a beautiful unprinted warm ivory page.
Add comfortable page margins so the full character occupies only about 80 percent of image height and is centered. Preserve the character's pose, details, facial identity and premium flat editorial illustration style. No text, border, logo or watermark. Keep both feet and cap fully visible. Square composition.
```

### Selected README hero

Reference: the delivered `columbus-character.png`.
Selected output: `exec-5b77ab24-d36a-43f5-8115-a6f2cad114b3.png`, copied to `columbus-hero.png`.

```text
Use case: ads-marketing
Asset type: premium GitHub README hero banner for the COLUMBUS software repository explorer. Wide landscape 3:1 aspect ratio, ideally 2160 × 720.
Input image 1 is the approved character reference. Preserve this exact illustrated navigator's identity and outfit: rounded soft navy Renaissance cap (no tricorn), dark curls, friendly warm face, coral tunic with dark navy outer coat, ivory collar, teal satchel, brass compass and rolled parchment map. Keep the same polished editorial flat-shape illustration style and fine paper texture.
Scene/backdrop: a restrained parchment-ivory nautical code map, with deep navy and teal shapes along the lower edge suggesting a navigable ocean. The map contains a few thin curved routes connecting small simple code-node circles and tiny folder/map landmarks, at low visual contrast. This is a navigation tool for exploring code, not a historical conquest scene.
Composition/framing: generous uncluttered landscape banner. Large exact title in the left half, subtitle directly below. The same distinctive navigator stands fully visible in the right third, with safe margins around cap and boots, holding compass toward the title and map in the other hand. Character should occupy about 82 percent of banner height. Thin coral map-route accents connect the typography area to the character without touching the text. Title must be readable at a 720-pixel-wide display; supporting motifs never compete with the title or face.
Text (verbatim): "COLUMBUS"
Subtitle (verbatim): "Navigate your codebase."
Typography: COLUMBUS in large custom-feeling elegant sturdy navy serif capitals, every letter correct C-O-L-U-M-B-U-S; subtitle in a much smaller clean navy sans serif; crisp and perfectly legible, no extra words or symbols posing as text.
Color palette: parchment ivory #F4EAD8, midnight navy #152A3B, deep teal #23616A, coral #D46A50 and muted brass #CBA866.
Constraints: premium cohesive original branding, no fabricated chart or benchmark numbers, no screenshot, no text other than exact two lines, no flags, weapons, conquest imagery, pirate hat, extra character, watermark, decorative outer frame or cropped limbs. No globe with political borders. Keep adequate negative space and consistent mascot details.
```
