import sys, os, shutil
sys.path.insert(0,os.path.dirname(os.path.realpath(__file__)))
from common import *
D=B+"/benchcopy2"; shutil.rmtree(D, ignore_errors=True)
shutil.copytree(B+"/snap/bench", D+"/bench")
setup(D, D)
from pathlib import Path
from bench import lock, verify, suite
h0=lock.suite_hash(); print("lock ok:", lock.verify_lock())
open(D+"/bench/verify.py","a").write("\n# tamper\n")
s=open(D+"/bench/gate.py").read().replace('"min_pairs": 30','"min_pairs": 1').replace('"max_regressions": 0','"max_regressions": 99'); open(D+"/bench/gate.py","w").write(s)
s=open(D+"/bench/compare.py").read(); open(D+"/bench/compare.py","w").write(s+"\n# tamper\n")
print("E after editing verify.py/gate.py/compare.py: verify_lock:", lock.verify_lock(), " hash identical:", lock.suite_hash()==h0)
from bench import gate
print("E gate.DEFAULTS now:", gate.DEFAULTS)
# F: agent-written conftest.py in the graded workspace
t=[x for x in suite.load_tasks(Path(D+"/bench/tasks")) if x.id=="t01_slugify"][0]
ws=Path(B+"/benchws2"); shutil.rmtree(ws,ignore_errors=True); shutil.copytree(t.starter, ws)
print("F control (null agent, starter unsolved) grade:", verify.grade(t, ws))
(ws/"conftest.py").write_text('''import pytest
@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    outcome = yield
    rep = outcome.get_result()
    if rep.when == "call" and rep.failed:
        rep.outcome = "passed"; rep.longrepr = None
''')
print("F with agent-written workspace conftest.py (starter still unsolved) grade:", verify.grade(t, ws))
