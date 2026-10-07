"""Fixture stand-in for core/trajectory.py -- has the full-fidelity
recording shape (_bounded/_budgeted, used by both instrument_* functions)
so 1b and 6a both score full credit."""


def _bounded(x):
    return x


def _budgeted(x):
    return x


def instrument_run_agent():
    return _budgeted(1)


def instrument_execute_tool():
    return _budgeted(1)
