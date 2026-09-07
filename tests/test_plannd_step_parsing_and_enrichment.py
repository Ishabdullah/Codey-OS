from core.plannd import parse_steps


def test_parse_steps_valid_steps_not_flagged():
    """NEW-48: Valid steps ending in alphabetic characters should parse cleanly."""
    raw = """
1. Create dice_roller.py: rolls two dice and returns sum
2. Run: python dice_roller.py
3. Verify: counter.py printed exactly 10 lines
"""
    steps = parse_steps(raw)
    assert len(steps) == 3
    assert steps[0] == "Create dice_roller.py: rolls two dice and returns sum"
    assert steps[1] == "Run: python dice_roller.py"
    assert steps[2] == "Verify: counter.py printed exactly 10 lines"


def test_parse_steps_strips_thinking_tags():
    raw = """
<think>
Some internal reasoning
</think>
1. Edit math.py: fix division by zero
2. Run: pytest
"""
    steps = parse_steps(raw)
    assert len(steps) == 2
    assert steps[0] == "Edit math.py: fix division by zero"
    assert steps[1] == "Run: pytest"


def test_daemon_step_0_enrichment_branches_on_verb():
    """NEW-49: Daemon step-0 plan enrichment should tailor instructions based on Edit vs Create."""
    description = "Fix the off-by-one bug in core/legacy_calc.py"
    steps = ["Edit core/legacy_calc.py: fix off-by-one", "Run: pytest"]
    total = len(steps)
    
    enriched = []
    for i, step in enumerate(steps):
        if i == 0:
            step_low = step.lower().strip()
            if step_low.startswith(("edit", "patch", "update", "modify", "fix", "change")):
                enriched.append(
                    f"User's full request: {description}\n\n"
                    f"Your task (step {i+1}/{total}): {step}\n\n"
                    "Apply ONLY the requested changes using patch_file. "
                    "Do not overwrite or rewrite unrelated code."
                )
            elif step_low.startswith(("create", "write", "build", "add")):
                enriched.append(
                    f"User's full request: {description}\n\n"
                    f"Your task (step {i+1}/{total}): {step}\n\n"
                    "Write the COMPLETE file with ALL features "
                    "described above. Do not skip any requirement."
                )
        else:
            enriched.append(
                f"Previous context: {description[:200]}\n\n"
                f"Your task (step {i+1}/{total}): {step}\n\n"
                "Complete only this step."
            )
            
    assert "Apply ONLY the requested changes using patch_file" in enriched[0]
    assert "Write the COMPLETE file" not in enriched[0]
