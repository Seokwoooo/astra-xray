"""Description cost review, independent of whether the total catalog overflows."""

from __future__ import annotations

from .budget import approx_tokens
from .paths import local_key

# Review heuristics, not OpenAI limits or mandatory rewrite targets. Preserve
# useful task boundaries even when a description remains above these values.
REVIEW_CHARS = 200
REVIEW_TOKENS = 80


def audit(inv: dict, listing: dict) -> dict:
    visible = {local_key(s["path"]): s for s in listing["skills"]}
    rows = []
    for skill in inv["skills"]:
        desc = skill["description"]
        provenance = skill.get("provenance", {"kind": "unverified", "editable": False})
        cost = approx_tokens(desc)
        long = len(desc) > REVIEW_CHARS or cost > REVIEW_TOKENS
        active = bool(skill.get("enabled", True) and skill.get("implicit", True))
        if provenance["kind"] in ("managed", "upstream"):
            disposition = "excluded_upstream"
        elif skill.get("error"):
            disposition = "invalid_frontmatter"
        elif long:
            disposition = "review_description" if provenance["editable"] else "verify_ownership"
        else:
            disposition = "keep_concise"
        rows.append({
            "name": skill["name"], "path": skill["path"], "description": desc,
            "sha256": skill.get("sha256"), "description_chars": len(desc),
            "description_bytes": len(desc.encode("utf-8")), "description_estimated_tokens": cost,
            "enabled": skill.get("enabled", True), "implicit": skill.get("implicit", True),
            "in_target_catalog": local_key(skill["path"]) in visible,
            "active": active, "long_description": long, "provenance": provenance,
            "disposition": disposition,
        })
    rows.sort(key=lambda r: (-r["description_estimated_tokens"], r["path"]))
    candidates = [r for r in rows if r["disposition"] in ("review_description", "verify_ownership")]
    return {"thresholds": {"chars": REVIEW_CHARS, "estimated_tokens": REVIEW_TOKENS,
                           "meaning": "review heuristics, not mandatory length limits"},
            "review_count": len(candidates), "owned_review_count": sum(r["provenance"]["editable"] for r in candidates),
            "ownership_review_count": sum(r["disposition"] == "verify_ownership" for r in candidates),
            "excluded_upstream_count": sum(r["disposition"] == "excluded_upstream" for r in rows),
            "total_description_chars": sum(r["description_chars"] for r in rows),
            "rows": rows}
