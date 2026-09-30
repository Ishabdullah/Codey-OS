from slug import slugify

def test_basic():
    assert slugify('Hello World') == 'hello-world'
def test_punct():
    assert slugify('  A!!b??C  ') == 'a-b-c'
def test_empty():
    assert slugify('***') == ''
def test_digits():
    assert slugify('Room 101 / B') == 'room-101-b'
