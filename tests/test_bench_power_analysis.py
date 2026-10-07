"""WP1.3a: the power-analysis derivation is deterministic (same inputs,
same n), per the blueprint's stated acceptance test for this work package.
"""
import pytest

from bench.power_analysis import required_n, scenario_table


def test_required_n_matches_pinned_scenarios():
    # Pinned against the hand-derived table in bench/power_analysis.md.
    assert required_n(0.15, 0.08) == 182
    assert required_n(0.20, 0.10) == 155
    assert required_n(0.25, 0.15) == 85
    assert required_n(0.30, 0.15) == 103
    assert required_n(0.30, 0.20) == 57
    assert required_n(0.40, 0.20) == 77


def test_required_n_is_deterministic():
    assert required_n(0.30, 0.15) == required_n(0.30, 0.15)


def test_scenario_table_rows_match_required_n():
    for row in scenario_table():
        assert row["n"] == required_n(row["pd"], row["delta"])


def test_required_n_rejects_delta_outside_pd():
    with pytest.raises(ValueError):
        required_n(0.10, 0.20)


def test_required_n_rejects_zero_delta():
    with pytest.raises(ValueError):
        required_n(0.30, 0.0)
