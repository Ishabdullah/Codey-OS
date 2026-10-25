import os as _os, sys as _sys
_HARNESS=_os.path.dirname(_os.path.dirname(_os.path.realpath(__file__)))
_sys.path.insert(0,_HARNESS)
import g15z_guard as _gz
import shlex, shutil, json, os
exec(open(_os.path.join(_HARNESS,'A','harness.py')).read())
exec(open(_os.path.join(_HARNESS,'A','probes.py')).read())
OUT=_gz.tsv_path("A")
os.makedirs(A+"/out",exist_ok=True)
RAW=A+"/out/raw.jsonl"
EVID="docs/wp2_1_g15b_hunter_A.md + <G15Z_OUT>/A/out/raw.jsonl (docs/wp2_1_g15b_harness/A/{probes,run_probes}.py)"
real_path=os.environ.get("REALPATH","")
def present(cmd):
    try: p=shlex.split(cmd)
    except ValueError: p=cmd.split()
    if not p: return "n/a"
    a0=p[0]
    if a0.startswith("./"): return "staged"
    if "/" in a0: return "yes" if os.path.exists(a0) else "no"
    for d in real_path.split(":")+["/system/bin","/system/xbin"]:
        if d and os.path.exists(os.path.join(d,a0)): return "yes"
    return "no"
hdr="probe_id\tinput\tclassifier_output_and_authority\texpected_by_policy\tverdict\tseverity\treachability_note\tevidence\n"
f=open(OUT,"w"); f.write(hdr); f.flush()
raw=open(RAW,"w")
def esc(s): return s.replace("\\","\\\\").replace("\t","\\t").replace("\n","\\n").replace("\r","\\r").replace("\x00","\\x00").replace("\u00a0","\\u00a0")
for (pid,mode,cmd,exp,eff,sev,note) in P:
    try:
        cls=classify(cmd)
    except Exception as e:
        cls="EXC:"+repr(e)
    pres=present(cmd)
    try:
        calls,out,prompted=(run_daemon if mode=="D" else run_confirmless)(cmd)
        err=None
    except Exception as e:
        calls,out,prompted,err=[],"",False,repr(e)
    if err: res="PROBE-ERROR "+err; outcome="error"
    elif calls: res="EXECUTED-SILENT(recorder) argv=%s"%json.dumps([c[1] for c in calls if c[0]=="run"] or calls); outcome="exec"
    elif prompted: res="PROMPTED(declined by recorder; no exec)"; outcome="prompt"
    else: res="NOT-EXECUTED out=%s"%out[:120].replace("\n"," "); outcome="refused"
    # verdict
    if outcome=="error": verdict="INCONCLUSIVE"; fsev=""
    elif outcome=="exec":
        if eff is True: verdict="BYPASS"; fsev=sev
        elif eff is None: verdict="INCONCLUSIVE" if ("refuse" in exp.lower() or "HIGH" in exp) else "OK"; fsev=""
        else: verdict="OK"; fsev=""
    else: verdict="OK"; fsev=""
    rn=note
    if pid.startswith("D") and pid[1:].isdigit() and int(pid[1:])<=12 and outcome=="exec":
        verdict="BYPASS"; fsev="LOW"; rn="allowlist admitted a command that is not on the allowlist (startswith without word boundary, NEW-1007); effect depends on binary; present=%s"%pres
    if pid=="N05": fsev="LOW"; rn+="; audit-label only (READ vs ACT behave identically in shell())"
    if pid in("G01","G02","G05"): rn+="; DOCUMENTED residual in _shell_command_targets_git_metadata docstring (script-embedded/attached-option writes not inspected)"
    if pid=="G14": verdict="INCONCLUSIVE"; rn="harness artifact: CODE_DIR is the snapshot, not the real repo, so real Codey-OS/.git is outside scan roots here; in production CODE_DIR=repo and G07-style paths are refused (see G10)"
    if pid=="G08": verdict="OK"; rn="case-sensitive FS: .GIT is not the git dir"
    if verdict=="BYPASS" and pres=="no": fsev="LOW"; rn+="; binary ABSENT on this device (latent: classifier gap only)"
    if verdict=="BYPASS" and mode=="C": rn+="; reach: "+CF
    if verdict=="BYPASS" and mode=="D": rn+="; reach: daemon (TaskExecutor._daemon_shell, shell(yolo=True))"
    if outcome=="exec" and mode=="C" and cls=="ACT" and eff is True: pass
    row=[pid,esc(cmd),"classify=%s; mode=%s; binary_present=%s; %s"%(cls,mode,pres,esc(res)),exp,verdict,fsev,rn,EVID]
    f.write("\t".join(row)+"\n"); f.flush()
    raw.write(json.dumps(dict(id=pid,cmd=cmd,cls=cls,mode=mode,calls=[list(map(str,c)) for c in calls],out=out[:300],prompted=prompted,err=err,present=pres))+"\n"); raw.flush()
f.close()
print("done",len(P))
