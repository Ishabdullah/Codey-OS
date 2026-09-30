from dd import dedupe

def test_ints():
    assert dedupe([3, 1, 3, 2, 1]) == [3, 1, 2]
def test_unhashable():
    assert dedupe([[1], [2], [1]]) == [[1], [2]]
def test_empty():
    assert dedupe([]) == []
