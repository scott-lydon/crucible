"""White-box brief assembly: oracle descriptions folded into the search prompt."""

from __future__ import annotations

from modules.red import compose_white_box_brief


def test_brief_lists_every_oracle_description() -> None:
    brief = compose_white_box_brief(
        [
            ("held_out", "generates fresh tests post-submit"),
            ("metamorphic", "checks transformation relations"),
        ]
    )
    assert "WHITE-BOX mode" in brief
    assert "- held_out: generates fresh tests post-submit" in brief
    assert "- metamorphic: checks transformation relations" in brief


def test_brief_is_empty_when_no_oracles_are_wired() -> None:
    # A white-box pass with no oracles falls back to the generic note rather
    # than emitting an empty heading.
    assert compose_white_box_brief([]) == ""
