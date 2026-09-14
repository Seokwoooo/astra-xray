# Reading the scan and reporting it

## Report shape

Write in the user's language. Lead with what Astra receives, then what to do.

1. **Headline:** skills in the Astra target simulation, how many descriptions are cut or dropped, and whether Codex would warn about it. Name the model that captured the host catalog separately. Then give AGENTS.md bytes loaded against the limit and how many findings are protected.
2. **Top actions (at most three):** each with its measured effect. Measure skill changes with `scan.py --without ...` before recommending them.
3. **Findings:** grouped by skills, AGENTS.md and config. Give `file:line`, a short excerpt and the source. List protected findings separately under "keep".

Do not paste whole files. Say plainly when numbers are estimates.

## Where the numbers come from

`skills.listing.source` is either:

- `session`: a trusted `world_state.state.host_skills` catalog from a fresh session for the scanned directory. The source session can use any model; `environment.model` is the independent target, normally Astra. `calibration.reproduced_lines` compares the target simulation with captured lines, so it is a renderer check rather than proof that file discovery found every skill. If `catalog_complete` is false, state that the target result is a lower bound because the source session omitted unknown skills.
- `files`: no matching catalog postdates the current skill/config files, so membership is a low-confidence estimate. App/plugin skills can be missing or extra. Suggest starting a fresh Codex task in that directory and rescanning; its model does not have to be Astra.

When a session catalog exists, `skills.catalog_comparison` compares its membership with file discovery. Report `session_only_count` and `files_only_count` when either is nonzero. A perfect renderer calibration does not cancel a membership mismatch.

Per-skill `status` describes the target simulation: `full`, `shortened`, `name_only` (description removed), or `omitted`. `captured_status` separately records `full`, `shortened`, `name_only`, `changed_since_session`, or `file_missing` for the source catalog.

`warning` is the text Codex shows, or null. Codex stays silent while `average_cut_chars` is 100 or less, even when many descriptions are cut. That gap is often worth pointing out.

AGENTS.md `files[].status`: `loaded`, `truncated`, `dropped_budget_exhausted`, `empty`, `ignored_untrusted_project`. `shadows` lists files in the same folder that Codex skipped because an earlier name won.

## Rule IDs

| ID | Meaning | Usual proposal |
|---|---|---|
| S1 | Budget cut or dropped descriptions | Turn off unused skills; put trigger words first in descriptions |
| S2 | Broad trigger ("use when working with…") | Name the specific task instead |
| S3 | Two skills with overlapping descriptions | Merge them or state the boundary |
| S4 | Large SKILL.md | Split mode-specific detail into references, only if there are several modes |
| S5 | Long numbered recipe | State the outcome and criteria; keep steps only where order matters |
| S6 | Skill in deprecated `~/.codex/skills` | Move to `~/.agents/skills` |
| S7 | Same name in several places | Rename or remove the stale copy |
| S8 | Script pipes a download into a shell | Flag to the user; never run it |
| S9, S10 | Description too long, or SKILL.md does not load | Fix the frontmatter |
| S11 | Wording written to make agents trigger more often | Narrow it |
| A1 | AGENTS.md cut by the byte limit | Move background material to docs and point to it |
| A2 | Required reading before every edit | Replace with pointers tied to the situation |
| A3 | Unconditional testing or re-checking | Remove, or allow a specific safe test workflow |
| A4 | Strong "never" or "ask first" wording | Keep if protected; otherwise scope it |
| A5 | Stops after a first pass | Replace with a definition of done |
| A7 | Rule chosen by model self-identification | Move the rule to a place only that agent reads |
| A8 | Names an older model | Check whether the rule was a workaround for that model |
| A10 | An override file hides another file | Remove the empty override or merge the files |
| A11 | Untrusted project; AGENTS.md ignored | Tell the user; trust is their decision |
| A12 | File shared with other agents | Do not relax it for Astra alone |
| C1–C5 | Codex version, effort, model, approval policy, open sandbox | Report; the user changes these |

Findings under a skill's own body are `info`: that skill's workflow may genuinely need the step. This includes strong boundaries and model-specific rules; judge each one in context instead of silently omitting it.
