# Third-party attribution

Several skills in this directory are vendored from **[mattpocock/skills](https://github.com/mattpocock/skills)**
and adapted for Killhouse. They are used under the MIT License — the full license text is in
[`THIRD-PARTY-LICENSE-mattpocock.txt`](./THIRD-PARTY-LICENSE-mattpocock.txt).

Vendored (and customized) here:

| Killhouse path | Upstream source |
| --- | --- |
| `triage/` (SKILL.md, AGENT-BRIEF.md, OUT-OF-SCOPE.md) | `skills/engineering/triage/` |
| `grill-with-docs/SKILL.md` | `skills/engineering/grill-with-docs/SKILL.md` |
| `grilling/SKILL.md` | `skills/productivity/grilling/SKILL.md` |
| `domain-modeling/` (SKILL.md, ADR-FORMAT.md, CONTEXT-FORMAT.md) | `skills/engineering/domain-modeling/` |
| `to-prd/SKILL.md` | `skills/engineering/to-prd/SKILL.md` |

These copies are intentionally forked: frontmatter was switched to model-invoked so `ask-kh` can drive
them, and a **Killhouse handoff** section was added to wire each into the pipeline. They will drift from
upstream as we customize them — that is expected. `ask-kh.md` is Killhouse-original and not derived from
`mattpocock/skills`.
