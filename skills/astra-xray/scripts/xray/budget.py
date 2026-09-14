"""Port of the skills-list budget from codex-rs/ext/skills/src/render.rs (host skills only).

Given the skills Codex would list, this reproduces which descriptions get shortened,
which skills drop out, and whether Codex shows a warning.
"""

from __future__ import annotations

from pathlib import PurePosixPath

from . import constants as C

LOCATOR_KIND = "file"


def approx_tokens(text: str) -> int:
    return (len(text.encode("utf-8")) + C.APPROX_BYTES_PER_TOKEN - 1) // C.APPROX_BYTES_PER_TOKEN


class Budget:
    def __init__(self, kind: str, limit: int):
        self.kind = kind  # "tokens" or "chars"
        self.limit = limit

    def with_limit(self, limit: int) -> "Budget":
        return Budget(self.kind, limit)

    def cost(self, text: str) -> int:
        return approx_tokens(text) if self.kind == "tokens" else len(text)

    def line_cost(self, line: str) -> int:
        return self.cost(line + "\n")

    def cost_from_counts(self, chars: int, byte_count: int) -> int:
        if self.kind == "tokens":
            return (byte_count + C.APPROX_BYTES_PER_TOKEN - 1) // C.APPROX_BYTES_PER_TOKEN
        return chars

    def to_dict(self) -> dict:
        return {"unit": self.kind, "limit": self.limit}


