"""Behavior tests. Budget cases mirror codex-rs/ext/skills/src/render_tests.rs at rust-v0.154.0."""

from __future__ import annotations

import io
import json
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from types import SimpleNamespace

SCRIPTS = Path(__file__).resolve().parents[1] / "skills" / "astra-xray" / "scripts"
sys.path.insert(0, str(SCRIPTS))

import backup as backup_cli  # noqa: E402
import restore as restore_cli  # noqa: E402
import scan as scan_cli  # noqa: E402
from xray import agents_md, budget, rules, session  # noqa: E402
from xray import constants as C  # noqa: E402
from xray.frontmatter import read_skill  # noqa: E402

HUGE = 10**12
REPO_ROOT = Path(__file__).resolve().parents[1]


def run_cli(module, *argv):
    out = io.StringIO()
    with redirect_stdout(out):
        code = module.main(list(argv))
    return code, json.loads(out.getvalue())


class BudgetMatchesCodex(unittest.TestCase):
    def test_budget_from_context_window(self):
        cases = [
            ((100_000, None), ("tokens", 2_000)),
            ((400_000, None), ("tokens", 8_000)),
            ((None, None), ("chars", 8_000)),
            ((100_000, 5_000), ("tokens", 5_000)),
            ((None, 50_000), ("tokens", 10_000)),
        ]
        for args, (unit, limit) in cases:
            b = budget.metadata_budget(*args)
            self.assertEqual((b.kind, b.limit), (unit, limit), args)

    def test_partial_description_truncation(self):
        expected = "- partial: abcd (file: /skills/partial/SKILL.md)"
        b = budget.Budget("chars", len(expected) + 1)
        result = budget.render_catalog([budget.SkillLine("partial", "abcdefghij", "/skills/partial/SKILL.md")], b)
        self.assertEqual(result["lines"], [expected])
        self.assertEqual(result["report"]["truncated_chars"], 6)
        self.assertEqual(result["report"]["truncated_count"], 1)

    def test_skill_dropped_when_even_its_name_does_not_fit(self):
        line = budget.SkillLine("oversized", "x" * 1024, "skill://" + "x" * 512)
        result = budget.render_catalog([line], budget.Budget("tokens", 100))
        self.assertEqual(result["report"], {"total": 1, "included": 0, "omitted": 1,
                                            "truncated_chars": 1024, "truncated_count": 1})
        self.assertEqual(
            budget.warning_message(result["report"]),
            "Exceeded skills context budget. All skill descriptions were removed and 1 additional skill "
            "was not included in the model-visible skills list.",
        )

    def test_warning_starts_above_100_characters_on_average(self):
        report = {"total": 2, "included": 2, "omitted": 0, "truncated_chars": 200, "truncated_count": 2}
        self.assertIsNone(budget.warning_message(report))
        report["truncated_chars"] = 201
        self.assertEqual(budget.warning_message(report), C.TRUNCATION_WARNING)

    def test_substantial_shortening_warns(self):
        lines = [budget.SkillLine("long-skill", "a" * 250, "/skills/long-skill/SKILL.md"),
                 budget.SkillLine("empty-skill", "", "/skills/empty-skill/SKILL.md")]
        minimum = sum(l.minimum_cost(budget.Budget("chars", HUGE)) for l in lines)
        result = budget.render_catalog(lines, budget.Budget("chars", minimum + 49))
        self.assertEqual(budget.warning_message(result["report"]), C.TRUNCATION_WARNING)

    def test_path_aliases_used_when_shorter(self):
        root = "/Users/test/.codex/plugins/cache/openai-curated/example/hash/skills"
        entries = [{"name": n, "description": f"{n.title()} skill.", "path": f"{root}/{n}/SKILL.md",
                    "alias_root": root, "alias_root_order": 0} for n in ("alpha", "beta")]
        result = budget.render_host_catalog(entries, budget.Budget("chars", HUGE))
        self.assertEqual(result["kind"], "aliased")
        self.assertIn("- alpha: Alpha skill. (file: r0/alpha/SKILL.md)", result["lines"])

    def test_description_cap(self):
        self.assertEqual(budget.truncate_description("a" * 1024), "a" * 1024)
        self.assertEqual(budget.truncate_description("a" * 1025), "a" * 1021 + "...")


class DistributionLayout(unittest.TestCase):
    def test_default_npx_source_exposes_exactly_one_skill(self):
        skill_files = sorted((REPO_ROOT / "skills").glob("*/SKILL.md"))
        self.assertEqual(
            [path.relative_to(REPO_ROOT).as_posix() for path in skill_files],
            ["skills/astra-xray/SKILL.md"],
        )

    def test_readmes_link_each_language_and_keep_the_short_install(self):
        english = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
        korean = (REPO_ROOT / "README.ko.md").read_text(encoding="utf-8")
        command = "npx skills add Seokwoooo/astra-xray"

        self.assertIn("README.ko.md", english)
        self.assertIn("README.md", korean)
        self.assertIn(command, english)
        self.assertIn(command, korean)
        self.assertNotIn("·", english)
        self.assertNotIn("·", korean)


