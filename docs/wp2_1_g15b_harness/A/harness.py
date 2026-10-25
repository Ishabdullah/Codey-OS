# Hunter A harness: classifier + recording-fake execution. Never executes anything.
import os, sys, json, subprocess, socket
import g15z_guard as _gz
A = _gz.work_root("A")
SNAP = A + "/snap"
sys.path[:] = [SNAP] + [p for p in sys.path if "site-packages" not in p or True][:0] + sys.path[1:]
sys.path.insert(0, SNAP)
os.chdir(A + "/ws")

CALLS = []
class _Res:
    def __init__(s): s.stdout="REC"; s.stderr=""; s.returncode=0
def rec_run(args, *a, **k):
    CALLS.append(("run", list(args) if not isinstance(args,str) else args, {kk:(vv if kk!="env" else "ENV-ISOLATED") for kk,vv in k.items() if kk in("env","timeout")}))
    return _Res()
def rec_popen(*a, **k):
    CALLS.append(("Popen", a[:1], {})); raise RuntimeError("recorder: Popen blocked")
def _blk(name):
    def f(*a, **k):
        CALLS.append((name, a[:2], {})); raise RuntimeError("recorder: %s blocked" % name)
    return f
subprocess.run = rec_run
subprocess.Popen = rec_popen
subprocess.call = _blk("call"); subprocess.check_output=_blk("check_output"); subprocess.check_call=_blk("check_call")
for n in ("system","kill","killpg","execv","execve","execvp","execvpe","execl","execle","execlp","spawnv","spawnvp","fork","popen"):
    if hasattr(os, n): setattr(os, n, _blk("os."+n))
socket.socket.connect = _blk("socket.connect")
socket.create_connection = _blk("socket.create_connection")

from tools import shell_tools as st
from core import action_gateway as ag
from utils import config
import core.task_executor as te

PROMPTS = []
def rec_confirm(msg, *a, **k):
    PROMPTS.append(msg); return False
st.ask_confirm = rec_confirm
st.warning = lambda *a, **k: None

def classify(cmd): return st.classify_shell_command(cmd)

def run_confirmless(cmd):
    """shell() as under --yolo/--fix/--tdd/one-shot: confirm_shell False."""
    config.AGENT_CONFIG["confirm_shell"] = False
    CALLS.clear(); PROMPTS.clear()
    out = st.shell(cmd)
    return list(CALLS), out, bool(PROMPTS)

def run_daemon(cmd):
    config.AGENT_CONFIG["confirm_shell"] = False
    CALLS.clear(); PROMPTS.clear()
    out = te.TaskExecutor._daemon_shell(None, cmd)
    return list(CALLS), out, bool(PROMPTS)
