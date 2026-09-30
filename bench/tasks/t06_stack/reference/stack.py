class Stack:
    def __init__(self):
        self._a = []
    def push(self, x):
        self._a.append(x)
    def pop(self):
        if not self._a:
            raise IndexError('empty')
        return self._a.pop()
    def peek(self):
        if not self._a:
            raise IndexError('empty')
        return self._a[-1]
    def __len__(self):
        return len(self._a)
