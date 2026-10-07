"""Fixture stand-in for core/embeddings.py -- exists, but is never
imported by prompts/layered_prompt.py at all (not even an unused
import). Third discriminating case for 1c/6c: "not imported" vs.
context.py's "imported but not called"."""


def get_embedding_store():
    return None
