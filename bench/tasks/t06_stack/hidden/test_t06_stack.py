import pytest
from stack import Stack

def test_lifo():
    s = Stack(); s.push(1); s.push(2)
    assert s.pop() == 2 and s.peek() == 1 and len(s) == 1
def test_empty_pop():
    with pytest.raises(IndexError):
        Stack().pop()
def test_empty_peek():
    with pytest.raises(IndexError):
        Stack().peek()
