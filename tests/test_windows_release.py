"""Regression cases from the Windows audit, using disposable skills and sessions."""

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
from unittest.mock import patch

SCRIPTS = Path(__file__).resolve().parents[1] / "skills" / "astra-xray" / "scripts"
sys.path.insert(0, str(SCRIPTS))
import scan
import tune
import backup
import restore
from xray import archive, budget, config, descriptions, provenance, rules, session, skills
from xray.frontmatter import read_skill, replace_description
from xray.paths import local_key, path_key


class Fixture(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.user = self.root / "user"
        self.home = self.user / ".codex"
        self.home.mkdir(parents=True)
        self.work = self.root / "work"
        self.work.mkdir()
        (self.work / ".git").mkdir()
        self.state = self.root / "state"
        self.addCleanup(patch.stopall)
        patch.object(Path, "home", return_value=self.user).start()
        patch.object(config, "codex_cli_version", return_value="0.153.4").start()
        patch.dict(os.environ, {"ASTRA_XRAY_HOME": str(self.state)}).start()

    def skill(self, name="personal", desc=None, parent=None):
        path = (parent or self.user / ".agents" / "skills") / name / "SKILL.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("---\nname: " + name + "\ndescription: " + (desc or "Personal workflow. " * 25) +
                        "\n---\nKeep source media unchanged.\n", encoding="utf-8")
        return path

    def plan(self, paths):
        value = {"local_skills": [str(p) for p in paths], "edits": [
            {"path": str(p), "sha256": archive.sha256_path(p),
             "description": "Edit local clips from locked narration. Preserve source media.",
             "reason": "Remove repeated examples; retain locked narration and source preservation."}
            for p in paths]}
        path = self.root / "plan.json"
        path.write_text(json.dumps(value), encoding="utf-8")
        return path

    def invoke(self, module, *args):
        out = io.StringIO()
        with redirect_stdout(out):
            code = module.main(list(args))
        return code, json.loads(out.getvalue())

    def args(self, **overrides):
        return SimpleNamespace(**dict({"cwd": str(self.work), "codex_home": str(self.home),
            "session": "auto", "model": None, "context_window": 100000,
            "without": None, "baseline": None, "ownership": None, "without_path": None}, **overrides))

    def capture(self, paths, timestamp="2099-01-01T00:00:00Z"):
        body = "## Skills\n### Available skills\n" + "\n".join(
            f"- {read_skill(p)['name']}: {read_skill(p)['description']} (file: {p.as_posix()})" for p in paths)
        logs = self.home / "sessions"
        logs.mkdir(exist_ok=True)
        log = logs / "rollout-fixture.jsonl"
        records = [
            {"type": "session_meta", "payload": {"cwd": str(self.work), "timestamp": timestamp, "cli_version": "0.153.4"}},
            {"type": "turn_context", "payload": {"model": "gpt-5.6-sol"}},
            {"type": "world_state", "timestamp": timestamp, "payload": {"state": {"host_skills": {"body": body}}}},
        ]
        log.write_text("\n".join(json.dumps(r) for r in records), encoding="utf-8")
        return log


class WindowsPaths(unittest.TestCase):
    def test_catalog_slashes_case_and_extended_paths_match(self):
        paths = [r"C:\Users\Person\.agents\skills\demo\SKILL.md",
                 "c:/users/person/.agents/skills/demo/SKILL.md",
                 r"\\?\C:\Users\Person\.agents\skills\demo\SKILL.md"]
        self.assertEqual(len({path_key(p) for p in paths}), 1)
        compared = scan.catalog_comparison({"skills": [{"name": "demo", "path": paths[0]}]},
                                           {"skills": [{"name": "demo", "path": paths[1]}]})
        self.assertTrue(compared["matches"])
        self.assertEqual(compared["shared_count"], 1)

    def test_unc_and_posix_semantics(self):
        self.assertEqual(path_key(r"\\server\share\Skill"), path_key("//SERVER/SHARE/skill"))
        self.assertEqual(path_key(r"\\?\UNC\server\share\Skill"), path_key("//SERVER/SHARE/skill"))
        self.assertNotEqual(path_key("/repo/Skill"), path_key("/repo/skill"))

    def test_windows_trust_and_cwd(self):
        cfg = {"projects": {r"C:\Users\Person\project": {"trust_level": "untrusted"}}}
        self.assertEqual(config.project_trust(cfg, Path("c:/users/person/project/sub")), "untrusted")
        self.assertIsNone(config.project_trust(cfg, Path("c:/users/person/project-two")))
        self.assertTrue(session.cwd_matches({"cwd": r"C:\Users\Person\project"}, Path("c:/users/person/project")))

    def test_fallback_toml_windows_strings(self):
        text = r'''model = "gpt-5.6-sol"
[[skills.config]]
path = "C:\\Users\\Person\\skills\\demo\\SKILL.md"
enabled = false
[projects."C:\\Users\\Person\\project"]
trust_level = "untrusted"
'''
        cfg = config._fallback_toml(text)
        self.assertIn(path_key("C:/Users/Person/skills/demo/SKILL.md"), skills._disabled_paths(cfg))
        self.assertEqual(config.project_trust(cfg, Path("c:/users/person/project/sub")), "untrusted")