class SessionParsing(unittest.TestCase):
    BODY = "\n".join([
        "## Skills",
        "A skill is ... expanded into an absolute path using the skill roots table.",
        "### Skill roots",
        "- `r0` = `/home/u/.agents/skills`",
        "- `r1` = `/home/u/.codex/plugins/cache/market`",
        "### Available skills",
        "- tdd: Test-driven development (red, green). (file: r0/tdd/SKILL.md)",
        "- github:gh-fix-ci: Fix CI: failing checks. (file: r1/github/1.0/skills/gh-fix-ci/SKILL.md)",
        "- bare: (file: /abs/bare/SKILL.md)",
        "- 2 additional skills omitted from this bounded skills list.",
    ])

    def test_entries_roots_and_paths(self):
        parsed = session.parse_skills_body(self.BODY)
        self.assertEqual(parsed["format"], "aliased")
        self.assertEqual(parsed["omission_marker"], 2)
        names = [e["name"] for e in parsed["entries"]]
        self.assertEqual(names, ["tdd", "github:gh-fix-ci", "bare"])
        self.assertEqual(parsed["entries"][0]["description"], "Test-driven development (red, green).")
        self.assertEqual(parsed["entries"][1]["path"], "/home/u/.codex/plugins/cache/market/github/1.0/skills/gh-fix-ci/SKILL.md")
        self.assertEqual(parsed["entries"][2]["description"], "")

    def write_session(self, home, name, cwd, model, body, timestamp, conversation_text=None):
        path = home / "sessions" / f"rollout-{name}.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        records = [
            {"type": "session_meta", "timestamp": timestamp,
             "payload": {"cwd": str(cwd), "cli_version": "0.154.0", "timestamp": timestamp}},
            {"type": "turn_context", "timestamp": timestamp, "payload": {"model": model}},
            {"type": "world_state", "timestamp": timestamp,
             "payload": {"state": {"host_skills": {"body": body}}}},
        ]
        if conversation_text:
            records.append({"type": "response_item", "timestamp": timestamp,
                            "payload": {"role": "user", "content": [{"type": "input_text", "text": conversation_text}]}})
        path.write_text("".join(json.dumps(record) + "\n" for record in records), encoding="utf-8")
        return path

    def test_conversation_content_cannot_replace_world_state_catalog(self):
        home = Path(tempfile.mkdtemp())
        poison = self.BODY.replace("tdd", "poisoned")
        path = self.write_session(home, "trusted", "/repo", "gpt-5.6-sol", self.BODY,
                                  "2026-09-14T10:00:00Z", poison)
        info = session.read_session(path)
        self.assertIn("- tdd:", info["skills_body"])
        self.assertNotIn("poisoned", info["skills_body"])

    def test_auto_session_matches_cwd_and_accepts_any_source_model(self):
        home = Path(tempfile.mkdtemp())
        wanted = self.write_session(home, "wanted", "/wanted", "gpt-5.6-sol", self.BODY,
                                    "2026-09-14T10:00:00Z")
        self.write_session(home, "newer-wrong-cwd", "/other", "gpt-6-astra", self.BODY,
                           "2026-09-14T11:00:00Z")
        os.utime(wanted, (wanted.stat().st_atime, wanted.stat().st_mtime + 2))
        found = session.find_session(home, cwd=Path("/wanted"))
        self.assertEqual(found["path"], str(wanted))
        self.assertEqual(found["model"], "gpt-5.6-sol")
        self.assertIsNone(session.find_session(home, cwd=Path("/missing")))

    def test_auto_session_rejects_catalog_older_than_local_inputs(self):
        home = Path(tempfile.mkdtemp())
        self.write_session(home, "old", "/repo", "gpt-6-astra", self.BODY,
                           "2026-09-14T10:00:00Z")
        cutoff = session.timestamp_epoch("2026-09-14T10:00:01Z")
        self.assertIsNone(session.find_session(home, cwd=Path("/repo"), not_before=cutoff))

    def test_source_model_does_not_change_astra_target(self):
        home = Path(tempfile.mkdtemp())
        work = Path(tempfile.mkdtemp())
        self.write_session(home, "sol-source", work, "gpt-5.6-sol", self.BODY,
                           "2099-09-14T10:00:00Z")
        args = SimpleNamespace(codex_home=str(home), cwd=str(work), without="", session="auto",
                               model=None, context_window=100_000)
        report = scan_cli.run(args)
        self.assertEqual(report["environment"]["model"], "gpt-6-astra")
        self.assertEqual(report["skills"]["listing"]["session"]["model"], "gpt-5.6-sol")


