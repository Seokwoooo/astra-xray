#!/usr/bin/env python3
"""Read-only scan of what Codex loads for GPT-6 Astra: skills list, AGENTS.md chain, config.

Writes the full report as JSON under ~/.astra-xray/scans/ and prints a short summary.
Makes no network calls and changes no files outside ~/.astra-xray.
"""

from __future__ import annotations

import argparse
import fnmatch
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from xray import __version__, agents_md, budget, config, rules, descriptions  # noqa: E402
from xray import constants as C  # noqa: E402
from xray import session as sess  # noqa: E402
from xray import skills as sk  # noqa: E402
from xray.archive import private_write, state_dir  # noqa: E402
from xray.frontmatter import read_skill  # noqa: E402
from xray.paths import local_key  # noqa: E402

TARGET_MODEL = "gpt-6-astra"
SECRET = re.compile(
    r"(sk-[A-Za-z0-9_\-]{16,}|gh[pousr]_[A-Za-z0-9]{20,}|AKIA[0-9A-Z]{16}|xox[baprs]-[A-Za-z0-9\-]{10,}|"
    r"((api[_-]?key|token|secret|password)\s*[:=]\s*)[^\s'\"]{6,})",
    re.IGNORECASE,
)


def mask(text: str) -> str:
    return SECRET.sub(lambda m: (m.group(3) or "") + "•••", text)


def _without(names: list[str], patterns: list[str]) -> list[bool]:
    return [any(fnmatch.fnmatchcase(n, p) for p in patterns) for n in names]


def what_if(entries: list[dict], budget_obj: budget.Budget, patterns: list[str], paths=(), alias_roots=None) -> dict:
    drop = _without([e["name"] for e in entries], patterns)
    selected = {local_key(p) for p in paths}
    drop = [d or local_key(e["path"]) in selected for e, d in zip(entries, drop)]
    kept = [e for e, d in zip(entries, drop) if not d]
    plan = budget.AliasPlan(alias_roots) if alias_roots is not None else None
    result = budget.render_host_catalog(kept, budget_obj, plan=plan)
    return {"removed": sum(drop), "removed_entries": [{"name": e["name"], "path": e["path"]}
                                                       for e, d in zip(entries, drop) if d],
            "selection_note": "Name patterns remove every matching copy. Use --without-path for one copy.",
            "report": result["report"], "warning": result["warning"],
            "used_percent": round(100 * result["cost"] / max(1, budget_obj.limit))}


def latest_catalog_input_mtime(home: Path, inv: dict) -> float | None:
    """Newest local change that can alter the host skills catalog."""
    paths = [home / "config.toml"]
    paths.extend(Path(skill["path"]) for skill in sk.listed_entries(inv))
    mtimes = []
    for path in paths:
        try:
            mtimes.append(path.stat().st_mtime)
        except OSError:
            continue
    return max(mtimes) if mtimes else None


def catalog_comparison(observed: dict, estimated: dict) -> dict:
    """Compare catalog membership; renderer line reproduction cannot detect this drift."""
    captured = {(s["name"], local_key(s["path"])) for s in observed["skills"]}
    files = {(s["name"], local_key(s["path"])) for s in estimated["skills"]}

    def rows(items):
        return [{"name": name, "path": path} for name, path in sorted(items)]

    session_only = captured - files
    files_only = files - captured
    return {
        "session_count": len(captured),
        "file_estimate_count": len(files),
        "shared_count": len(captured & files),
        "session_only_count": len(session_only),
        "files_only_count": len(files_only),
        "session_only": rows(session_only),
        "files_only": rows(files_only),
        "matches": not session_only and not files_only,
    }


def lint_loaded_instruction_text(global_info: dict, chain: dict) -> list[dict]:
    """Lint exactly the instruction bytes Codex loads, not text beyond its limit."""
    targets = []
    if global_info["loaded"]:
        targets.append((global_info["loaded"], None))
    targets.extend(
        (item["path"], item.get("loaded_bytes"))
        for item in chain["files"]
        if item["status"] in ("loaded", "truncated")
    )
    findings = []
    for path, byte_limit in targets:
        try:
            data = Path(path).read_bytes()
        except OSError:
            continue
        if byte_limit is not None:
            data = data[:byte_limit]
        findings += rules.lint_text(path, data.decode("utf-8", errors="replace"))
    return findings


