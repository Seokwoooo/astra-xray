"""Findings. Every rule names the source it comes from; rules without a source do not ship."""

from __future__ import annotations

import os
import re
from pathlib import Path

from . import constants as C
from .config import version_tuple

SOURCES = {
    "blog": "OpenAI, Rethinking skills and prompts for GPT-6 Astra — https://developers.openai.com/blog/rethinking-skills-and-prompts-for-gpt-6-astra",
    "model_guide": "OpenAI, GPT-6 Astra model guide — https://developers.openai.com/api/docs/guides/latest-model",
    "system_card": "OpenAI, GPT-6 Astra system card — https://deploymentsafety.openai.com/gpt-6-astra",
    "codex_render": f"Codex {C.CODEX_PINNED_VERSION} source, ext/skills/src/render.rs — {C.CODEX_SOURCE}/ext/skills/src/render.rs",
    "codex_roots": f"Codex {C.CODEX_PINNED_VERSION} source, ext/skills/src/host_roots.rs — {C.CODEX_SOURCE}/ext/skills/src/host_roots.rs",
    "codex_agents": f"Codex {C.CODEX_PINNED_VERSION} source, core/src/agents_md.rs — {C.CODEX_SOURCE}/core/src/agents_md.rs",
    "docs_skills": "Codex docs, Build skills — https://learn.chatgpt.com/docs/build-skills",
    "docs_config": "Codex docs, Config reference — https://learn.chatgpt.com/docs/config-file/config-reference",
    "releases": "Codex releases — https://github.com/openai/codex/releases",
    "skills_spec": "Agent Skills specification — https://agentskills.io/specification",
    "hygiene": "astra-xray safety check (not an Astra guideline)",
}

PROTECTED = re.compile(
    r"prod(uction)?\b|deploy|release|\b(pnpm|npm|yarn|bun|uv|pip|poetry|cargo)\b|package manager|패키지 매니저|secret|token|credential|password|api[ _-]?key|\.env\b|"
    r"rm\s+-rf|delet|drop\s+(table|database)|truncate|migrat|force[- ]push|push\b|merge\b|"
    r"billing|payment|invoice|customer|pii|personal data|network|internet|connector|account|"
    r"irreversible|destructive|compliance|legal|budget|cost limit|"
    r"source media|original|hash|signature|evidence|proven|placeholder|guess|fabricat|silently|"
    r"explicitly authoriz|read.only|read only|scope|boundary|boundaries|bypass|captcha|cookie|"
    r"원본|해시|증거|추측|조작|읽기 전용|우회|허위|권한|범위|"
    r"운영|배포|릴리스|비밀|시크릿|토큰|자격|비밀번호|키\b|삭제|드롭|마이그레이션|푸시|머지|결제|과금|고객|개인정보|네트워크|인터넷|계정|되돌릴 수 없|파괴|규정|컴플라이언스|비용",
    re.IGNORECASE,
)