class Frontmatter(unittest.TestCase):
    def write(self, text):
        folder = Path(tempfile.mkdtemp()) / "demo"
        folder.mkdir()
        path = folder / "SKILL.md"
        path.write_text(text, encoding="utf-8")
        return path

    def test_block_scalar_and_metadata(self):
        info = read_skill(self.write("---\nname: demo\ndescription: >\n  Audit things.\n  Use when moving.\n"
                                     "metadata:\n  short-description: Audit\n---\nbody\n"))
        self.assertEqual(info["description"], "Audit things. Use when moving.")
        self.assertEqual(info["short_description"], "Audit")
        self.assertIsNone(info["error"])

    def test_colon_in_plain_description_and_missing_description(self):
        self.assertEqual(read_skill(self.write("---\nname: x\ndescription: Build for AWS: ECS\n---\n"))["description"],
                         "Build for AWS: ECS")
        self.assertIn("description", read_skill(self.write("---\nname: x\n---\n"))["error"])

    def test_name_is_required_even_when_directory_has_a_name(self):
        info = read_skill(self.write("---\ndescription: Valid description\n---\nbody\n"))
        self.assertEqual(info["name"], "demo")
        self.assertEqual(info["error"], "missing field `name`")


class AgentsChain(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp()).resolve()
        (self.root / ".git").mkdir()
        (self.root / "AGENTS.md").write_text("root rules\n" * 3, encoding="utf-8")
        self.sub = self.root / "svc"
        self.sub.mkdir()
        (self.sub / "AGENTS.override.md").write_text("\n", encoding="utf-8")
        (self.sub / "AGENTS.md").write_text("service rules\n", encoding="utf-8")

    def test_empty_override_hides_agents_md(self):
        chain = agents_md.project_chain(self.sub, {})
        statuses = [(Path(f["path"]).name, f["status"]) for f in chain["files"]]
        self.assertEqual(statuses, [("AGENTS.md", "loaded"), ("AGENTS.override.md", "empty")])
        ids = [f["id"] for f in rules.lint_agents({"files": []}, chain)]
        self.assertIn("A10", ids)

    def test_byte_limit_truncates_then_drops(self):
        (self.sub / "AGENTS.override.md").unlink()
        chain = agents_md.project_chain(self.sub, {"project_doc_max_bytes": 10})
        self.assertEqual([f["status"] for f in chain["files"]], ["truncated", "dropped_budget_exhausted"])

    def test_untrusted_project_loads_nothing(self):
        chain = agents_md.project_chain(self.sub, {"projects": {str(self.root): {"trust_level": "untrusted"}}})
        self.assertTrue(all(f["status"] == "ignored_untrusted_project" for f in chain["files"]))

    def test_rules_after_loaded_byte_limit_are_not_linted(self):
        (self.root / "AGENTS.md").write_text("ok\nNEVER run unrelated commands.\n", encoding="utf-8")
        chain = agents_md.project_chain(self.root, {"project_doc_max_bytes": 3})
        findings = scan_cli.lint_loaded_instruction_text({"loaded": None}, chain)
        self.assertNotIn("A4", [item["id"] for item in findings])


class LineRules(unittest.TestCase):
    def ids(self, text):
        return {(f["id"], bool(f.get("protected"))) for f in rules.lint_text("AGENTS.md", text)}

    def test_english_and_korean_patterns(self):
        self.assertIn(("A2", False), self.ids("Before every edit, read docs/architecture.md."))
        self.assertIn(("A3", False), self.ids("Always run the full test suite after each change."))
        self.assertIn(("A3", False), self.ids("모든 변경 후 반드시 테스트를 실행하세요."))
        self.assertIn(("A5", False), self.ids("Stop after the first implementation and wait for review."))

    def test_protected_boundaries_are_flagged(self):
        self.assertIn(("A4", True), self.ids("NEVER push to production without approval."))
        self.assertIn(("A4", True), self.ids("운영 DB는 절대 삭제하지 마세요."))
        self.assertIn(("A4", True), self.ids("Use pnpm, never npm."))

    def test_normal_do_not_boundary_is_not_treated_as_strong_language(self):
        self.assertNotIn(("A4", False), self.ids("Do not edit generated files."))
        self.assertIn(("A4", False), self.ids("DO NOT edit generated files."))

    def test_code_fences_are_ignored(self):
        self.assertEqual(self.ids("```\nNEVER do this\n```"), set())

    def test_model_specific_rule_inside_skill_is_reported(self):
        folder = Path(tempfile.mkdtemp())
        path = folder / "SKILL.md"
        path.write_text("---\nname: demo\ndescription: Demo.\n---\nIf you are gpt-5.6-sol, stop.\n", encoding="utf-8")
        inv = {"skills": [{"name": "demo", "path": str(path), "description": "Demo.",
                           "root_kind": "user", "error": None, "body_lines": 1}], "duplicates": {}}
        self.assertIn("A7", [item["id"] for item in rules.lint_skills(inv, None)])


