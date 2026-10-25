exec(open(__import__("os").path.join(__import__("os").path.dirname(__import__("os").path.realpath(__file__)),"h.py")).read())
import subprocess as sp, shutil, tempfile, time, asyncio
os.chdir(B+"/work")
# (a) real harmless python -Bc acceptance
r=sp.run(["python3","-Bc","print(40+2)"],capture_output=True,text=True)
print("A python3 -Bc:",r.stdout.strip(),r.returncode)
r=sp.run(["python3","-ic","print(41+1)"],capture_output=True,text=True,input="")
print("A2 python3 -ic:",r.stdout.strip(),r.returncode)
# (b) bench lock
from bench import lock
td=B+"/work/benchcopy"; shutil.rmtree(td,ignore_errors=True); shutil.copytree(SNAP+"/bench/tasks",td+"/tasks"); shutil.copy(SNAP+"/bench/suite.lock",td+"/suite.lock")
print("B0 verify baseline copy:", lock.verify_lock(td+"/tasks" and __import__("pathlib").Path(td+"/tasks"), __import__("pathlib").Path(td+"/suite.lock")))
from pathlib import Path
files=[p for p in Path(td+"/tasks").rglob("*") if p.is_file() and "hidden" in p.parts and p.suffix==".py"]
print("hidden test files:",len(files), files[0] if files else None)
f=files[0]; f.write_text(f.read_text()+"\n# tamper\n")
print("B1 verify after hidden tamper:", lock.verify_lock(Path(td+"/tasks"),Path(td+"/suite.lock")))
lock.write_lock(Path(td+"/tasks"),Path(td+"/suite.lock"))
print("B2 verify after tamper + write_lock (agent-callable, lock file ACT-writable):", lock.verify_lock(Path(td+"/tasks"),Path(td+"/suite.lock")))
# which bench files does the lock cover
cov=set(str(p.relative_to(SNAP+"/bench")) for p in Path(SNAP+"/bench/tasks").rglob("*") if p.is_file())
allb=set(str(p.relative_to(SNAP+"/bench")) for p in Path(SNAP+"/bench").rglob("*") if p.is_file() and "__pycache__" not in p.parts)
print("B3 bench files:",len(allb),"covered by suite_hash:",len(cov),"uncovered non-task:",sorted(allb-cov))
# classification of write targets
from tools.file_tools import classify_write_action as cw
for rel in ["bench/suite.lock","bench/verify.py","bench/gate.py","bench/runner.py","bench/scorecard_history.jsonl","bench/scorecard_manual.json","config.json","ccos/plugins/voice/aigentik/manifest.json","ccos/data/capabilities.json","main.py","codeyOS","codey-start","lib/service_lifecycle.sh","install.sh",".codeyignore","tools/setup_skills.sh","CODEY.md","requirements.txt","core/data/x.json"]:
    print("W",rel, cw(SNAP+"/"+rel))