LINE_RULES = [
    ("A2", "Required reading before every edit", "blog", re.compile(
        r"(before|prior to)\s+(every|each|any)\s+(edit|change|task|commit|modification)[^.\n]{0,80}\b(read|review|load|consult|open)\b|"
        r"\b(always|must)\s+(read|review|load)\b[^.\n]{0,60}\bbefore\b|"
        r"(매번|항상|모든)\s*.{0,20}(수정|편집|작업|변경).{0,12}(전에|하기 전).{0,30}(읽|검토|확인)",
        re.IGNORECASE)),
    ("A3", "Unconditional test or re-check instruction", "blog", re.compile(
        r"\b(always|must|after (every|each|any))\b[^.\n]{0,40}\b(run|execute)\b[^.\n]{0,40}\b(tests?|test suite|lint|type-?check|build)\b|"
        r"double[- ]check everything|verify everything|"
        r"(항상|반드시|매번|모든 (변경|수정)).{0,20}(테스트|린트|빌드|타입 ?체크).{0,15}(실행|돌려|돌리|수행)",
        re.IGNORECASE)),
    ("A4", "Strong ask-first or never language", "blog", re.compile(
        r"\bnever\b|(?-i:\bMUST NOT\b|\bDO NOT\b)|\bask (the user )?(for )?(permission|approval|confirmation) before\b|"
        r"\bwithout (asking|explicit (approval|permission))\b|"
        r"절대.{0,20}(하지 ?마|금지|안 ?된)|(승인|허락|허가|확인)(을|를)? ?받(고|은 ?후|기 ?전|아야)",
        re.IGNORECASE)),
    ("A5", "Stops after a first pass", "blog", re.compile(
        r"\b(stop|pause|wait)\b[^.\n]{0,40}\b(for|after|until)\b[^.\n]{0,30}\b(review|approval|confirmation|feedback)\b|"
        r"after (the )?first (implementation|draft|pass|attempt)|check in with (me|the user) (before|after)|"
        r"(첫|1차).{0,10}(구현|초안|시도).{0,15}(후|뒤|다음).{0,20}(멈|대기|검토|리뷰|확인)|(리뷰|검토).{0,10}(받을 때까지|기다)",
        re.IGNORECASE)),
    ("A7", "Rule selected by model self-identification", "blog", re.compile(
        r"\bif you are (gpt|claude|gemini|astra|sol|luna|terra|codex|opus|sonnet|haiku)\b|"
        r"(너는|네가|당신이|당신은)\s*(gpt|claude|클로드|제미나이|아스트라|솔|루나)",
        re.IGNORECASE)),
    ("A8", "Names an older model", "blog", re.compile(
        r"\bgpt-?4(\.\d+)?o?\b|\bgpt-?5(\.\d+)?(-(codex|sol|luna|terra|mini))?\b|\bo[134](-mini)?\b|\bgpt-5\.6-(sol|luna|terra)\b",
        re.IGNORECASE)),
]

BROAD_TRIGGER = re.compile(
    r"use (it |this( skill)? )?(when|whenever|for) (working with|anything)\b|"
    r"anything (related to|involving)|all kinds of",
    re.IGNORECASE,
)
PUSHY_TRIGGER = re.compile(
    r"make sure to use (this|the) skill|even if (the user|they) (do(es)?n.t|do not) (explicitly )?(ask|mention)|"
    r"always use this skill|use this skill proactively",
    re.IGNORECASE,
)
RISKY_SCRIPT = re.compile(
    r"(curl|wget)[^\n|]{0,200}\|\s*(ba|z)?sh\b|base64\s+(-d|--decode)[^\n]{0,80}\|\s*(ba|z)?sh|eval\s+\"?\$\((curl|wget)",
    re.IGNORECASE,
)
STOPWORDS = set(
    "a an and are as at be by for from in into is it of on or that the this to use used using when with your you "
    "skill skills codex user users task tasks work working create creating".split()
)
EDITABLE_ROOT_KINDS = {"user", "user-deprecated", "repo", "repo-codex"}


def finding(rule_id, severity, title, source, file=None, line=None, excerpt=None, note=None, protected=False, data=None):
    item = {"id": rule_id, "severity": severity, "title": title, "source": SOURCES[source]}
    if file:
        item["file"] = str(file)
    if line:
        item["line"] = line
    if excerpt:
        item["excerpt"] = excerpt.strip()[:220]
    if note:
        item["note"] = note
    if protected:
        item["protected"] = True
    if data is not None:
        item["data"] = data
    return item


def lint_text(path: str, text: str) -> list[dict]:
    results = []
    in_fence = False
    for number, line in enumerate(text.splitlines(), start=1):
        if line.lstrip().startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence or not line.strip():
            continue
        for rule_id, title, source, pattern in LINE_RULES:
            if pattern.search(line):
                protected = rule_id in ("A4", "A5") and bool(PROTECTED.search(line))
                note = "Protected topic: keep this rule; tighten wording only." if protected else None
                item = finding(rule_id, "info" if rule_id in ("A4", "A8") else "warn", title, source, path, number, line, note, protected)
                if rule_id in ("A4", "A5") and not protected:
                    item["review_required"] = True
                    item["note"] = "Unclassified boundary, not permission to delete it. Judge the purpose and surrounding text."
                results.append(item)
    return results


def _tokens(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z][a-z0-9]+", text.lower()) if w not in STOPWORDS and len(w) > 2}