def observed_listing(parsed: dict, budget_obj: budget.Budget, patterns: list[str]) -> dict:
    roots = dict(parsed["roots"])
    entries, captured = [], []
    for e in parsed["entries"]:
        disk = read_skill(Path(e["path"])) if Path(e["path"]).is_file() else None
        full = budget.truncate_description(disk["description"]) if disk and disk["description"] else None
        shown = e["description"]
        if full is None:
            status, cut = "file_missing", None
        elif not full.startswith(shown):
            status, cut = "changed_since_session", None
        else:
            cut = len(full) - len(shown)
            status = "full" if cut == 0 else ("name_only" if not shown else "shortened")
        captured.append({"status": status, "shown_chars": len(shown), "cut_chars": cut})
        entries.append({
            "name": e["name"],
            "description": disk["description"] if full is not None else shown,
            "path": e["path"],
            "alias_root": roots.get(e["alias"]) if e["alias"] else None,
            "alias_root_order": int(e["alias"][1:]) if e["alias"] else None,
            "file_present": disk is not None,
        })
    capture_report = {
        "total": len(captured) + parsed["omission_marker"],
        "included": len(captured),
        "omitted": parsed["omission_marker"],
        "truncated_chars": sum(p["cut_chars"] or 0 for p in captured),
        "truncated_count": sum(1 for p in captured if (p["cut_chars"] or 0) > 0),
    }
    plan = budget.AliasPlan(parsed["roots"]) if parsed["roots"] else None
    sim = budget.render_host_catalog(entries, budget_obj, plan=plan)
    per_skill = []
    for entry, target, source in zip(entries, sim["per_skill"], captured):
        per_skill.append({
            "name": entry["name"],
            "path": entry["path"],
            **target,
            "captured_status": source["status"],
            "captured_shown_chars": source["shown_chars"],
            "captured_cut_chars": source["cut_chars"],
        })
    reproduced = sum(1 for a, b in zip(sim["lines"], (e["line"] for e in parsed["entries"])) if a == b)
    listing = {
        "source": "session",
        "entries": entries,
        "alias_roots": parsed["roots"],
        "used_units": sim["cost"],
        "catalog_complete": parsed["omission_marker"] == 0,
        "unknown_omitted_from_capture": parsed["omission_marker"],
        "report": sim["report"],
        "capture_report": capture_report,
        "skills": per_skill,
        "warning": sim["warning"],
        "average_cut_chars": sim["average_cut_chars"],
        "budget": budget_obj.to_dict(),
        "used_percent": round(100 * sim["cost"] / max(1, budget_obj.limit)),
        "calibration": {
            "reproduced_lines": reproduced,
            "observed_lines": len(parsed["entries"]),
            "meaning": "target-model simulation compared with the captured catalog lines",
        },
    }
    if patterns:
        listing["what_if"] = what_if(entries, budget_obj, patterns)
    return listing


def estimated_listing(inv: dict, budget_obj: budget.Budget, patterns: list[str]) -> dict:
    entries = [
        {"name": s["name"], "description": s["description"], "path": s["path"],
         "alias_root": s["alias_root"], "alias_root_order": s["alias_root_order"]}
        for s in sk.listed_entries(inv)
    ]
    result = budget.render_host_catalog(entries, budget_obj)
    per_skill = [dict(name=e["name"], path=e["path"], **p) for e, p in zip(entries, result["per_skill"])]
    listing = {
        "source": "files",
        "entries": entries,
        "used_units": result["cost"],
        "confidence": "low",
        "limitations": "App/plugin skills can be absent or extra; use a fresh matching session catalog for authoritative membership.",
        "report": result["report"],
        "skills": per_skill,
        "warning": result["warning"],
        "average_cut_chars": result["average_cut_chars"],
        "budget": budget_obj.to_dict(),
        "used_percent": round(100 * result["cost"] / max(1, budget_obj.limit)),
        "format": result["kind"],
    }
    if patterns:
        listing["what_if"] = what_if(entries, budget_obj, patterns)
    return listing


