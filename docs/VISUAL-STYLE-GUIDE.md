# Visual Style Guide — Realistic Office, Not Cartoon

## Target

A grounded contemporary headquarters visualization with the visual language of a realistic architectural walkthrough / business simulation. The environment should feel designed and furnished at human scale. Avoid exaggerated proportions, toy-like people, saturated color coding, floating interaction orbs and permanent nameplates.

## Material direction

| Surface | Direction | Godot starting material |
|---|---|---|
| Lobby floor | Large-format porcelain / polished stone, low-contrast variation | Roughness 0.22–0.38 |
| Work areas | Low-pile commercial carpet / carpet tile | Roughness 0.82–0.95 |
| Desk tops | Walnut / oak veneer, restrained grain | Roughness 0.35–0.55 |
| Reception counter | Warm timber base + pale stone top | Roughness 0.24–0.5 |
| Glass | Slight cool tint, clear visibility, dark aluminum mullions | Roughness 0.1–0.2, metallic frame 0.45–0.7 |
| Metal legs / frames | Dark anodized metal | Roughness 0.25–0.45, metallic 0.55–0.8 |
| Upholstery | Muted charcoal, olive, slate or warm grey fabric | Roughness 0.88–0.98 |
| Painted walls | Warm off-white / soft grey | Roughness 0.82–0.95 |

Use subtle value differences. Avoid glossy gold everywhere, saturated neon strips, and overly bright emissive monitors.

## Lighting

- Use a soft daylight key from the glazed facade.
- Keep warm ceiling illumination neutral and restrained.
- Linear luminaires should illuminate desks and circulation, not act as neon decoration.
- Use shadows for grounding, but avoid excessive shadow contrast.
- Use filmic tonemapping and modest contrast/saturation.
- The GL Compatibility renderer is a portability tradeoff; verify actual lighting quality on target GPUs.

## Human characters

The current CharacterFactory model is an interim procedural mesh. It uses improved human proportions, neutral business-casual clothes, a small ID badge and hidden nameplates. It is not final.

Production asset requirements:

- Licensed/owned rigged GLB model.
- Realistic body proportions and natural face/hair silhouette.
- Separate skeleton and AnimationTree.
- Walk, idle, sit, type, talk, listen, gesture and stand-up clips.
- Consistent scale around 1.65–1.85 m.
- Department-appropriate but restrained clothing.
- No permanent floating nameplates; show names when focused or through workplace context.

## Office UI

- HUD must be thin and quiet: connection, location, team/project hint, reticle and contextual interaction prompt.
- The full Company Command Center opens only at the Owner computer.
- Agenda opens from the Secretary desk.
- Paper reader opens from the physical tray.
- Do not show approval modal popups during normal walking.
- UI panels use neutral surfaces, restrained sage/teal accent and low-radius corners. No large animated badges or candy-colored cards.

## Asset policy

Use licensed or original assets only. Record asset name, source URL, license, attribution requirement and local path in `docs/ASSET-REGISTER.md` before adding third-party models, textures, sound or fonts. The v0.5 project currently uses generated native geometry, so no external asset pack is required.