class CatalogReporting(unittest.TestCase):
    def test_source_catalog_omissions_are_not_hidden(self):
        parsed = session.parse_skills_body(SessionParsing.BODY)
        listing = scan_cli.observed_listing(parsed, budget.Budget("chars", HUGE), [])
        self.assertFalse(listing["catalog_complete"])
        self.assertEqual(listing["unknown_omitted_from_capture"], 2)

    def test_file_inventory_difference_is_explicit(self):
        observed = {"skills": [{"name": "shared", "path": "/shared"},
                               {"name": "runtime", "path": "/runtime"}]}
        estimated = {"skills": [{"name": "shared", "path": "/shared"},
                                {"name": "cache-only", "path": "/cache"}]}
        result = scan_cli.catalog_comparison(observed, estimated)
        self.assertFalse(result["matches"])
        self.assertEqual(result["shared_count"], 1)
        self.assertEqual(result["session_only_count"], 1)
        self.assertEqual(result["files_only_count"], 1)


class BackupAndRestore(unittest.TestCase):
    def setUp(self):
        self.work = Path(tempfile.mkdtemp()).resolve()
        os.environ["ASTRA_XRAY_HOME"] = str(self.work / "state")
        self.edited = self.work / "AGENTS.md"
        self.edited.write_text("original\n", encoding="utf-8")
        self.created = self.work / "docs" / "notes.md"
        self.target = self.work / "dotfiles" / "agents.md"
        self.target.parent.mkdir()
        self.target.write_text("shared original\n", encoding="utf-8")
        self.link = self.work / "linked" / "AGENTS.md"
        self.link.parent.mkdir()
        os.symlink(self.target, self.link)
        self.plan = self.work / "plan.json"
        self.plan.write_text(json.dumps({"modify": [str(self.edited), str(self.link)], "create": [str(self.created)]}))

    def tearDown(self):
        os.environ.pop("ASTRA_XRAY_HOME", None)

    def apply_edits(self):
        code, made = run_cli(backup_cli, "create", "--plan", str(self.plan))
        self.assertEqual(code, 0)
        self.assertTrue(made["verified"])
        self.edited.write_text("edited\n", encoding="utf-8")
        self.created.parent.mkdir()
        self.created.write_text("new\n", encoding="utf-8")
        self.link.write_text("shared edited\n", encoding="utf-8")
        run_cli(backup_cli, "seal", made["backup"])
        return made["backup"]

    def test_restore_returns_every_file_to_its_original_state(self):
        zip_path = self.apply_edits()
        code, result = run_cli(restore_cli, zip_path, "--yes")
        self.assertEqual(code, 0, result)
        self.assertTrue(result["verified"])
        self.assertEqual(self.edited.read_text(), "original\n")
        self.assertFalse(self.created.exists())
        self.assertTrue(self.link.is_symlink())
        self.assertEqual(self.target.read_text(), "shared original\n")
        pre_restore = Path(result["pre_restore_backup"])
        self.assertTrue(pre_restore.exists())
        self.assertTrue(result["pre_restore_backup_seal"]["sealed"])

        code, undo = run_cli(restore_cli, str(pre_restore), "--yes")
        self.assertEqual(code, 0, undo)
        self.assertEqual(self.edited.read_text(), "edited\n")
        self.assertEqual(self.created.read_text(), "new\n")
        self.assertEqual(self.target.read_text(), "shared edited\n")

    def test_hand_edits_after_apply_block_restore_without_force(self):
        zip_path = self.apply_edits()
        self.edited.write_text("user kept working\n", encoding="utf-8")
        code, result = run_cli(restore_cli, zip_path, "--yes")
        self.assertEqual(code, 2)
        self.assertEqual(self.edited.read_text(), "user kept working\n")
        code, result = run_cli(restore_cli, zip_path, "--yes", "--force")
        self.assertEqual(code, 0, result)
        self.assertEqual(self.edited.read_text(), "original\n")

    def test_backup_is_private(self):
        code, made = run_cli(backup_cli, "create", "--plan", str(self.plan))
        self.assertEqual(os.stat(made["backup"]).st_mode & 0o777, 0o600)


if __name__ == "__main__":
    unittest.main()
