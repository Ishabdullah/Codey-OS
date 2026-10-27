import sys, json, hashlib
sys.path.insert(0,"/data/data/com.termux/files/home/Codey-OS/tools")
import wp21_census as w
HERE="/data/data/com.termux/files/usr/tmp/wp21_closure_next/supplementary/"
# usage: _build.py [OUT_PATH] [--reviewed-by VALUE]
# Always rebuilds from supplementary_dispositions.tsv.pre_review (round-0 draft, source of PM/SR evidence text),
# the frozen merged candidate (sibling evidence tails) and _verify13.json; applies round-1/2 changes, then optional reviewed_by.
OUT=HERE+"supplementary_dispositions.tsv"; RB=""
_a=sys.argv[1:]
if _a and not _a[0].startswith("--"): OUT=_a.pop(0)
if _a[:1]==["--reviewed-by"]: RB=_a[1]
import subprocess
FIRST_SEEN=subprocess.check_output(["git","-C","/data/data/com.termux/files/home/Codey-OS","rev-parse","941ec3fb"],text=True).strip()
assert FIRST_SEEN=="941ec3fb076d97e6e0998c0ea98eee086e6b0915"
old=w.parse_register(open(HERE+"supplementary_dispositions.tsv.pre_review").read())
pm_old=next(d for d in old if "plugin_manager" in d["key"])["evidence"]
sr_old=next(d for d in old if "skill_recombiner" in d["key"])
def sub(s,a,b):
    assert a in s,a; return s.replace(a,b)
PM=pm_old
PM=sub(PM,"(the neighbouring registered rows 1202 spec_from_file_location and 1205 module_from_spec only build the spec/module object; this line runs","(the neighbouring registered rows 1202 spec_from_file_location and 1205 module_from_spec, OPERATOR_BOOTSTRAP, only PREPARE the spec/module object and execute nothing; per NEW-1102 classification note this line is the executing step and is classed UNMEDIATED/MEDIUM, the siblings stay unchanged by coordinator decision; this line runs")
PM=sub(PM,"NOT gate_exec covered and no confirmation: PluginManager.load -> _load -> exec_module has no Action Gateway call; gating is structural only. Gate chain in _load before this line:","CLASS RATIONALE (independent review of 2026-10-27 + coordinator decision): not an operator-run installer/setup script (OPERATOR_BOOTSTRAP needs a written operator act); this is in-process execution step of production plugin activation reached prod-confirmless from the REPL, TaskExecutor/daemon and Core API paths below. NOT gate_exec covered and no confirmation: PluginManager.load -> _load -> exec_module has no Action Gateway call; the structural checks below are PARTIAL MITIGATION on WHERE the file is, explicitly NOT a gate and nothing constrains WHAT it contains. Severity MEDIUM (escalate to HIGH if a confirm-less write into ccos/plugins/** is shown to be ACT; write side: tools/file_tools.py classify_write_action treats ccos/plugins/ HIGH_IMPACT, core/protected_paths.py F3_PLUGIN_ROOT, shell G15e scan). Finding NEW-1102 (execution trust boundary); NEW-1101 (scanner gap). Gate chain in _load before this line:")
PM=sub(PM,"Trust therefore rests entirely on same-UID filesystem integrity of ccos/plugins/** (same-UID writer/F2 and the unvalidated-registry class are retained as NEW-1086/NEW-1069).","Trust therefore rests entirely on same-UID filesystem integrity of ccos/plugins/** (NEW-1102; same-UID writer/F2 and the unvalidated-registry class are retained as NEW-1086/NEW-1069; NEW-953 is partial registration after spawn and is related only, not the boundary).")
PM=sub(PM,"Related rows: PluginManager._load spec_from_file_location/module_from_spec (OPERATOR_BOOTSTRAP, C6_FRESH), ProcessSupervisor external spawn rows. NEW-1101 decision","Related rows: PluginManager._load spec_from_file_location/module_from_spec (OPERATOR_BOOTSTRAP, C6_FRESH, unchanged), ProcessSupervisor external spawn rows. NEW-1101 decision")
SR=sr_old["evidence"]
SR=sub(SR,"NEW-1101 decision (Ish 2026-10-27)","Review note: the test's discriminator is the marker-file assertion (the skill writes a marker on import; removing gate_exec would create it); mutation run not executed. NEW-1101 decision (Ish 2026-10-27)")
SR=sub(SR,"skill_recombiner.py:430/441/452 emit exec_module into GENERATED test.py source; ccos/core/capability_optimizer.py:357 builds a `python -c` string run through self._sandbox.run_python.","skill_recombiner.py:430/441/452 emit exec_module into GENERATED test.py source (NEW-976); ccos/core/capability_optimizer.py:356-357 builds a `python -c` string run through self._sandbox.run_python (NEW-1099).")
rows=[
 dict(key="ccos/core/plugin_manager.py::PluginManager._load::*.exec_module::1", **{"class":"UNMEDIATED"},
      mediator="", evidence=PM, reach="prod-confirmless", severity="MEDIUM",
      finding="NEW-1102;NEW-1101;NEW-1086;NEW-1069",
      decided_by="/root/project_architect:SUPP_NEW1101_R2", reviewed_by="", first_seen_rev="770dc663", count=""),
 dict(key=sr_old["key"], **{"class":"GATED"}, mediator="gate_exec", evidence=SR, reach="dormant", severity="",
      finding="NEW-1101;NEW-976;NEW-1086", decided_by="/root/project_architect:SUPP_NEW1101",
      reviewed_by="", first_seen_rev="770dc663", count=""),
]
ver=json.load(open(HERE+"_verify13.json"))
sib={}
for d in w.parse_register(open("/data/data/com.termux/files/usr/tmp/wp21_closure_next/merged_candidate/dispositions_candidate.tsv").read()):
    sib[d["key"]]=d
