"""Codex behavior that astra-xray reproduces, pinned to one Codex release.

Every number here was read from the Codex source at the tag below. When Codex
changes, update this file first; the rest of the scanner reads from it.
"""

CODEX_PINNED_VERSION = "0.154.0"
CODEX_SOURCE = "https://github.com/openai/codex/blob/rust-v0.154.0/codex-rs"

# codex-rs/ext/skills/src/render.rs
SKILL_CONTEXT_WINDOW_PERCENT = 2
DEFAULT_SKILL_CHAR_BUDGET = 8_000
MAX_CONFIGURED_SKILL_TOKEN_BUDGET = 10_000
MAX_CATALOG_DESCRIPTION_CHARS = 1_024
TRUNCATED_DESCRIPTION_SUFFIX = "..."
TRUNCATION_WARNING_THRESHOLD_CHARS = 100
APPROX_BYTES_PER_TOKEN = 4

# codex-rs/ext/skills/src/loader/mod.rs
MAX_SKILL_NAME_CHARS = 64
MAX_SCAN_DEPTH = 6
MAX_SKILL_DIRS_PER_ROOT = 2_000

# codex-rs/core/src/config/mod.rs, codex-rs/core/src/agents_md.rs
DEFAULT_PROJECT_DOC_MAX_BYTES = 32 * 1024
AGENTS_OVERRIDE_FILENAME = "AGENTS.override.md"
AGENTS_FILENAME = "AGENTS.md"
DEFAULT_PROJECT_ROOT_MARKERS = [".git"]

# codex-rs/models-manager/models.json (used only when no models cache is found)
KNOWN_CONTEXT_WINDOWS = {
    "gpt-6-astra": 272_000,
}

# codex-rs/ext/skills/src/catalog_prompt.rs
INTRO_WITH_SOURCE_LOCATORS = (
    "A skill is a set of instructions provided through a `SKILL.md` source. Below is the list of "
    "skills that can be used. Each entry includes a name, description, and source locator. `file` "
    "locators are on the host filesystem, `executor package` locators are owned by their execution "
    "environment, `orchestrator package` locators are opaque package identifiers, and `custom "
    "resource` locators use their provider's access mechanism."
)
INTRO_WITH_HOST_ALIASES = (
    "A skill is a set of local instructions to follow that is stored in a `SKILL.md` file. Below is "
    "the list of skills that can be used. Each entry includes a name, description, and a short path "
    "that can be expanded into an absolute path using the skill roots table."
)

TRUNCATION_WARNING = (
    "Skill descriptions were shortened to fit the skills context budget. Codex can still see every "
    "skill, but some descriptions are shorter. Disable unused skills or plugins to leave more room "
    "for the rest."
)
REMOVAL_WARNING_PREFIX = "Exceeded skills context budget. All skill descriptions were removed and"

LATEST_KNOWN_CODEX = "0.154.0"
