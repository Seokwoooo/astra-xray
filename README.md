**English** | [한국어](./README.ko.md)

# astra-xray

Know what Codex gives Astra before you clean it up.

Codex setups collect history. Skills pile up. AGENTS.md grows. Rules written for
an older model stay long after their reason is gone. astra-xray shows what Codex
will place in GPT-6 Astra's context and what deserves another look.

## Install

For the current project:

```bash
npx skills add Seokwoooo/astra-xray
```

Then run it in Codex:

```text
$astra-xray
```

Want it in every project? Add one flag:

```bash
npx skills add Seokwoooo/astra-xray -g
```

That is the whole install. This repository ships one skill. The installer finds
it and detects Codex on its own.

Requires Python 3.9 or newer. The scanner has no Python dependencies.

Already installed? Run the same install command again in the same project.
Keep `-g` if you installed globally. Version 0.3.0 fixes Windows path comparisons
and the description cleanup workflow. Open a new Codex task after updating.

<details>
<summary>Install without Node.js</summary>

```bash
git clone --depth 1 https://github.com/Seokwoooo/astra-xray.git
mkdir -p ~/.agents/skills
cp -R astra-xray/skills/astra-xray ~/.agents/skills/
```

</details>

## What it finds

- Skill descriptions cut by the context budget
- Long personal descriptions worth shortening even when the budget has room
- Skills missing from the model-visible list
- Duplicate skills and triggers that reach too far
- AGENTS.md files that Codex loads or skips
- Instructions left behind for older models
- Config values that no longer fit the current Codex build
- Install scripts that deserve a closer look

Checks cover English and Korean instructions.

## How it works

**Scan** is read-only. It measures the skills catalog and follows the AGENTS.md
chain for the current project. It also checks config without changing it.

**Propose** turns the findings you choose into small diffs. Each proposal points
back to its source.

**Apply** starts with a verified zip backup. It changes only the files you
approved and scans again when the edit is done. A request to patch the reported
scope covers those steps. Each personal description is changed or kept with a
reason. Anything unresolved is reported.

**Restore** puts the backed-up files back. It stops when it finds work that was
added after the backup unless you explicitly choose to overwrite it.

You can also run the scanner directly:

```bash
python3 .agents/skills/astra-xray/scripts/scan.py
```

On Windows use `py -3` or `python` in place of `python3`.

## What it will not remove

Official skills and upstream installations keep their original files. That
includes Playwright, Superpowers and Puppeteer. A user installation folder does
not make a skill user-authored. astra-xray checks installation records and source
evidence before editing. Unknown ownership needs verification.

Some rules are supposed to be strict. astra-xray keeps safeguards for production
systems and secrets. It keeps rules for publishing and destructive actions too.
It can tighten their wording but it does not throw them away.

The tool never changes approval settings or sandbox settings. It leaves hooks
and MCP configuration alone. Instruction cleanup also leaves your default model
and skill locations alone. Scan results and backups stay under
`~/.astra-xray`.

## Accuracy

The budget logic follows the Codex 0.154.0 renderer line by line. The pinned
values and their sources live in
[`constants.py`](skills/astra-xray/scripts/xray/constants.py).

The session used to capture the skills catalog may run any model. Its job is to
show what Codex loaded. GPT-6 Astra remains the separate simulation target.

After an edit the scanner can compare against the saved pre-edit scan with
`--baseline`. It updates known entries without pulling unrelated cache files into
the comparison. A fresh Codex task still needs to confirm the runtime result.
Without a captured catalog the file-based result is a low-confidence estimate.

The reasoning behind this audit is covered in OpenAI's
[Astra skills and prompts article](https://developers.openai.com/blog/rethinking-skills-and-prompts-for-gpt-6-astra)
and the [latest model guide](https://developers.openai.com/api/docs/guides/latest-model).
The budget implementation is pinned to Codex
[`render.rs`](https://github.com/openai/codex/blob/rust-v0.154.0/codex-rs/ext/skills/src/render.rs).

## Development

```bash
python3 -m unittest discover -s tests
```

The budget cases mirror Codex's own renderer tests.

## License

MIT