class Ownership(Fixture):
    def test_user_directory_does_not_prove_authorship(self):
        p = self.skill()
        self.assertEqual(provenance.classify(p)["kind"], "unverified")
        self.assertTrue(provenance.classify(p, local_skills=[str(p)])["editable"])

    def test_popular_families_cannot_be_asserted_local(self):
        for name in ("playwright", "playwright-interactive", "superpowers", "puppeteer", "puppetter"):
            p = self.skill(name)
            self.assertEqual(provenance.classify(p, local_skills=[str(p)])["kind"], "upstream")

    def test_global_installer_lock_and_copied_official(self):
        p = self.skill("video")
        lock = self.user / ".agents" / ".skill-lock.json"
        lock.write_text(json.dumps({"skills": {"video": {"source": "publisher/video", "sourceType": "github"}}}))
        self.assertFalse(provenance.classify(p, local_skills=[str(p)])["editable"])
        official = self.skill("imagegen", parent=self.home / "skills")
        (official.parent / "LICENSE.txt").write_text("Copyright (c) OpenAI. All rights reserved.")
        self.assertEqual(provenance.classify(official)["kind"], "upstream")

    def test_project_lock_is_bound_to_installation(self):
        installed = self.skill("demo", parent=self.work / ".agents" / "skills")
        personal = self.skill("demo")
        (self.work / "skills-lock.json").write_text(json.dumps({"skills": {"demo": {"source": "publisher/demo"}}}))
        self.assertEqual(provenance.classify(installed)["kind"], "upstream")
        self.assertEqual(provenance.classify(personal)["kind"], "unverified")

    def test_reference_link_does_not_prove_upstream(self):
        p = self.skill()
        with p.open("a") as handle:
            handle.write("See https://github.com/microsoft/playwright for browser documentation.\n")
        self.assertTrue(provenance.classify(p, local_skills=[str(p)])["editable"])

    def test_json_publisher_metadata_cannot_be_asserted_local(self):
        p = self.skill("maintained-upstream")
        (p.parent / ".skill-metadata.json").write_text(json.dumps({"source": "publisher/workflow"}))
        self.assertEqual(provenance.classify(p, local_skills=[str(p)])["kind"], "upstream")

    def test_managed_and_superpowers_checkout_are_preserved(self):
        p = self.skill("brainstorming", parent=self.root / "superpowers" / "skills")
        self.assertFalse(provenance.classify(p, local_skills=[str(p)])["editable"])
        for kind in ("system", "plugin", "admin"):
            self.assertEqual(provenance.classify(self.skill(), kind)["kind"], "managed")


