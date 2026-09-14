# Preserve the purpose of useful rules

OpenAI's Astra guidance recommends removing unnecessary instructions and old
workarounds while retaining the constraints that matter for the actual task.
A keyword match is not enough to decide which is which.

Keep boundaries for production, publishing, credentials, personal accounts,
network access, costs and destructive changes. Keep domain facts, package
commands, source media, hashes, evidence requirements and rules written after
a concrete incident. Do not remove a rule just because it says never.

Protected flags are conservative hints. An unflagged finding is unclassified,
not safe to delete. Read the surrounding text and preserve the intent.
With approvals or sandbox restrictions disabled, the written boundaries remain
important. That observation is not permission to change those settings.

Shared instructions may govern other agents too. Preserve their useful
constraints. Use the user's existing authorization and task scope when deciding
whether an approval condition already has been satisfied.

Tighten wording only when the action the rule protects stays protected.
Official and upstream-installed skills are excluded from local rewrites.
Unknown authorship needs verification before any edit.
