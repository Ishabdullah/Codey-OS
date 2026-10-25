import os, sys
exec(open(os.path.join(os.path.dirname(os.path.realpath(__file__)),"rows1.py")).read())
exec(open(os.path.join(os.path.dirname(os.path.realpath(__file__)),"rows2.py")).read())
import csv
if os.path.exists(OUT): os.remove(OUT)
for r in R:
    assert len(r)==8, r[0]
    rec(*r)
print(len(R),"rows")
