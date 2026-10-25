import os as _os, sys as _sys
_sys.path.insert(0,_os.path.dirname(_os.path.dirname(_os.path.dirname(_os.path.realpath(__file__)))))
import g15z_guard as _gz
import os, sys, json
B=_gz.work_root("B")
def setup(code_dir, ws, state=True, home=None):
    for k in list(os.environ):
        if k.lower().endswith("_proxy") or k.lower()=="all_proxy": os.environ.pop(k)
    os.environ["HOME"]= home or B+"/home"
    if state:
        os.environ["CODEY_STATE_DIR"]=B+"/state"
    else:
        os.environ.pop("CODEY_STATE_DIR",None)
    os.environ["CODEY_ACTION_GATEWAY_AUDIT"]=B+"/state/audit.jsonl"
    os.makedirs(ws,exist_ok=True)
    os.chdir(ws)
    sys.path.insert(0, code_dir)
def row(pid, setup_s, obs, exp, verdict, sev, reach, ev=""):
    clean=lambda s: str(s).replace("\t"," ").replace("\n","\\n")
    with open(_gz.tsv_path("B"),"a") as f:
        f.write("\t".join(clean(x) for x in (pid,setup_s,obs,exp,verdict,sev,reach,ev))+"\n")
