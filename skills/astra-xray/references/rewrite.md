# Proposing changes

Classify each finding before writing a diff:

- **KEEP**: protected (see [keep.md](keep.md)), or still true and useful. No change.
- **TIGHTEN**: a protected rule whose wording also blocks safe work. Scope it so the protected action stays blocked.
- **MOVE**: true, but not needed on every task. Move it to docs or references and leave a pointer that says when to read it.
- **DROP**: exists only to push an older model: forced reading, forced testing, stopping after a first pass, model workarounds.
- **RESOLVE**: two rules contradict. Astra can stall on conflicting instructions, so ask the user which one wins.

Show one unified diff per file. Above each hunk, give the finding ID, the class and the source.

## Skill descriptions (S1, S2, S11)

OpenAI's example:

- Bad: `Create and validate Postgres schema migrations. Use when working with databases, queries, models, or persistence.`
- Good: `Create and validate Postgres schema migrations. Use when adding or changing a migration, or reviewing its rollout.`

Put trigger words first. When Codex shortens descriptions it keeps the beginning.

For S1, first measure `scan.py --without` with the skills the user does not use. Turning a skill off keeps it installed:

```toml
[[skills.config]]
path = "/absolute/path/to/SKILL.md"
enabled = false
```

## Required reading (A2)

OpenAI's example:

- Bad: `Before every edit, read architecture.md, database.md, and deployment.md.`
- Good: `Use architecture.md for service boundaries, database.md for schema changes, and deployment.md when preparing a deployment.`

## Forced testing (A3)

Wording from OpenAI's GPT-6 Astra model guide:

> Do not write tests for reversible, low-impact changes that mirror the implementation.

> Run tests appropriate to the change and complete required checks. Once those pass, broaden or repeat testing only when new changes, failures, or unresolved concerns justify it; otherwise, continue toward completing the task.

Where a test workflow is known to be safe, say so. OpenAI's example:

> The local tests use disposable fixtures and have no production access. Run them, fix failures caused by the requested change, and rerun affected tests without asking for approval at each step.

Write that only if it is true for this repository.

## Stopping early (A5)

A required review stop after the first implementation pulls Astra toward stopping early. Replace it with what done looks like, for example:

`Done means the change runs, the affected checks pass, and the result has been inspected. Keep going until then; stop early only for decisions that change scope.`

If the user does want a review point, keep it and say what should be finished before it.

## Model-specific rules (A7, A8)

DROP a rule that only corrected an older model. If other agents still need it (A12), leave it where they read it. Do not choose rules by asking the model which model it is.

## Large or recipe-style skills (S4, S5)

Keep the outcome, the decision criteria and any step whose order truly matters. If the skill has several distinct modes, move each mode's detail into references and route to it from SKILL.md. A single-mode skill does not need a router.

## Deprecated folder (S6)

Move `~/.codex/skills/<name>` to `~/.agents/skills/<name>`. In the plan, list every file in the folder as `create` at the new path and `delete` at the old one.

## AGENTS.md over the byte limit (A1)

MOVE background and long examples into docs and point to them by situation, or split rules into nested AGENTS.md files next to the code they govern.

## After applying

Rescan and report before and after: descriptions cut, skills dropped, AGENTS.md bytes, findings by ID.
