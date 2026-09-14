# astra-xray

See what GPT-6 Astra actually receives from your Codex setup, then trim what no longer helps.

A Codex skill for people moving to GPT-6 Astra. It measures the parts a prompt can't: how much of your skills list Codex cuts to fit its budget, which AGENTS.md files reach the model, and which old instructions now hold Astra back. It also takes a zip backup before changing anything, so every change can be undone.

```
astra-xray 0.2.0 · Codex rules pinned to 0.154.0
Codex CLI   0.154.0 (captured session) · target gpt-6-astra · context 272000 (models_cache.json)
Skills      61 in target simulation (host catalog captured by gpt-5.6-sol on 2026-09-14)
            budget 5,440 tokens, 100% used · 27 descriptions cut (2,310 chars) · 0 dropped
            Codex warning: not shown (average cut 38 chars ≤ 100)
            target simulation vs capture: 61/61 lines reproduced
            what-if without 12 skills: 0 cut · 0 dropped · 81% used
AGENTS.md   global: 2,114 bytes · project: 2 files · 9,870 / 32,768 bytes
Findings    14 (warn 6 · info 8) · protected 3
```
<sub>Example output with made-up numbers.</sub>

## Why

- **Codex trims your skills list without telling you.** The list gets 2% of the context window. When it overflows, descriptions are cut round-robin, and Codex only warns once the *average* cut passes 100 characters ([render.rs](https://github.com/openai/codex/blob/rust-v0.154.0/codex-rs/ext/skills/src/render.rs)). Many descriptions can be half gone with no warning.
- **Astra reads instructions differently.** OpenAI recommends auditing skills and AGENTS.md for Astra: short descriptions, no forced reading before every edit, no blanket test mandates, a clear definition of done ([blog](https://developers.openai.com/blog/rethinking-skills-and-prompts-for-gpt-6-astra), [model guide](https://developers.openai.com/api/docs/guides/latest-model)).
- **Not everything should go.** Rules about production, secrets, publishing and destructive actions still matter. astra-xray never removes them.

## Install

```bash
git clone --depth 1 https://github.com/Seokwoooo/astra-xray.git
mkdir -p ~/.agents/skills
cp -R astra-xray/skills/astra-xray ~/.agents/skills/
```

In Codex:

```
$astra-xray
```

Or run the scanner on its own:

```bash
python3 ~/.agents/skills/astra-xray/scripts/scan.py
```

Requires Python 3.9 or newer. No dependencies.

## What it does

| Mode | What happens |
|---|---|
| Scan | Read-only. Uses a fresh host catalog captured by any model, applies Astra's budget, and checks it against current files, the AGENTS.md chain and byte limit, and config. |
| Propose | Diffs for the findings you pick, each with its official source. |
| Apply | Zip backup first, verified, then only the approved edits, then a rescan. |
| Restore | Puts every file back, deletes files the edit created, and relinks symlinks. It stops if you changed a file after the edit. |

Ask in plain words: "scan my Codex setup for Astra", "fix the skill descriptions", "undo yesterday's astra-xray changes".

### Checks

- **Skills:** descriptions cut or dropped by the budget; broad or over-eager triggers; overlapping skills; oversized or recipe-style SKILL.md; the deprecated `~/.codex/skills` folder; duplicate names; scripts that pipe downloads into a shell.
- **AGENTS.md:** reading required before every edit; blanket testing; "stop after the first pass"; strong "never/ask first" wording (sorted into protected and legacy); rules keyed to a model's name; files cut by the 32 KiB limit; empty override files hiding real ones; untrusted projects; files shared with other agents.
- **Config:** Codex version, unsupported effort levels, deprecated approval policy, and whether sandbox and approvals are off.

Patterns cover English and Korean instructions.

## Safety

- Scanning is read-only, makes no network calls, and writes only under `~/.astra-xray`.
- Edits happen only after you pick them, and only after a backup verifies. The backup is a private (`0600`) zip outside your repo, so Codex never loads it as a skill.
- Restoring first backs up the current state and seals that backup after the restore, so the restore can be undone safely too.
- It never changes approval, sandbox, hooks, MCP or credential settings.
- Secrets in quoted excerpts are masked.

## Accuracy

The budget logic is a line-by-line port of Codex 0.154.0, including path aliases. The scanner trusts only `world_state.state.host_skills`, ignores conversation text, and automatically uses a catalog only when its directory matches and it postdates local skill/config changes. The source session can run any model; Astra remains the independent simulation target. Without a fresh matching catalog, file discovery is explicitly low confidence because app/plugin skills can be missing or extra. When both sources exist, the report lists their membership difference instead of treating renderer reproduction as inventory proof.

Codex changes. Every pinned number lives in [`constants.py`](skills/astra-xray/scripts/xray/constants.py) with its source.

## Development

```bash
python3 -m unittest discover -s tests
```

Budget tests mirror Codex's own `render_tests.rs`.

## License

MIT
