import pytest
from roman import to_roman

def test_small():
    assert to_roman(4) == 'IV' and to_roman(9) == 'IX'
def test_big():
    assert to_roman(1994) == 'MCMXCIV' and to_roman(3999) == 'MMMCMXCIX'
def test_range():
    for bad in (0, 4000, -1):
        with pytest.raises(ValueError):
            to_roman(bad)
