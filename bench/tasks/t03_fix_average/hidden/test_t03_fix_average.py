from mathutil import average

def test_empty():
    assert average([]) == 0.0
def test_float():
    assert average([1, 2]) == 1.5
def test_three():
    assert average([2, 4, 9]) == 5.0
