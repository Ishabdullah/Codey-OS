exec(open(__import__("os").path.join(__import__("os").path.dirname(__import__("os").path.realpath(__file__)),"h.py")).read())
os.environ["OPENROUTER_API_KEY"]="FAKE-OPENROUTER-KEY"; os.environ["AIGENTIK_INTERNAL_TOKEN"]="FAKE-AIGENTIK-TOKEN"; os.environ["CLOUDFLARE_TUNNEL_TOKEN"]="FAKE-CF-TOKEN"
install_fakes()
os.chdir(B+"/work")
from core import dashboard_data as dd
try:
    snap=dd.get_snapshot()
    print("snapshot ok", type(snap))
except Exception as e:
    print("snapshot exc", repr(e))
pm=dd._plugins
print("plugins:", {n:(p.status.value, p.execution_mode) for n,p in pm._plugins.items()})
for c in CALLS:
    name,a,k=c
    if name=="subprocess.Popen":
        env=k.get("env") or {}
        print("POPEN", a[0], "cwd=",k.get("cwd"), "env has FAKE keys:", sorted(x for x in env if x in ("OPENROUTER_API_KEY","AIGENTIK_INTERNAL_TOKEN","CLOUDFLARE_TUNNEL_TOKEN")))
    else:
        print(name, str(a)[:150])
