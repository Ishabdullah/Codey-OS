import sys
import os; sys.path.insert(0,os.path.dirname(os.path.realpath(__file__)))
from common import row
a=sys.argv[1:]
assert len(a)==8, len(a)
row(*a)
