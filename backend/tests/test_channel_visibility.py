"""Role changes carry visibility with them unless the caller sets it (CIR-001, CIR-002)."""

from app.devices.service import channel_changes


def test_leaving_unused_shows_the_channel():
    assert channel_changes("unused", {"role": "branch"}) == {"role": "branch", "visible": True}


def test_becoming_unused_hides_the_channel():
    assert channel_changes("branch", {"role": "unused"}) == {"role": "unused", "visible": False}


def test_explicit_visibility_wins():
    changes = {"role": "branch", "visible": False}
    assert channel_changes("unused", changes) == changes


def test_role_change_between_used_roles_keeps_visibility():
    assert channel_changes("branch", {"role": "grid_main"}) == {"role": "grid_main"}


def test_other_fields_pass_through():
    assert channel_changes("unused", {"display_name": "Pool"}) == {"display_name": "Pool"}


def test_input_is_not_mutated():
    changes = {"role": "branch"}
    channel_changes("unused", changes)
    assert changes == {"role": "branch"}
