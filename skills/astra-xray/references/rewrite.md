# Preparing the edit

A request to patch the audited scope authorizes the normal implementation steps.
Show the concrete diff and continue when that authorization already exists.
Ask only when a missing decision changes scope or risks losing later work.

## Ownership comes first

Use the scan's provenance and inspect the source evidence. Preserve official
OpenAI skills, plugin caches and upstream installations. This includes popular
skills such as Playwright, Superpowers and Puppeteer, but popularity is not the
test: every maintained upstream installation is excluded from local rewrites.
A copy under a user directory is still upstream. Do not use a generic GitHub
reference in the body or the existence of openai.yaml alone as proof of ownership.

No ownership evidence means unverified. Determine whether the user created the
skill from a direct statement or local history. Record exact verified local
paths in an ownership JSON. If uncertainty remains, list the item as unresolved
and continue other verified work. Editing this project's source repository for
a requested release is separate from rewriting installed third-party skills.

## Cover the requested cleanup

Review all personal descriptions. Budget headroom does not make verbose
descriptions useful. Preserve task triggers and meaningful exclusions. Remove
repeated instructions, exhaustive examples and generic persuasion from the
description when the body already carries them. Judge each case; there is no
mandatory character target.

Account for every candidate as changed, kept with a reason, excluded upstream
or unresolved. Do not substitute model changes, duplicate renames or directory
moves for the description work the user requested.

## Description plan

Write a JSON file outside the repository:

```json
{
  "local_skills": ["/absolute/path/to/personal-skill/SKILL.md"],
  "edits": [{
    "path": "/absolute/path/to/personal-skill/SKILL.md",
    "sha256": "<sha256 from description_audit.rows>",
    "description": "<reviewed replacement with task trigger and useful exclusions>",
    "reason": "<what repetition was removed and what boundary was preserved>"
  }]
}
```

Use native absolute Windows paths encoded as valid JSON on Windows.
Use `tune.py --plan <plan>` to validate and preview all changes.
With existing patch authorization use `tune.py --plan <plan> --apply`.
The helper rejects upstream files and unverified ownership even if an edit
attempts to list them as local. It validates the full batch before writing,
backs up exact original bytes, replaces only the description field, verifies
the written bytes and seals the backup.

Review semantic equivalence before applying. In particular, preserve exclusions
such as read-only use, locked narration, supported file types and task routing.
The helper protects bytes and ownership; it cannot judge meaning.

Keep the timestamped pre-edit scan. Compare with
`scan.py --baseline <pre-edit-scan.json> --ownership <plan>`.
Never use latest.json as a durable baseline because every normal scan updates it.
If the baseline predates 0.3.0 or has only file discovery, run a new scan before
editing. Without captured membership report per-file savings separately.

## Other instruction findings

KEEP useful domain facts and safety boundaries.
TIGHTEN unnecessary wording while preserving the rule's purpose.
MOVE background to references when the condition for reading it is clear.
DROP obsolete workaround instructions only after checking their purpose.
RESOLVE conflicts using existing user intent; ask only if it does not settle them.

Required reading should point to a document when its subject is relevant.
Testing should match the risk and affected behavior, with existing release gates
preserved. Replace needless first-pass stops with the actual completion criteria.
Inspect model-specific instructions in context; a model name in a reference link
or migration example is not itself an obsolete workaround.

An old skills folder still works. Keep it unless the user requested migration.
Do not traverse or move large assets and node_modules for description cleanup.
A duplicate name can represent a different API or tool workflow. Preserve both
until the user selects a particular redundant installation. Measure that exact
path with --without-path, not the name shared by both copies.

Do not rewrite installed upstream content to make astra-xray's findings disappear.
