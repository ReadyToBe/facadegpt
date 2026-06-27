# Design QA — First-turn project prompt examples

- Source visual truth: `C:\Users\99791\AppData\Local\Temp\codex-clipboard-eee35043-295f-4344-952a-9086b37df150.png`
- Implementation screenshot: `D:\FileK\facadegpt3\design-qa-prompt-suggestions.png`
- Viewport: 1865 × 935 desktop
- State: newly created project containing only the persisted FacadeGPT introduction

## Full-view comparison evidence

The implementation preserves the source workspace structure, column proportions, header, project navigation, conversation area, composer position, scheme rail, and empty scheme preview. The annotated space below the composer is now occupied by three compact project-prompt buttons without changing surrounding navigation or page hierarchy.

## Focused region comparison evidence

The composer region was reviewed at original resolution because it contains the requested interaction. The new prompt group aligns to the same 760px composer width, uses the existing neutral/mint tokens, and keeps each option readable as a single-line button with a clear action icon. No new raster assets are required; all visible icons come from the project's existing icon library.

## Required fidelity surfaces

- Fonts and typography: existing Inter/Microsoft YaHei stack, weights, line heights, and small-label hierarchy are preserved.
- Spacing and layout rhythm: 10px separation from the composer, 6px option gaps, and shared composer width match the existing workspace rhythm.
- Colors and visual tokens: existing ink, muted, line, soft surface, and mint-dark tokens are reused; contrast remains clear.
- Image quality and asset fidelity: no image assets are introduced or replaced.
- Copy and content: three realistic facade-design examples cover climate/solar control, daylight/cost, and energy/carbon goals.

## Findings

No actionable P0, P1, or P2 differences remain. The source annotation specified the location and multiplicity rather than an exact component treatment; the outlined stacked buttons are consistent with the existing FacadeGPT design system.

## Patches made

- Added a dedicated prompt-example configuration file.
- Added first-turn-only rendering below the composer.
- Added click-to-send behavior and automatic disappearance once a user message exists.
- Added responsive button sizing and existing-token hover/focus treatment.

## Follow-up polish

- P3: prompt examples could later be personalized from project metadata once location or building type is known.

final result: passed