def rebase_listing(previous: dict, inv: dict, cfg: dict, budget_obj: budget.Budget) -> dict:
    """Model edits on known membership. Uncaptured cache files never join the baseline."""
    current = {local_key(s["path"]): s for s in inv["skills"]}
    disabled = sk._disabled_paths(cfg)
    entries, removed = [], []
    for original in previous["entries"]:
        e = dict(original)
        key = local_key(e["path"])
        now = current.get(key)
        reason = None
        if key in disabled or (now and (not now["enabled"] or not now["implicit"])):
            reason = "disabled"
        elif e.get("file_present") and not Path(e["path"]).is_file():
            reason = "removed_file"
        if reason:
            removed.append({"path": e["path"], "name": e["name"], "reason": reason})
            continue
        disk = read_skill(Path(e["path"])) if Path(e["path"]).is_file() else None
        if disk and not disk["error"]:
            e["description"] = disk["description"]
            # Preserve a plugin namespace from the capture.
            e["name"] = e["name"].rsplit(":", 1)[0] + ":" + disk["name"] if ":" in e["name"] else disk["name"]
        entries.append(e)
    roots = previous.get("alias_roots")
    plan = budget.AliasPlan(roots) if roots is not None else None
    sim = budget.render_host_catalog(entries, budget_obj, plan=plan)
    known = {local_key(e["path"]) for e in previous["entries"]}
    unobserved = [{"name": s["name"], "path": s["path"]} for s in sk.listed_entries(inv)
                  if local_key(s["path"]) not in known]
    return {
        "source": "baseline", "confidence": "estimate", "entries": entries,
        "alias_roots": roots,
        "limitations": "Known captured membership with current file edits; a fresh task must confirm runtime membership.",
        "catalog_complete": previous.get("catalog_complete", False),
        "unknown_omitted_from_capture": previous.get("unknown_omitted_from_capture", 0),
        "session": previous.get("session"), "report": sim["report"],
        "skills": [dict(name=e["name"], path=e["path"], **s) for e, s in zip(entries, sim["per_skill"])],
        "budget": budget_obj.to_dict(), "used_units": sim["cost"],
        "used_percent": round(100 * sim["cost"] / max(1, budget_obj.limit)),
        "warning": sim["warning"], "average_cut_chars": sim["average_cut_chars"],
        "removed_since_baseline": removed, "unobserved_files": unobserved,
        "comparison": {"before_units": previous["used_units"], "after_units": sim["cost"],
                       "saved_units": previous["used_units"] - sim["cost"],
                       "unit": budget_obj.kind,
                       "before_description_chars": sum(len(e["description"]) for e in previous["entries"]),
                       "after_description_chars": sum(len(e["description"]) for e in entries)},
    }


def load_baseline(path: str, cwd: Path, model: str, budget_obj: budget.Budget) -> dict:
    data = json.loads(Path(path).expanduser().read_text(encoding="utf-8-sig"))
    if not isinstance(data, dict) or not isinstance(data.get("skills"), dict):
        raise ValueError("baseline must be an astra-xray scan object")
    listing = data.get("skills", {}).get("listing", {})
    env = data.get("environment", {})
    if not isinstance(listing, dict) or not isinstance(env, dict) or data.get("tool") != "astra-xray" or not isinstance(listing.get("entries"), list):
        raise ValueError("baseline must be a scan from astra-xray 0.3.0 or newer")
    if local_key(env.get("cwd", "")) != local_key(str(cwd)):
        raise ValueError("baseline belongs to a different project")
    if env.get("model") != model or listing.get("budget") != budget_obj.to_dict():
        raise ValueError("baseline target model or budget differs; scan again before comparing")
    if listing.get("source") not in ("session", "baseline"):
        raise ValueError("a file-only estimate cannot establish baseline membership; capture a matching task first")
    if (listing.get("session") or {}).get("cwd_matches_scan") is False:
        raise ValueError("baseline capture belongs to a different project")
    if not isinstance(listing.get("used_units"), int) or any(
        not isinstance(e, dict) or any(not isinstance(e.get(k), str) for k in ("name", "path", "description"))
        for e in listing["entries"]
    ):
        raise ValueError("baseline is missing recorded descriptions or budget usage")
    return listing