for p,line,callee,qn,seg in ver:
    assert callee=="*.exec_module" and qn=="<module>"
    s=sib[f"{p}::<module>::importlib.util.module_from_spec::1"]
    tail=s["evidence"].split(" | ",1)[1]
    ev=(f"770dc663:{p}:{line} <module> *.exec_module: {seg} | THE EXECUTION STEP of this script's fixed _pathutil bootstrap (sibling rows spec_from_file_location/module_from_spec only prepare it; unchanged). "
        "The path is the fixed repo-relative ccos/plugins/_pathutil.py (Path(__file__).resolve().parent.parent.parent / '_pathutil.py'), not user-controlled; the helper only walks up to the repo root and edits sys.path (file read in frozen tree). Reached only when an operator runs this test script directly (python/pytest); not imported by product code. "
        "Added per NEW-1101 (scanner DYN_EXACT lacks exec_module); coordinator decision 2026-10-27 and independent review other_dynamic_sites. "+tail)
    rows.append(dict(key=f"{p}::<module>::*.exec_module::1", **{"class":"OPERATOR_SCRIPT_RUNNABLE"},
        mediator=s["mediator"], evidence=ev, reach="operator-only", severity="", finding="NEW-1101;NEW-1069",
        decided_by="/root/project_architect:SUPP_NEW1101_R2", reviewed_by="", first_seen_rev="770dc663", count=""))
# round-2: agent-shell ACT statement in operator-script evidence (reach vocabulary is closed, so reach stays operator-only);
# first_seen_rev 941ec3fb for all rows (verified via git show <sha>:<path> containing exec_module( for all 15 files).
for d in rows:
    d["first_seen_rev"]=FIRST_SEEN
    if d["class"]=="OPERATOR_SCRIPT_RUNNABLE":
        a_="Python script/import invocation can execute it under F2/F3 named-script limits;"
        assert a_ in d["evidence"]
        d["evidence"]=d["evidence"].replace(a_,"Reach is operator-only AND agent-shell ACT via python script (NEW-904 ceiling): "+a_.replace("Python","python"),1)
# final step (optional): reviewed_by after independent review rounds 1-3
if RB:
    for d in rows: d["reviewed_by"]=RB
out=w.render_register(rows)
open(OUT,"w").write(out)
for d in rows:
    assert d["class"] in w.CLASSES and d["reach"] in w.REACH_VALUES and d["severity"] in w.SEVERITIES
    assert d["key"].count("::")==3 and d["evidence"].strip()
    if d["class"]=="GATED": assert all(g in w.GATE_NAMES for g in w._gates_of(d["mediator"]))
    if d["class"]=="UNMEDIATED": assert d["finding"] and d["severity"]
back=w.parse_register(out); assert len(back)==15 and w.render_register(back)==out
assert all(b["reviewed_by"]==RB for b in back)
print("ok",OUT,len(out),hashlib.sha256(out.encode()).hexdigest())
