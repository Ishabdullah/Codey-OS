from fb import fizzbuzz

def test_15():
    r = fizzbuzz(15)
    assert r[2] == 'Fizz' and r[4] == 'Buzz' and r[14] == 'FizzBuzz' and r[0] == '1'
def test_len():
    assert len(fizzbuzz(7)) == 7
def test_zero():
    assert fizzbuzz(0) == []
