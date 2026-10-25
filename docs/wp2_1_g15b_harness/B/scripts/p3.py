import sys, os, shutil
sys.path.insert(0,os.path.dirname(os.path.realpath(__file__)))
from common import *
# fresh disposable copy of the bench tree (not the repo, not the earlier copy)
D=B+"/benchcopy"; shutil.rmtree(D, ignore_errors=True)
shutil.copytree(B+"/snap/bench", D+"/bench")
setup(D, D)
from pathlib import Path
from bench import lock
print("baseline verify_lock:", lock.verify_lock())
t=D+"/bench/tasks/t01_slugify"
# A: hidden-test fixture / prompt tamper detected?
open(t+"/prompt.txt","a").write("\nextra\n"); print("A after prompt.txt edit verify_lock:", lock.verify_lock())
# B: re-lock (ACT shell: python3 -c 'from bench.lock import write_lock; write_lock()')
lock.write_lock(); print("B after write_lock() verify_lock:", lock.verify_lock())
# C: edit evaluator code (not under tasks/): verify.py, gate.py, lock.py
v=D+"/bench/verify.py"; s=open(v).read(); s=s.replace("return r.returncode == 0","return True"); open(v,"w").write(s)
g=D+"/bench/gate.py"; s=open(g).read(); s=s.replace("DEFAULTS = {\"min_pairs\": 30","DEFAULTS = {\"min_pairs\": 1"); open(g,"w").write(s)
l=D+"/bench/lock.py"; s=open(l).read(); s=s.replace("    return lock.read_text().strip() == suite_hash(tasks_dir)","    return True"); open(l,"w").write(s)
import importlib; importlib.reload(lock)
print("C after editing verify.py/gate.py/lock.py: verify_lock (reloaded):", lock.verify_lock(), "| suite hash unchanged:", lock.suite_hash()==open(D+"/bench/suite.lock").read().strip() or "changed(expected since B relock)")
# D: sourceless .pyc / __pycache__ under tasks are excluded from the hash
h0=lock.suite_hash()
open(t+"/starter/evil.pyc","wb").write(b"\x00junk"); os.makedirs(t+"/starter/__pycache__",exist_ok=True); open(t+"/starter/__pycache__/x.cpython-314.pyc","wb").write(b"z")
print("D hash unchanged after planting starter/evil.pyc and __pycache__/x.pyc:", lock.suite_hash()==h0)
import bench.suite as S
from bench import runner
ws=Path(B+"/benchws"); shutil.rmtree(ws,ignore_errors=True); shutil.copytree(t+"/starter", ws)
print("D planted pyc copied into agent workspace by runner copytree:", sorted(p.name for p in ws.rglob("*") if p.suffix==".pyc"))