class DescriptionWorkflow(Fixture):
    def test_backup_accepts_powershell_utf8_bom_plan(self):
        p = self.skill()
        plan = self.root / "bom-plan.json"
        plan.write_bytes(b'\xef\xbb\xbf' + json.dumps({"modify": [str(p)]}).encode("utf-8"))
        code, result = self.invoke(backup, "create", "--plan", str(plan))
        self.assertEqual(code, 0, result)
        self.assertTrue(result["verified"])

    def test_review_below_budget_includes_disabled_personal_skills(self):
        p = self.skill()
        q = self.skill("disabled")
        managed = self.skill("playwright")
        cfg = {"skills": {"config": [{"path": str(q), "enabled": False}]}}
        inv = skills.inventory(self.work, self.home, cfg, [str(p), str(q)])
        listing = scan.estimated_listing(inv, budget.Budget("tokens", 5440), [])
        audit = descriptions.audit(inv, listing)
        self.assertEqual(listing["report"]["truncated_count"], 0)
        self.assertEqual(audit["owned_review_count"], 2)
        self.assertEqual(audit["excluded_upstream_count"], 1)
        self.assertEqual({r["path"] for r in audit["rows"]}, {str(p), str(q), str(managed)})

    def test_yaml_bom_crlf_multiline_body_are_preserved(self):
        before = b'\xef\xbb\xbf---\r\nname: personal\r\ndescription: >-\r\n  Long old line.\r\n  More examples.\r\nmetadata:\r\n  short-description: Keep this\r\n---\r\nBody must remain byte-identical.\r\n'
        after = replace_description(before, 'Use when editing "clips": preserve source media.')
        self.assertTrue(after.startswith(b'\xef\xbb\xbf'))
        self.assertIn(b'description: "Use when editing \\"clips\\": preserve source media."\r\n', after)
        self.assertEqual(after.split(b'metadata:')[1], before.split(b'metadata:')[1])
        p = self.skill()
        p.write_bytes(after)
        self.assertEqual(read_skill(p)["description"], 'Use when editing "clips": preserve source media.')

    def test_successful_apply_and_restore(self):
        p = self.skill()
        before = p.read_bytes()
        plan = self.plan([p])
        code, preview = self.invoke(tune, "--plan", str(plan))
        self.assertEqual(code, 0)
        self.assertEqual(before, p.read_bytes())
        code, result = self.invoke(tune, "--plan", str(plan), "--apply")
        self.assertEqual(code, 0, result)
        self.assertTrue(result["seal"]["sealed"])
        self.assertGreater(result["description_chars_saved"], 0)
        code, restored = self.invoke(restore, result["backup"]["backup"], "--yes")
        self.assertEqual(code, 0, restored)
        self.assertEqual(before, p.read_bytes())

    def test_upstream_in_batch_prevents_all_edits(self):
        personal, upstream = self.skill(), self.skill("playwright")
        original = personal.read_bytes()
        code, result = self.invoke(tune, "--plan", str(self.plan([personal, upstream])), "--apply")
        self.assertEqual(code, 1)
        self.assertIn("upstream", result["error"])
        self.assertEqual(personal.read_bytes(), original)
        self.assertFalse((self.state / "backups").exists())

    def test_stale_hash_rejects_before_any_mutation(self):
        p, q = self.skill(), self.skill("second")
        plan = self.plan([p, q])
        original = p.read_bytes()
        q.write_bytes(q.read_bytes() + b'User added this.\n')
        code, result = self.invoke(tune, "--plan", str(plan), "--apply")
        self.assertEqual(code, 1)
        self.assertIn("changed since review", result["error"])
        self.assertEqual(p.read_bytes(), original)

    def test_write_failure_rolls_back_already_written_files(self):
        p, q = self.skill(), self.skill("second")
        original = p.read_bytes()
        real_write = tune.write_bytes

        def fail_second(path, data):
            if path == q:
                raise OSError("simulated disk failure")
            real_write(path, data)

        with patch.object(tune, "write_bytes", side_effect=fail_second):
            code, result = self.invoke(tune, "--plan", str(self.plan([p, q])), "--apply")
        self.assertEqual(code, 1, result)
        self.assertEqual(result["unresolved"], [])
        self.assertEqual(p.read_bytes(), original)
        self.assertTrue(result["seal"]["sealed"])

    def test_failed_apply_preserves_concurrent_user_edits(self):
        p, q = self.skill(), self.skill("second")
        real_write = tune.write_bytes
        external = b"User's concurrent changes must survive.\n"

        def fail_after_external_edit(path, data):
            if path == q:
                p.write_bytes(external)
                raise OSError("simulated disk failure")
            real_write(path, data)

        with patch.object(tune, "write_bytes", side_effect=fail_after_external_edit):
            code, result = self.invoke(tune, "--plan", str(self.plan([p, q])), "--apply")
        self.assertEqual(code, 1, result)
        self.assertEqual(result["unresolved"], [str(p)])
        self.assertEqual(p.read_bytes(), external)

    def test_invalid_multiline_batch_rejects_before_any_mutation(self):
        p, q = self.skill(), self.skill("second")
        plan = self.plan([p, q])
        value = json.loads(plan.read_text())
        value["edits"][1]["description"] = "bad\nname: replaced"
        plan.write_text(json.dumps(value))
        original = p.read_bytes()
        code, _ = self.invoke(tune, "--plan", str(plan), "--apply")
        self.assertEqual(code, 1)
        self.assertEqual(p.read_bytes(), original)


