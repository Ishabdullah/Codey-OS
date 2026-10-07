"""Fake entry point for the scorecard test fixture (tests/test_scorecard.py).

Deliberately imports exactly the modules needed to hit specific,
hand-computed sub-items in bench/scorecard.py's rubric:
  - core.preferences / core.learning / prompts.layered_prompt -> 1a full credit
  - ccos.core.capability_registry -> makes it both import-graph-reachable
    (6f's second condition) and importable "from outside ccos/" (7a)
"""
import ccos.core.capability_registry
import core.learning
import core.preferences
import prompts.layered_prompt
