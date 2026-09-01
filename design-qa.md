# V3 Android visual QA

## Scope

- Target: Agent-first recommendation stack and recovery experience.
- Device: Pixel_9 API 35, 1080×2424.
- Reference sources:
  - `docs/task-packages/previews/generated/01-recommendation-stack-editorial-v3.png` (852×1846)
  - `docs/task-packages/previews/generated/06-recovery-experience-editorial-v1.png` (853×1844)
- Runtime screenshots:
  - `output/v3-recommendation-final.png`
  - `output/v3-recovery-final.png`
- Combined source/implementation comparisons:
  - `output/design-qa-recommendation-final.png`
  - `output/design-qa-recovery-final.png`

## Comparison method

The implementation screenshots are full runtime captures. For same-height comparison, the Android status and gesture-system areas are cropped (`y=142`, height `2219`) and resized only for density normalization; no application content is cropped. Reference is on the left and runtime implementation is on the right in each combined artifact.

## Required surfaces

| Surface | Runtime result |
| --- | --- |
| Editorial palette and hierarchy | Cream field, ink typography, emerald/lime/coral state cues, black three-tab rail match the selected visual language. |
| Main recommendation | Real product asset, `主推荐`, `01 / 03`, price, `DEMO_FIXTURE`, evidence reference, compare/save/waiting actions and `下滑查看次推荐` are visible. |
| Ranked navigation | Runtime renders only the top three; the main/secondary/third labels and directional hints follow the confirmed vertical stack interaction. |
| Recovery | Explicit recovered state, task constraint, safe recovery point, receipt, no-duplicate terminal state and continue action are visible. |
| Truth boundary | Reference-only metrics and unsupported commercial claims were not copied. The implementation instead renders API-derived title, price, evidence, risk and `DEMO_FIXTURE`. |

## Iterations

1. Initial comparison exposed an undersized product image and a `01 / 05` counter.
2. The result pager was limited to the confirmed top three; the generated earbud asset was enlarged and placed on the lime editorial stage.
3. The final pass added the API-derived quote/actions and corrected the vertical-stack hint to `下滑查看次推荐`.

## Result

**passed** — no P0/P1/P2 visible fidelity defect remains for the two confirmed runtime states. The deliberate differences are the removal of fabricated match/specification/source-count facts and the use of real fixture-backed data.
