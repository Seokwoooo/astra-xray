# Reading the report

Write in the user's language. Lead with the result and the next useful action.
Keep raw data in the timestamped JSON report.

## What to report

- Target model and catalog source. The captured model and configured model are
  separate metadata. Neither needs to be Astra for this audit.
- Catalog budget usage, description cuts and omitted skills. Always identify
  estimates. Compare the same membership before and after edits.
- Personal description review: how many need work, how many need ownership
  verification and how many are excluded because upstream maintains them.
- AGENTS.md findings, important protected boundaries and the report path.

Give at most three priority actions. Group repeated wording observations with a
count. The full JSON contains every finding; do not paste dozens of keyword hits
as if each were a confirmed defect. A4 is a context review signal. An unmarked
line can still be an important boundary.

## Sources and comparisons

`skills.listing.source`:
- `session`: catalog captured in a matching task. Disk descriptions are used to
  simulate the target model. Check freshness and cwd annotations for explicit logs.
- `baseline`: known catalog membership updated with current file contents and
  disabled entries. This avoids loading unrelated plugin cache files into a
  before/after comparison. It remains an estimate until a fresh task confirms it.
- `files`: discovery only. Low confidence. App skills may be absent and plugin
  caches may be extra. Do not claim runtime truncation from this estimate.

`entries` preserves full descriptions for later baseline comparisons.
`comparison` gives before/after budget units and description characters.
`unobserved_files` lists files outside baseline membership, not new runtime skills.
`unknown_omitted_from_capture` means some source skills could not be recovered.
Call out an incomplete capture for baseline results too.

`catalog_comparison` uses normalized Windows path identity without changing the
paths used for rendering. Plugin cache versions still represent distinct files.
The renderer line reproduction count is not inventory proof.

`description_audit.rows` contains each path, description, character/byte counts,
estimated tokens, hash, enabled state, provenance and review disposition.
The 200-character / 80-estimated-token thresholds are astra-xray heuristics.
They are not OpenAI limits, enforced targets or proof that the text should shrink.

`provenance.kind` is managed, upstream, local or unverified.
Only verified local ownership is editable. Installation location is not ownership.
No installer record does not prove that a skill is personal.

## Rule groups

S1 reports budget cuts. S2/S11 flag broad or pushy triggers. S3 flags overlap for
review, not automatic merging. S4/S5 inspect body size and recipes. S6 reports a
legacy path, not a migration request. S7 reports a shared name, not equivalent
capabilities. S8 flags suspicious scripts without executing them. S9/S10 flag
frontmatter issues. S12 surfaces long personal or unverified descriptions even
below the budget.

A1/A10/A11 concern loading, limits and trust. A2/A3/A5 concern forced workflow
steps. A4/A7/A8 require contextual judgment. A12 marks shared instructions.
C findings are configuration observations. Cleanup does not authorize changing
the default model, CLI installation or security settings.

## Completion record

For each personal candidate use changed, kept with a reason or unresolved.
Report upstream exclusions separately. Provide the backup path and the relevant
restore command after applying. If something remains unresolved, describe it
instead of claiming the entire cleanup is complete.
