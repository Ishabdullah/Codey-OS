from window import moving_sum

def test_basic():
    assert moving_sum([1, 2, 3, 4], 2) == [3, 5, 7]
def test_full():
    assert moving_sum([1, 2, 3], 3) == [6]
def test_too_big():
    assert moving_sum([1], 2) == []