def lint_skills(inv: dict, listing: dict | None) -> list[dict]:
    results = []
    editable = [s for s in inv["skills"] if s["root_kind"] in EDITABLE_ROOT_KINDS
                and s.get("provenance", {}).get("kind") not in ("managed", "upstream")]

    if listing:
        report = listing["report"]
        cut = [s for s in listing["skills"] if s["status"] in ("shortened", "name_only")]
        dropped = [s for s in listing["skills"] if s["status"] == "omitted"]
        if cut or dropped:
            results.append(finding(
                "S1", "warn", "Skill descriptions cut or dropped by the skills budget", "codex_render",
                note=(f"{len(cut)} shortened, {len(dropped)} dropped, {report['truncated_chars']} characters cut. "
                      + ("Codex shows no warning because the average cut is "
                         f"{listing['average_cut_chars']} characters (threshold {C.TRUNCATION_WARNING_THRESHOLD_CHARS})."
                         if not listing.get("warning") else "Codex shows a warning for this.")),
                data={"shortened": [s["name"] for s in cut], "dropped": [s["name"] for s in dropped]},
            ))

    for skill in inv["skills"]:
        if skill["error"]:
            results.append(finding("S10", "warn", "SKILL.md does not load", "docs_skills", skill["path"], note=skill["error"]))
        elif len(skill["description"]) > C.MAX_CATALOG_DESCRIPTION_CHARS:
            results.append(finding("S9", "warn", "Description longer than 1,024 characters", "codex_render", skill["path"],
                                   note=f"{len(skill['description'])} characters; Codex cuts it at 1,024."))

    for skill in editable:
        desc = skill["description"]
        if BROAD_TRIGGER.search(desc):
            results.append(finding("S2", "warn", "Broad trigger in description", "blog", skill["path"], excerpt=desc))
        if PUSHY_TRIGGER.search(desc):
            results.append(finding("S11", "info", "Trigger wording written to over-trigger", "blog", skill["path"], excerpt=desc,
                                   note="Wording tuned to make other agents trigger more often can load the skill on unrelated Astra tasks."))
        body = Path(skill["path"]).read_text(encoding="utf-8", errors="replace") if Path(skill["path"]).is_file() else ""
        approx_tokens = len(body.encode("utf-8")) // 4
        if skill.get("body_lines", 0) > 500 or approx_tokens > 5000:
            results.append(finding("S4", "info", "Large SKILL.md", "skills_spec", skill["path"],
                                   note=f"{skill.get('body_lines', 0)} lines, ~{approx_tokens} tokens. Move mode-specific detail to references/."))
        steps = len(re.findall(r"^\s*\d+[.)]\s", body, re.MULTILINE))
        if steps >= 15:
            results.append(finding("S5", "info", "Long step-by-step recipe", "blog", skill["path"], note=f"{steps} numbered steps."))
        for item in lint_text(skill["path"], body):
            item["severity"] = "info"  # a skill's own workflow may need these; judge in context
            results.append(item)
        scripts = Path(skill["path"]).parent / "scripts"
        if scripts.is_dir():
            for script in sorted(scripts.rglob("*"))[:200]:
                try:
                    if script.is_file() and script.stat().st_size < 200_000:
                        for number, line in enumerate(script.read_text(encoding="utf-8", errors="ignore").splitlines(), 1):
                            if RISKY_SCRIPT.search(line):
                                results.append(finding("S8", "warn", "Script pipes a download into a shell", "hygiene", script, number, line))
                except OSError:
                    continue

    deprecated = [s for s in inv["skills"] if s["root_kind"] == "user-deprecated"]
    if deprecated:
        results.append(finding("S6", "info", "Skills in the deprecated ~/.codex/skills folder", "codex_roots",
                               note=f"{len(deprecated)} skills. Codex still loads them. This is location information, not a request to move or rename files; inspect dependencies only if migration was requested.",
                               data=[s["name"] for s in deprecated]))
    for name, paths in inv["duplicates"].items():
        results.append(finding("S7", "info", "Same skill name in more than one place", "docs_skills",
                               note=f"{name}: compare capabilities and ownership. A shared name alone does not prove redundancy. Use exact paths for any authorized exclusion.", data=paths))

    pairs = []
    token_sets = [(s, _tokens(s["description"])) for s in editable if not s["error"]]
    for i in range(len(token_sets)):
        for j in range(i + 1, len(token_sets)):
            a, ta = token_sets[i]
            b, tb = token_sets[j]
            if len(ta) < 4 or len(tb) < 4 or a["name"] == b["name"]:
                continue
            score = len(ta & tb) / len(ta | tb)
            if score >= 0.5:
                pairs.append((score, a["name"], b["name"]))
    for score, a, b in sorted(pairs, reverse=True)[:10]:
        results.append(finding("S3", "info", "Two skills with overlapping descriptions", "blog", note=f"{a} ↔ {b} ({score:.0%} shared terms)"))
    return results


