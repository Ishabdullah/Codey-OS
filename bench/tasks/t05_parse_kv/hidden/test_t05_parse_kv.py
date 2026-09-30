from kv import parse_kv

def test_basic():
    assert parse_kv('a=1;b=two;c=') == {'a': '1', 'b': 'two', 'c': ''}
def test_ws():
    assert parse_kv(' a = 1 ;; b=x=y ') == {'a': '1', 'b': 'x=y'}
def test_skip():
    assert parse_kv('novalue;k=v') == {'k': 'v'}
