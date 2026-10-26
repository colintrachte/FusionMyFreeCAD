"""Tests for Slice 5 Continuous A/B Attribution & Performance Benchmark."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FIXTURE_PATH = ROOT / "tests" / "fixtures" / "freecad-ab-attribution.json"


def test_ab_attribution_fixture_meets_simulated_contract():
    assert FIXTURE_PATH.is_file(), "A/B attribution fixture must exist"
    data = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))

    # Validate top-level schema
    assert "metadata" in data
    assert "journeys" in data
    assert "attribution" in data
    assert "gates" in data
    assert data["passed"] is True
    assert data["mode"] == "simulated-contract"
    assert data["performanceEvidence"] is False

    # Validate Journey 1: Startup
    startup = data["journeys"]["startup"]
    assert startup["durationMs"] <= 250.0
    assert startup["networkRequests"] == 0

    # Validate Journey 2: Focus
    focus = data["journeys"]["focus"]
    assert focus["metrics"]["p95Ms"] <= 2.0
    assert focus["titleBarReplacements"] == 0
    assert focus["searchBarFilters"] == 1

    # Validate Journey 3: Transitions
    transitions = data["journeys"]["transitions"]
    assert transitions["native"]["completed"] == 52
    assert transitions["fmf"]["completed"] == 52
    assert len(transitions["fmf"]["failures"]) == 0
    assert transitions["deltaP95Ms"] <= 100.0

    # Validate Journey 4: Idle & Lifecycle
    idle = data["journeys"]["idle"]
    assert idle["parameterFlushes"] == 0
    assert idle["stableObserverCount"] >= 0

    # Validate Attribution records
    attribution = data["attribution"]
    assert "transitionPhases" in attribution
    assert "actionRegistry" in attribution
    assert "lifecycle" in attribution
    assert "persistence" in attribution

    # Validate Gates
    gates = data["gates"]
    assert gates["startupIncrementWithinLimit"] is True
    assert gates["focusPairP95WithinLimit"] is True
    assert gates["transitionP95DeltaWithinLimit"] is True
    assert gates["zeroIdleParameterWrites"] is True
    assert gates["zeroUnexpectedTransitions"] is True
    assert gates["inventoryScansBounded"] is True


def test_probe_ab_attribution_programmatic_run():
    from tools import probe_ab_attribution

    result = probe_ab_attribution.run_ab_attribution(live=False, cycles=2)

    assert result["passed"] is True
    assert result["mode"] == "simulated-contract"
    assert result["performanceEvidence"] is False
    assert result["journeys"]["transitions"]["native"]["completed"] == 8
    assert result["journeys"]["transitions"]["fmf"]["completed"] == 8
    assert result["gates"]["zeroIdleParameterWrites"] is True
