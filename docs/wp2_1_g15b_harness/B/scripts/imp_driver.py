import os as _os, sys as _sys
_sys.path.insert(0,_os.path.dirname(_os.path.dirname(_os.path.dirname(_os.path.realpath(__file__)))))
import g15z_guard as _gz
import sys, os, json, subprocess, shutil, time
B=_gz.work_root("B"); SNAP=B+"/snap"
unset=sys.argv[1]  # "0" or "1"
mods=[]
for root in ("core","tools","utils","prompts","ccos","bench","pipeline","telemetry","codey_estimator","restoricon_core"):
    for dp,dn,fn in os.walk(SNAP+"/"+root):
        dn[:]=[d for d in dn if d not in ("__pycache__","tests","node_modules")]
        for f in fn:
            if f.endswith(".py") and not f.startswith("test_") and f!="conftest.py":
                rel=os.path.relpath(dp+"/"+f,SNAP)[:-3].replace("/",".")
                if rel.endswith(".__init__"): rel=rel[:-9]
                mods.append(rel)
mods.append("main")
mods=sorted(set(mods))
def walk(d):
    out={}
    for dp,dn,fn in os.walk(d):
        for f in fn+dn:
            p=dp+"/"+f
            try: out[p]=os.lstat(p).st_mtime_ns
            except OSError: pass
    return out
snap_before=walk(SNAP)
out=(_os.makedirs(B+"/logs",exist_ok=True), open(B+"/logs/imp_%s.jsonl"%unset,"w"))[1]
for i,m in enumerate(mods):
    base=B+"/imp/%s_%03d"%(unset,i); shutil.rmtree(base,ignore_errors=True)
    for d in ("home","state","ws"): os.makedirs(base+"/"+d)
    try:
        r=subprocess.run(["python3","-B","-I",_os.path.join(_os.path.dirname(_os.path.realpath(__file__)),"imp_child.py"),m,base+"/home",base+"/state",base+"/ws",SNAP,unset],capture_output=True,text=True,timeout=60,stdin=subprocess.DEVNULL)
        line=[l for l in r.stdout.splitlines() if l.startswith("IMPJSON")]
        info=json.loads(line[0][7:]) if line else {"mod":m,"err":"NOOUT rc=%s %s"%(r.returncode,r.stderr[-150:]),"att":[]}
    except subprocess.TimeoutExpired:
        info={"mod":m,"err":"TIMEOUT","att":[]}
    created=[]
    for d in ("home","state","ws"):
        for dp,dn,fn in os.walk(base+"/"+d):
            for f in fn+dn: created.append(os.path.relpath(dp+"/"+f,base))
    info["created"]=sorted(created)
    out.write(json.dumps(info)+"\n"); out.flush()
snap_after=walk(SNAP)
chg=[p for p in snap_after if p not in snap_before or snap_before[p]!=snap_after[p]]
gone=[p for p in snap_before if p not in snap_after]
open(B+"/logs/imp_%s_snapchg.json"%unset,"w").write(json.dumps({"changed_or_new":chg,"removed":gone}))
print("modules:",len(mods),"snap changes:",len(chg))
