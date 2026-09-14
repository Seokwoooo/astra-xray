# Rules that stay

OpenAI's Astra guidance says strong wording written for older models can make Astra stop too early. It does not say to remove safety boundaries. The Astra system card also shows written scope still matters: in a simulated UK AISI evaluation, out-of-scope supply-chain attacks fell from 60 in 499 samples to 2 in 500 once the task explicitly ruled out internet access.

So astra-xray never removes or weakens these. The scanner marks likely ones `protected`, but judge every line yourself; the keyword match is only a hint.

| Category | Examples |
|---|---|
| Facts Astra cannot infer | Package manager, build and test commands, generated files not to edit, required test suites |
| Destructive or irreversible actions | Deleting data, dropping tables, migrations, force pushes, `rm -rf` |
| Permission to publish | Commit, push, merge, deploy, release, sending messages |
| Secrets, accounts and reach | `.env`, credentials, tokens, personal accounts, connectors, network or internet scope |
| Security, compliance and cost | Regulated data, licensing, spending limits |
| Stop conditions | "If the migration check fails, stop and report" |
| Domain invariants | Signatures, hashes, IDs, formats other systems depend on |
| Rules written after an incident | Keep the rule even if its backstory moves to docs |

## Context that raises the bar

- **Sandbox or approvals off (finding C5).** With `danger-full-access` or `approval_policy = "never"`, written rules are the only guard. Treat every boundary as protected.
- **Shared files (finding A12).** Other agents read the same file. Do not relax it for Astra; offer an Astra-only place or skip the change.

## Tightening is allowed

A protected rule can be rewritten only if the protected action stays blocked and the user approves:

- Before: `NEVER run any commands without asking.`
- After: `Ask before commands that write outside this repo, touch production, or publish anything. Local builds and tests are fine to run.`

If you cannot tighten without opening a path to the protected action, leave the rule as it is.
