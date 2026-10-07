"""Fixture stand-in for core/context.py -- deliberately IMPORTED by
prompts/layered_prompt.py but never actually CALLED. This is the
discriminating case for the 1c/6c bugfix: the old import-graph-BFS
check would have scored this as reachable (full credit); the new
call-site check must score it as a miss."""


def build_context():
    return "context"
