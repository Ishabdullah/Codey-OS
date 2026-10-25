import sys, os, json
mod, home, state, ws, code_dir, unset_state = sys.argv[1:7]
for k in list(os.environ):
    if k.lower().endswith("_proxy"): os.environ.pop(k)
os.environ["HOME"]=home
if unset_state=="1": os.environ.pop("CODEY_STATE_DIR",None)
else: os.environ["CODEY_STATE_DIR"]=state
os.environ["CODEY_ACTION_GATEWAY_AUDIT"]=state+"/audit.jsonl" if unset_state!="1" else home+"/.codeyOS/audit.jsonl"
os.environ.pop("CODEY_ACTION_GATEWAY_AUDIT") if unset_state=="1" else None
os.chdir(ws); sys.path.insert(0, code_dir)
att=[]
import subprocess, socket, threading
def mk(name):
    def f(*a, **k):
        att.append(name+":"+repr(a)[:80]); raise RuntimeError("FAKE-"+name)
    return f
subprocess.Popen.__init__ = (lambda self,*a,**k: (att.append("Popen:"+repr(a)[:100]), (_ for _ in ()).throw(RuntimeError("FAKE-Popen")))[1])
os.system=mk("os.system"); os.kill=mk("os.kill"); os.killpg=mk("os.killpg")
for n in ("execv","execve","execvp","execl","execlp","fork","forkpty","spawnv","popen"):
    if hasattr(os,n): setattr(os,n,mk("os."+n))
socket.socket.connect=mk("socket.connect"); socket.socket.bind=mk("socket.bind"); socket.socket.connect_ex=mk("socket.connect_ex")
_ts=threading.Thread.start
def ts(self,*a,**k): att.append("Thread.start:"+str(self.name)); return _ts(self,*a,**k)
threading.Thread.start=ts
err=None
try:
    import importlib; importlib.import_module(mod)
except BaseException as e:
    err=type(e).__name__+": "+str(e)[:120]
print("IMPJSON"+json.dumps({"mod":mod,"err":err,"att":att}))
sys.stdout.flush(); os._exit(0)