def lint_agents(global_info: dict, chain: dict) -> list[dict]:
    results = []
    for info in global_info["files"]:
        if info["status"] == "shadowed":
            results.append(finding("A10", "warn", "Global AGENTS.md hidden by AGENTS.override.md", "codex_agents", info["path"]))
    for info in chain["files"]:
        if info["status"] in ("truncated", "dropped_budget_exhausted"):
            results.append(finding("A1", "warn", "AGENTS.md cut by project_doc_max_bytes", "codex_agents", info["path"],
                                   note=f"{info['status']}: {info.get('loaded_bytes', 0)} of {info['bytes']} bytes reach the model."))
        if info["status"] == "ignored_untrusted_project":
            results.append(finding("A11", "warn", "Project is untrusted, so its AGENTS.md is not loaded", "codex_agents", info["path"]))
        for other in info["shadows"]:
            if Path(info["path"]).name == C.AGENTS_OVERRIDE_FILENAME and info["empty"] and not other["empty"]:
                results.append(finding("A10", "warn", "Empty AGENTS.override.md hides AGENTS.md in the same folder", "codex_agents", other["path"]))
        directory = Path(info["dir"])
        shared = []
        for other_name in ("CLAUDE.md", "GEMINI.md", ".cursorrules"):
            other = directory / other_name
            if other.is_file():
                same = False
                try:
                    same = os.path.samefile(other, info["path"])
                    text = other.read_text(encoding="utf-8", errors="ignore")[:4000]
                    same = same or "@AGENTS.md" in text
                except OSError:
                    pass
                if same:
                    shared.append(other_name)
        if info.get("symlink_to") or shared:
            results.append(finding("A12", "info", "Instruction file shared with other agents", "blog", info["path"],
                                   note="Other models read this file. Keep relaxations Astra-specific or skip them.",
                                   data={"symlink_to": info.get("symlink_to"), "shared_with": shared}))
    used, limit = chain["used_bytes"], chain["max_bytes"]
    if limit and used >= 0.85 * limit:
        results.append(finding("A1", "info", "AGENTS.md chain close to the byte limit", "codex_agents", note=f"{used:,} of {limit:,} bytes."))
    return results


def lint_config(cfg: dict, env: dict) -> list[dict]:
    results = []
    if cfg.get("_error"):
        results.append(finding("C0", "warn", "config.toml could not be parsed", "docs_config", note=cfg["_error"]))
    cli = env.get("codex_cli")
    if cli and version_tuple(cli) < version_tuple(C.LATEST_KNOWN_CODEX):
        results.append(finding("C1", "info", "Codex CLI is older than the version these rules were checked against", "releases",
                               note=f"Captured {cli}; rules pinned to {C.LATEST_KNOWN_CODEX}. This is a compatibility caveat, not a cleanup action. Desktop-bundled Codex and a shell CLI can be different installations."))
    policy = cfg.get("approval_policy")
    if policy in ("untrusted", "on-failure"):
        state = "no longer supported" if policy == "untrusted" else "deprecated"
        results.append(finding("C4", "warn", f"approval_policy = \"{policy}\" is {state}", "docs_config",
                               note="Use on-request for interactive runs or never for non-interactive runs."))
    model = env.get("model") or ""
    effort = cfg.get("model_reasoning_effort")
    if cfg.get("model") == model and "astra" in model and effort in ("none", "minimal"):
        results.append(finding("C2", "warn", f"model_reasoning_effort = \"{effort}\" is not an Astra effort level", "model_guide",
                               note="Astra supports low and above. Start at low."))
    if cfg.get("sandbox_mode") == "danger-full-access" or cfg.get("approval_policy") == "never":
        results.append(finding("C5", "info", "Sandbox or approvals are off", "system_card", protected=True,
                               note="Written scope boundaries still matter. Preserve them; these settings are informational and are not cleanup targets."))
    return results
