"""Bundled resources for the /crucible slash command.

The SKILL.md alongside this file is the canonical, version-controlled source
for the slash command. `crucible cowork install-skill` reads it via
importlib.resources.files(\"skills.crucible\").joinpath(\"SKILL.md\") so the
file ships inside the wheel and stays in sync with the CLI it describes."""
