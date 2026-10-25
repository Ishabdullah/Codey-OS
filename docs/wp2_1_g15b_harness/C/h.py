import os as _os, sys as _sys
_sys.path.insert(0,_os.path.dirname(_os.path.dirname(_os.path.realpath(__file__))))
import g15z_guard as _gz
import os, sys, json
B=_gz.work_root("C")
SNAP=B+"/snap"
for k in list(os.environ):
    if k.lower() in ("http_proxy","https_proxy","all_proxy","no_proxy") : del os.environ[k]
os.environ["HOME"]=B+"/home"
os.environ["CODEY_STATE_DIR"]=B+"/state"
os.environ["CODEY_ACTION_GATEWAY_AUDIT"]=B+"/state/audit.jsonl"
sys.path.insert(0,SNAP)
OUT=_gz.tsv_path("C")
HDR=["probe_id","setup_entrypoint","observed_gate_authority_verbatim","expected_by_policy","verdict","severity","reachability_note","evidence_path"]
def _c(s):
    return str(s).replace("\t"," ").replace("\r"," ").replace("\n"," \\n ")
def rec(pid,setup,obs,exp,verdict,sev,reach,ev):
    new=not os.path.exists(OUT)
    with open(OUT,"a") as f:
        if new: f.write("\t".join(HDR)+"\n")
        f.write("\t".join(_c(x) for x in (pid,setup,obs,exp,verdict,sev,reach,ev))+"\n"); f.flush()
    print(pid,verdict,sev,"|",str(obs)[:200])
# recording fakes
CALLS=[]
import subprocess, socket, urllib.request, http.client
def _fake_run(*a,**k):
    CALLS.append(("subprocess.run",a,k))
    class R: returncode=0; stdout="FAKE-OUT"; stderr=""
    return R()
class _FakePopen:
    def __init__(self,*a,**k):
        CALLS.append(("subprocess.Popen",a,k)); raise OSError("recording fake: Popen blocked")
def _fake_kill(*a,**k):
    CALLS.append(("os.kill",a,k))
def _fake_killpg(*a,**k):
    CALLS.append(("os.killpg",a,k))
def _fake_urlopen(*a,**k):
    CALLS.append(("urlopen",a,k)); raise OSError("recording fake: network blocked")
def _fake_conn(self,*a,**k):
    CALLS.append(("socket.connect",a,k)); raise OSError("recording fake: socket blocked")
def _fake_bind(self,*a,**k):
    CALLS.append(('socket.bind',a,k)); raise OSError('recording fake: bind blocked')
def install_fakes():
    socket.socket.bind=_fake_bind
    subprocess.run=_fake_run; subprocess.Popen=_FakePopen
    subprocess.call=_fake_run; subprocess.check_output=_fake_run
    os.kill=_fake_kill; os.killpg=_fake_killpg
    urllib.request.urlopen=_fake_urlopen
    socket.socket.connect=_fake_conn
    http.client.HTTPConnection.connect=lambda self:(_ for _ in ()).throw(OSError("blocked"))