class ComparableScans(Fixture):
    def test_no_edit_preserves_capture_alias_table_and_reports_zero_savings(self):
        # The capture may use nonsequential aliases or several roots from one plugin.
        parsed = session.parse_skills_body("""## Skills
### Skill roots
- `r7` = `C:/Users/Person/.codex/plugins/cache/publisher/workflow/1.0/skills`
### Available skills
- workflow: A workflow. (file: r7/deep/nested/workflow/SKILL.md)
""")
        b = budget.Budget("tokens", 5440)
        previous = scan.observed_listing(parsed, b, [])
        after = scan.rebase_listing(previous, {"skills": []}, {}, b)
        self.assertEqual(after["alias_roots"], previous["alias_roots"])
        self.assertEqual(after["comparison"]["saved_units"], 0)

    def test_after_edit_uses_baseline_not_extra_cache_files(self):
        personal = self.skill()
        self.capture([personal])
        before = scan.run(self.args())
        report = self.root / "before.json"
        report.write_text(json.dumps(before))
        personal.write_bytes(replace_description(personal.read_bytes(), "Edit clips from locked narration."))
        for i in range(8):
            self.skill(f"uncaptured-{i}")
        after = scan.run(self.args(baseline=str(report)))
        listing = after["skills"]["listing"]
        self.assertEqual(listing["source"], "baseline")
        self.assertEqual(listing["report"]["total"], 1)
        self.assertEqual(len(listing["unobserved_files"]), 8)
        self.assertGreater(listing["comparison"]["saved_units"], 0)
        self.assertEqual(listing["report"]["truncated_count"], 0)

    def test_stale_matching_capture_retains_known_membership(self):
        personal = self.skill()
        self.capture([personal], timestamp="2020-01-01T00:00:00Z")
        self.skill("unobserved-cache")
        report = scan.run(self.args())
        listing = report["skills"]["listing"]
        self.assertEqual(listing["source"], "baseline")
        self.assertEqual(listing["report"]["total"], 1)
        self.assertNotIn("comparison", listing)
        self.assertEqual(listing["session"]["model"], "gpt-5.6-sol")

    def test_exact_path_exclusion_keeps_other_same_name_copy(self):
        a = self.skill("demo")
        b = self.skill("demo", parent=self.home / "skills")
        entries = [{"name": "demo", "description": "Browser automation", "path": str(p)} for p in (a, b)]
        selected = scan.what_if(entries, budget.Budget("tokens", 5440), [], [str(a)])
        self.assertEqual(selected["removed"], 1)
        self.assertEqual(selected["report"]["total"], 1)
        broad = scan.what_if(entries, budget.Budget("tokens", 5440), ["demo"])
        self.assertEqual(broad["removed"], 2)

    def test_other_configured_model_is_not_cleanup_finding(self):
        config_path = self.home / "config.toml"
        config_path.write_text('model = "gpt-5.6-sol"\nmodel_reasoning_effort = "minimal"\n')
        original = config_path.read_bytes()
        report = scan.run(self.args())
        self.assertEqual(report["environment"]["model"], "gpt-6-astra")
        self.assertEqual(report["environment"]["configured_model"], "gpt-5.6-sol")
        self.assertFalse({"C2", "C3"} & {f["id"] for f in report["findings"]})
        self.assertEqual(config_path.read_bytes(), original)
        self.assertGreaterEqual(report["skills"]["description_audit"]["review_count"], 0)

    def test_wrong_project_baseline_rejected(self):
        p = self.skill()
        self.capture([p])
        data = scan.run(self.args())
        data["environment"]["cwd"] = str(self.root / "other")
        saved = self.root / "baseline.json"
        saved.write_text(json.dumps(data))
        with self.assertRaisesRegex(ValueError, "different project"):
            scan.run(self.args(baseline=str(saved)))

    def test_explicit_foreign_capture_cannot_establish_baseline(self):
        self.capture([self.skill()])
        data = scan.run(self.args())
        data["skills"]["listing"]["session"]["cwd_matches_scan"] = False
        saved = self.root / "foreign-capture.json"
        saved.write_text(json.dumps(data))
        with self.assertRaisesRegex(ValueError, "different project"):
            scan.run(self.args(baseline=str(saved)))

    def test_malformed_ownership_is_a_clear_error(self):
        saved = self.root / "ownership.json"
        for value in ([], {"local_skills": "not-a-list"}, {"local_skills": ["relative/SKILL.md"]}):
            saved.write_text(json.dumps(value))
            with self.assertRaises(ValueError):
                scan.run(self.args(ownership=str(saved)))

    def test_truth_and_source_boundaries_remain_protected(self):
        for text in ("Never modify source media.", "Never summarize from filenames alone; require evidence.",
                     "Never convert a failed lane into guessed evidence.", "Never bypass an OpenMP collision."):
            found = [f for f in rules.lint_text("SKILL.md", text) if f["id"] == "A4"]
            self.assertTrue(found[0]["protected"], text)
        unknown = rules.lint_text("SKILL.md", "Never do this.")[0]
        self.assertTrue(unknown["review_required"])


if __name__ == "__main__":
    unittest.main()