def run(args) -> dict:
    home = Path(args.codex_home).expanduser() if args.codex_home else config.codex_home()
    cwd = Path(args.cwd).expanduser().resolve()
    cfg = config.load_config(home)
    patterns = [p.strip() for p in (args.without or "").split(",") if p.strip()]

    ownership = getattr(args, "ownership", None)
    ownership_data = json.loads(Path(ownership).expanduser().read_text(encoding="utf-8-sig")) if ownership else {}
    if not isinstance(ownership_data, dict):
        raise ValueError("ownership must be a JSON object with local_skills")
    local_skills = ownership_data.get("local_skills", [])
    if not isinstance(local_skills, list) or any(not isinstance(p, str) or not Path(p).is_absolute() for p in local_skills):
        raise ValueError("local_skills must be a list of absolute SKILL.md paths")
    inv = sk.inventory(cwd, home, cfg, local_skills)
    catalog_changed = latest_catalog_input_mtime(home, inv)
    explicit_session = None if args.session == "auto" else args.session
    found = None if args.session == "none" else sess.find_session(
        home,
        explicit_session,
        cwd=cwd if args.session == "auto" else None,
        not_before=catalog_changed if args.session == "auto" else None,
    )
    model = args.model or TARGET_MODEL
    window, window_source = (args.context_window, "--context-window") if args.context_window else \
        config.model_context_window(cfg, home, model)
    max_tokens = config.get(cfg, "skills.max_context_tokens")
    budget_obj = budget.metadata_budget(window, max_tokens if isinstance(max_tokens, int) else None)
    stale = False
    if found is None and args.session == "auto":
        found = sess.find_session(home, cwd=cwd)
        stale = found is not None
    shell_cli = config.codex_cli_version()
    effective_cli = (found or {}).get("cli_version") or shell_cli

    env = {
        "codex_home": str(home),
        "cwd": str(cwd),
        "codex_cli": effective_cli,
        "codex_cli_source": "captured session" if found and found.get("cli_version") else "shell PATH",
        "shell_codex_cli": shell_cli,
        "model": model,
        "configured_model": cfg.get("model"),
        "reasoning_effort": cfg.get("model_reasoning_effort"),
        "approval_policy": cfg.get("approval_policy"),
        "sandbox_mode": cfg.get("sandbox_mode"),
        "context_window": window,
        "context_window_source": window_source,
        "catalog_inputs_latest_mtime": catalog_changed,
    }

    observed = None
    if found:
        parsed = sess.parse_skills_body(found["skills_body"])
        observed = observed_listing(parsed, budget_obj, patterns)
        observed["session"] = {
            k: found.get(k)
            for k in ("path", "cli_version", "model", "cwd", "timestamp", "skills_timestamp", "selection")
        }
        observed["session"]["cwd_matches_scan"] = sess.cwd_matches(found, cwd)
        observed["session"]["fresh_for_catalog"] = sess.catalog_is_fresh(found, catalog_changed)
    estimated = estimated_listing(inv, budget_obj, patterns)
    primary = observed or estimated
    baseline = getattr(args, "baseline", None)
    if baseline:
        primary = rebase_listing(load_baseline(baseline, cwd, model, budget_obj), inv, cfg, budget_obj)
        primary["baseline_path"] = str(Path(baseline).expanduser())
    elif stale:
        primary = rebase_listing(observed, inv, cfg, budget_obj)
        primary.pop("comparison", None)  # old full descriptions were not recorded, so no before/after proof
        primary["limitations"] += " The source session predates local changes; no historical saving is claimed."
    if patterns or getattr(args, "without_path", None):
        primary["what_if"] = what_if(primary["entries"], budget_obj, patterns, getattr(args, "without_path", None) or [], primary.get("alias_roots"))
    comparison = catalog_comparison(observed, estimated) if observed else None

    global_info = agents_md.global_instructions(home)
    chain = agents_md.project_chain(cwd, cfg)

    findings = rules.lint_config(cfg, env)
    findings += rules.lint_agents(global_info, chain)
    findings += lint_loaded_instruction_text(global_info, chain)
    findings += rules.lint_skills(inv, primary)
    description_audit = descriptions.audit(inv, primary)
    for item in description_audit["rows"]:
        if item["disposition"] in ("review_description", "verify_ownership"):
            findings.append(rules.finding("S12", "info", "Long description to review even without budget overflow", "blog",
                                         item["path"], note=f"{item['description_chars']} chars; ~{item['description_estimated_tokens']} tokens; {item['disposition']}. Length is a review signal, not a rewrite quota."))
    for item in findings:
        if "excerpt" in item:
            item["excerpt"] = mask(item["excerpt"])

    surface = [str(p) for p in agents_md.instruction_files(home, chain, global_info)]
    surface += [s["path"] for s in inv["skills"] if s["provenance"]["editable"]]
    surface = sorted(dict.fromkeys(p for p in surface if Path(p).exists()))

    return {
        "tool": "astra-xray",
        "version": __version__,
        "codex_rules_pinned_to": C.CODEX_PINNED_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "environment": env,
        "skills": {
            "listing": primary,
            "estimate_from_files": estimated if primary is not estimated else None,
            "catalog_comparison": comparison,
            "roots": inv["roots"],
            "installed": [{k: s.get(k) for k in ("name", "path", "scope", "root_kind", "enabled", "implicit", "error", "description", "sha256", "provenance")} for s in inv["skills"]],
            "description_audit": description_audit,
        },
        "agents_md": {"global": global_info, "project": chain},
        "findings": findings,
        "summary": {
            "warn": sum(1 for f in findings if f["severity"] == "warn"),
            "info": sum(1 for f in findings if f["severity"] == "info"),
            "protected": sum(1 for f in findings if f.get("protected")),
        },
        "surface_files": surface,
    }