def metadata_budget(context_window: int | None, max_context_tokens: int | None) -> Budget:
    if max_context_tokens:
        return Budget("tokens", min(max_context_tokens, C.MAX_CONFIGURED_SKILL_TOKEN_BUDGET))
    if context_window and context_window > 0:
        return Budget("tokens", max(1, context_window * C.SKILL_CONTEXT_WINDOW_PERCENT // 100))
    return Budget("chars", C.DEFAULT_SKILL_CHAR_BUDGET)


def truncate_description(description: str) -> str:
    if len(description) <= C.MAX_CATALOG_DESCRIPTION_CHARS:
        return description
    keep = C.MAX_CATALOG_DESCRIPTION_CHARS - len(C.TRUNCATED_DESCRIPTION_SUFFIX)
    return description[:keep] + C.TRUNCATED_DESCRIPTION_SUFFIX


class SkillLine:
    def __init__(self, name: str, description: str, locator: str):
        self.name = name
        self.description = truncate_description(description)
        self.locator = locator

    def render(self, description: str) -> str:
        if not description:
            return f"- {self.name}: ({LOCATOR_KIND}: {self.locator})"
        return f"- {self.name}: {description} ({LOCATOR_KIND}: {self.locator})"

    def render_chars(self, count: int) -> str:
        return self.render(self.description[:count])

    def full_cost(self, budget: Budget) -> int:
        return budget.line_cost(self.render(self.description))

    def minimum_cost(self, budget: Budget) -> int:
        return budget.line_cost(self.render(""))


OMITTED = None  # allocation marker for a skill left out of the list


def _extra_costs(line: SkillLine, budget: Budget) -> list[int]:
    minimum = line.render("")
    min_chars = len(minimum) + 1
    min_bytes = len(minimum.encode("utf-8")) + 1
    min_cost = budget.cost_from_counts(min_chars, min_bytes)
    costs = [0]
    prefix_chars = 0
    prefix_bytes = 0
    for ch in line.description:
        prefix_chars += 1
        prefix_bytes += len(ch.encode("utf-8"))
        cost = budget.cost_from_counts(min_chars + prefix_chars + 1, min_bytes + prefix_bytes + 1)
        costs.append(max(0, cost - min_cost))
    return costs


def _allocate_description_chars(lines: list[SkillLine], budget: Budget, limit: int) -> list[int]:
    extra = [_extra_costs(line, budget) for line in lines]
    chars = [0] * len(lines)
    current = [0] * len(lines)
    remaining = limit
    # Round-robin, one character per skill per pass, as Codex does.
    while True:
        changed = False
        for i, line in enumerate(lines):
            if chars[i] >= len(line.description):
                continue
            nxt = chars[i] + 1
            delta = max(0, extra[i][nxt] - current[i])
            if delta <= remaining:
                chars[i] = nxt
                current[i] = extra[i][nxt]
                remaining -= delta
                changed = True
        if not changed:
            return chars


def allocate(lines: list[SkillLine], budget: Budget) -> list[int | None]:
    if sum(line.full_cost(budget) for line in lines) <= budget.limit:
        return [len(line.description) for line in lines]
    minimum = sum(line.minimum_cost(budget) for line in lines)
    if minimum <= budget.limit:
        return list(_allocate_description_chars(lines, budget, budget.limit - minimum))
    used = 0
    allocations: list[int | None] = []
    for line in lines:
        nxt = used + line.minimum_cost(budget)
        if nxt <= budget.limit:
            used = nxt
            allocations.append(0)
        else:
            allocations.append(OMITTED)
    return allocations


def render_catalog(lines: list[SkillLine], budget: Budget) -> dict:
    allocations = allocate(lines, budget)
    rendered, per_skill = [], []
    omitted = truncated_chars = truncated_count = 0
    for line, alloc in zip(lines, allocations):
        total = len(line.description)
        if alloc is OMITTED:
            omitted += 1
            truncated_chars += total
            truncated_count += 1 if total else 0
            per_skill.append({"status": "omitted", "shown_chars": 0, "cut_chars": total})
            continue
        cut = total - alloc
        if cut > 0:
            truncated_chars += cut
            truncated_count += 1
        rendered.append(line.render_chars(alloc))
        status = "full" if cut == 0 else ("name_only" if alloc == 0 else "shortened")
        per_skill.append({"status": status, "shown_chars": alloc, "cut_chars": cut})
    report = {
        "total": len(lines),
        "included": len(lines) - omitted,
        "omitted": omitted,
        "truncated_chars": truncated_chars,
        "truncated_count": truncated_count,
    }
    return {"lines": rendered, "report": report, "per_skill": per_skill}


def warning_message(report: dict) -> str | None:
    if report["omitted"] > 0:
        noun = "skill" if report["omitted"] == 1 else "skills"
        verb = "was" if report["omitted"] == 1 else "were"
        return (
            f"{C.REMOVAL_WARNING_PREFIX} {report['omitted']} additional {noun} {verb} "
            "not included in the model-visible skills list."
        )
    if average_cut_chars(report) > C.TRUNCATION_WARNING_THRESHOLD_CHARS:
        return C.TRUNCATION_WARNING
    return None


def average_cut_chars(report: dict) -> int:
    if report["total"] == 0 or report["truncated_chars"] == 0:
        return 0
    return (report["truncated_chars"] + report["total"] - 1) // report["total"]


# --- path aliases (aliases.rs, host_aliases.rs) ---------------------------------------


class AliasPlan:
    def __init__(self, roots: list[tuple[str, str]]):
        self.roots = roots  # (alias, value)

    @classmethod
    def build(cls, candidates: list[str], prefix: str = "r") -> "AliasPlan | None":
        seen, roots = set(), []
        for root in candidates:
            if root in seen:
                continue
            seen.add(root)
            roots.append((f"{prefix}{len(roots)}", root))
        return cls(roots) if roots else None

    def shorten(self, locator: str) -> str | None:
        best = None
        for alias, value in self.roots:
            base = value.rstrip("/")
            if locator.startswith(base) and locator[len(base) : len(base) + 1] == "/":
                if best is None or len(value) >= len(best[1]):
                    best = (alias, value, locator[len(base) + 1 :])
        return f"{best[0]}/{best[2]}" if best else None

    def root_lines(self) -> list[str]:
        return [f"- `{alias}` = `{value}`" for alias, value in self.roots]


def _plugin_marketplace_base(path: PurePosixPath) -> PurePosixPath | None:
    candidate = path
    while candidate.parent != candidate:
        parent = candidate.parent
        if parent.name == "cache" and parent.parent.name == "plugins":
            return candidate
        candidate = parent
    return None


def _plugin_version_base(path: PurePosixPath) -> PurePosixPath | None:
    base = _plugin_marketplace_base(path)
    if base is None:
        return None
    parts = path.relative_to(base).parts
    if len(parts) < 2:
        return None
    return base / parts[0] / parts[1]


def shared_alias_roots(alias_roots: list[str]) -> list[str]:
    counts: dict = {}
    for root in alias_roots:
        version = _plugin_version_base(PurePosixPath(root))
        if version is not None:
            counts[version] = counts.get(version, 0) + 1
    shared = []
    for root in alias_roots:
        path = PurePosixPath(root)
        version = _plugin_version_base(path)
        if version is not None and counts.get(version, 0) <= 1:
            shared.append(str(_plugin_marketplace_base(path) or path))
        else:
            shared.append(str(path))
    return shared


def render_body(intro: str, root_lines: list[str], skill_lines: list[str]) -> str:
    lines = ["## Skills", intro]
    if root_lines:
        lines.append("### Skill roots")
        lines.extend(root_lines)
    lines.append("### Available skills")
    lines.extend(skill_lines)
    return "\n" + "\n".join(lines) + "\n"


def _alias_overhead(budget: Budget, root_lines: list[str]) -> int:
    absolute = render_body(C.INTRO_WITH_SOURCE_LOCATORS, [], [])
    aliased = render_body(C.INTRO_WITH_HOST_ALIASES, root_lines, [])
    return max(0, budget.cost(aliased) - budget.cost(absolute))


def render_host_catalog(entries: list[dict], budget: Budget, plan: AliasPlan | None = None) -> dict:
    """entries: dicts with name, description, path, and optional alias_root / alias_root_order.

    Pass `plan` to reuse the root table Codex already chose (observed sessions).
    """
    absolute_lines = [SkillLine(e["name"], e["description"], e["path"]) for e in entries]
    absolute = render_catalog(absolute_lines, budget)
    absolute.update(kind="absolute", root_lines=[])

    if plan is None:
        ordered = sorted(
            (e for e in entries if e.get("alias_root")),
            key=lambda e: e.get("alias_root_order", 1 << 30),
        )
        plan = AliasPlan.build(shared_alias_roots([e["alias_root"] for e in ordered]))
    if plan is None:
        return _finish(absolute, budget)

    root_lines = plan.root_lines()
    overhead = _alias_overhead(budget, root_lines)
    if overhead >= budget.limit:
        return _finish(absolute, budget)
    aliased_lines = [
        SkillLine(
            e["name"],
            e["description"],
            (plan.shorten(e["path"]) or e["path"]) if e.get("alias_root") else e["path"],
        )
        for e in entries
    ]
    aliased = render_catalog(aliased_lines, budget.with_limit(budget.limit - overhead))
    aliased.update(kind="aliased", root_lines=root_lines)

    def total_cost(result: dict) -> int:
        base = _alias_overhead(budget, result["root_lines"]) if result["root_lines"] else 0
        return base + sum(budget.line_cost(line) for line in result["lines"])

    a, b = aliased["report"], absolute["report"]
    if a["included"] != b["included"]:
        better = a["included"] > b["included"]
    elif a["truncated_chars"] != b["truncated_chars"]:
        better = a["truncated_chars"] < b["truncated_chars"]
    else:
        better = total_cost(aliased) < total_cost(absolute)
    chosen = aliased if better else absolute
    chosen["cost"] = total_cost(chosen)
    return _finish(chosen, budget)


def _finish(result: dict, budget: Budget) -> dict:
    if "cost" not in result:
        result["cost"] = sum(budget.line_cost(line) for line in result["lines"])
    result["budget"] = budget.to_dict()
    result["warning"] = warning_message(result["report"])
    result["average_cut_chars"] = average_cut_chars(result["report"])
    return result
