import sys, os
sys.path.insert(0,os.path.dirname(os.path.realpath(__file__)))
from common import *
SNAP=B+"/snap"; setup(SNAP, B+"/ws/w6")
import tools.shell_tools as st
calls=[]
def fake_shell(command, yolo=False, **k):
    calls.append((command,yolo)); return "FAKE-RAN"
st.shell=fake_shell
from core.task_executor import TaskExecutor
for cmd in ["find . -maxdepth 0 -fprint core/zz_out.py","find . -delete","find /x -fprintf core/agent.py x","env cp x core/agent.py","env sh -c id","cat ~/.codeyOS/age.key","grep -rn . /data/data/com.termux/files/home/.ssh","echo hi > core/agent.py","pytest -p evilplugin","pytest --rootdir=/x -o addopts=--co","lsof -i","python3 x.py","python3 -m http.server"]:
    calls.clear()
    r=TaskExecutor._daemon_shell(None, cmd)
    print("##", repr(cmd), "->", "ADMITTED(fake shell called, class=%s)"%st.classify_shell_command(cmd) if calls else "BLOCKED", "|", r[:60].replace("\n"," "))