def summary_text(report: dict, out_path: Path) -> str:
    env = report["environment"]
    listing = report["skills"]["listing"]
    rep = listing["report"]
    cli = env["codex_cli"] or "not found"
    update = f" (rules checked against {C.LATEST_KNOWN_CODEX})" if env["codex_cli"] and \
        config.version_tuple(env["codex_cli"]) < config.version_tuple(C.LATEST_KNOWN_CODEX) else ""
    unit = "tokens" if listing["budget"]["unit"] == "tokens" else "chars"
    lines = [
        f"astra-xray {report['version']} · Codex rules pinned to {C.CODEX_PINNED_VERSION}",
        f"Codex CLI   {cli}{update} ({env['codex_cli_source']}) · target {env['model']} · context {env['context_window'] or '?'} ({env['context_window_source']})",
    ]
    if listing["source"] == "session":
        s = listing["session"]
        lines.append(f"Skills      {rep['included']} in target simulation (host catalog captured by {s['model'] or 'unknown model'} on {str(s['skills_timestamp'] or s['timestamp'])[:10]})")
        cautions = []
        if not s["cwd_matches_scan"]:
            cautions.append("different cwd")
        if not s["fresh_for_catalog"]:
            cautions.append("catalog predates local config/skill changes")
        if cautions:
            lines.append(f"            explicit session caution: {', '.join(cautions)}")
    elif listing["source"] == "baseline":
        lines.append(f"Skills      {rep['included']} modeled on known catalog membership (estimate; fresh task needed for runtime confirmation)")
    else:
        lines.append(f"Skills      {rep['included']} estimated from files (no fresh matching session catalog; low confidence)")
    if listing.get("unknown_omitted_from_capture"):
        lines.append(f"            incomplete capture: {listing['unknown_omitted_from_capture']} unknown skills were omitted by the source session")
    lines.append(f"            budget {listing['budget']['limit']:,} {unit}, {listing['used_percent']}% used · "
                 f"{rep['truncated_count']} descriptions cut ({rep['truncated_chars']:,} chars) · {rep['omitted']} dropped")
    if rep["truncated_count"] or rep["omitted"]:
        shown = "shown" if listing["warning"] else f"not shown (average cut {listing['average_cut_chars']} chars ≤ {C.TRUNCATION_WARNING_THRESHOLD_CHARS})"
        lines.append(f"            Codex warning: {shown}")
    if listing.get("calibration"):
        cal = listing["calibration"]
        lines.append(f"            target simulation vs capture: {cal['reproduced_lines']}/{cal['observed_lines']} lines reproduced")
    if listing.get("comparison"):
        diff = listing["comparison"]
        lines.append(f"            baseline: {diff['before_units']} -> {diff['after_units']} {diff['unit']} ({diff['saved_units']} saved)")
    audit = report["skills"]["description_audit"]
    lines.append(f"Descriptions {audit['review_count']} to review ({audit['ownership_review_count']} need ownership verification); {audit['excluded_upstream_count']} upstream/managed excluded")
    comparison = report["skills"].get("catalog_comparison")
    if comparison and not comparison["matches"]:
        lines.append(f"            file estimate differs: {comparison['files_only_count']} extra, {comparison['session_only_count']} missing")
    if listing.get("what_if"):
        w = listing["what_if"]
        lines.append(f"            what-if without {w['removed']} skills: {w['report']['truncated_count']} cut · "
                     f"{w['report']['omitted']} dropped · {w['used_percent']}% used")
    g, p = report["agents_md"]["global"], report["agents_md"]["project"]
    global_state = f"{g['bytes']:,} bytes" if g["loaded"] else "empty or missing"
    lines.append(f"AGENTS.md   global: {global_state} · project: {sum(1 for f in p['files'] if f['status'] in ('loaded', 'truncated'))} files · "
                 f"{p['used_bytes']:,} / {p['max_bytes']:,} bytes")
    sm = report["summary"]
    lines.append(f"Findings    {sm['warn'] + sm['info']} (warn {sm['warn']} · info {sm['info']}) · protected {sm['protected']}")
    lines.append(f"Report      {out_path}")
    return "\n".join(lines)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--cwd", default=os.getcwd(), help="project directory to scan (default: current)")
    parser.add_argument("--codex-home", help="Codex home (default: $CODEX_HOME or ~/.codex)")
    parser.add_argument("--session", default="auto", help="auto uses a fresh catalog for this cwd from any model; or pass none/a rollout path")
    parser.add_argument("--model", help=f"target model to simulate (default: {TARGET_MODEL}; independent of the source session model)")
    parser.add_argument("--context-window", type=int, help="override the context window used for the skills budget")
    parser.add_argument("--without", help="comma-separated skill names or globs to simulate turning off, e.g. 'firecrawl-*'")
    parser.add_argument("--without-path", action="append", help="exclude one exact SKILL.md path in a simulation; repeatable")
    parser.add_argument("--baseline", help="pre-edit scan JSON; compare current files on its captured membership")
    parser.add_argument("--ownership", help="JSON with local_skills: exact paths whose local authorship has been verified")
    parser.add_argument("--out", help="where to write the JSON report")
    parser.add_argument("--json", action="store_true", help="print the JSON report instead of the summary")
    args = parser.parse_args(argv)

    try:
        report = run(args)
    except (ValueError, OSError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False))
        return 1
    if args.out:
        out_path = Path(args.out).expanduser()
    else:
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
        out_path = state_dir() / "scans" / f"scan-{stamp}.json"
    payload = json.dumps(report, ensure_ascii=False, indent=2)
    private_write(out_path, payload.encode("utf-8"))
    if not args.out:
        private_write(out_path.parent / "latest.json", payload.encode("utf-8"))
    print(payload if args.json else summary_text(report, out_path))
    return 0


if __name__ == "__main__":
    sys.exit(main())
