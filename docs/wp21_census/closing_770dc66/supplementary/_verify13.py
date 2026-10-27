import ast,sys,json
F="/data/data/com.termux/files/usr/tmp/wp21_closure_next/frozen_source_770dc66"
src=open(F+"/tools/wp21_census.py").read()
t=ast.parse(src); ns={"ast":ast,"Dict":dict,"List":list}
for n in t.body:
    if isinstance(n,ast.FunctionDef) and n.name in("_resolve","_collect_aliases"):
        exec(compile(ast.Module([n],[]),"x","exec"),ns)
files="coding/agent coding/error_recovery coding/finetune coding/git_integration coding/peer_escalation coding/static_analysis coding/task_queue crm/core_query device/bridge research/rag_retrieval system/daemon_control system/observability system/thermal_monitor".split()
res=[]
for f in files:
    p=f"ccos/plugins/{f}/test.py"; s=open(F+"/"+p).read(); tr=ast.parse(s); al=ns["_collect_aliases"](tr)
    # enclosing function map
    par={}
    for n in ast.walk(tr):
        for c in ast.iter_child_nodes(n): par[c]=n
    hits=[]
    for n in ast.walk(tr):
        if isinstance(n,ast.Call):
            c=ns["_resolve"](n.func,al)
            if c.endswith("exec_module") or "exec_module" in c:
                q=[]; x=n
                while x in par:
                    x=par[x]
                    if isinstance(x,(ast.FunctionDef,ast.AsyncFunctionDef,ast.ClassDef)): q.append(x.name)
                hits.append((n.lineno,c,".".join(reversed(q)) or "<module>",ast.get_source_segment(s,n)))
    assert len(hits)==1,(p,hits)
    res.append((p,)+hits[0])
    print(p,*hits[0])
json.dump(res,open("/data/data/com.termux/files/usr/tmp/wp21_closure_next/supplementary/_verify13.json","w"))
