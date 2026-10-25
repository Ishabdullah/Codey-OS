import sys, os, json
sys.path.insert(0,os.path.dirname(os.path.realpath(__file__)))
from common import *
CD=B+"/home/Codey-OS"
setup(CD, CD)
os.environ["CODEY_ACTION_GATEWAY_AUDIT"]=B+"/state/audit_p2.jsonl"
if os.path.exists(os.environ["CODEY_ACTION_GATEWAY_AUDIT"]): os.remove(os.environ["CODEY_ACTION_GATEWAY_AUDIT"])
from utils import config
assert str(config.CODE_DIR)==CD, config.CODE_DIR
config.AGENT_CONFIG["confirm_write"]=False; config.AGENT_CONFIG["confirm_shell"]=False
from tools import file_tools as ft
mf=[p for p in __import__("glob").glob(CD+"/ccos/plugins/*/*/manifest.json")][:1]
targets=["core/agent.py","tools/shell_tools.py","utils/config.py","prompts/system_prompt.py","bench/gate.py","bench/lock.py","bench/verify.py","bench/tasks/t01_slugify/hidden/test_t01_slugify.py",
 "ccos/plugins/crm/__init__.py"]+[os.path.relpath(m,CD) for m in mf]+[
 "bench/suite.lock","bench/tasks/t01_slugify/prompt.txt","bench/tasks/t01_slugify/reference/slug.py","bench/scorecard_manual.json","bench/README.md","tools/setup_skills.sh",
 "main.py","codey-start","codey-stop","codeyOS","codeydOS","codey","lib/service_manager.sh","lib/service_lifecycle.sh","install.sh","setup.sh",
 "ccos/core/plugin_manager.py","ccos/core/capability_registry.py","restoricon_core/authority.py","telemetry/store.py","pipeline/run.py",
 "conftest.py","pytest.ini",".github/workflows/tests.yml",".qwen/settings.json",".claude/agents/code-reviewer.md","CLAUDE.md","AGENTS.md","requirements.txt","config.json.example","ccos/data/projects.json",
 ".codeyignore","CODEY.md","codey_estimator/__init__.py"]
res=[]
for t in targets:
    if not os.path.exists(CD+"/"+t) and t not in (".codeyignore","CODEY.md"):
        print("MISSING",t); continue
    cls=ft.classify_write_action(t)
    r=ft.tool_append_file(t,"\n# g15b-probe\n")
    print("##",t,cls,"=>",r[:80].replace("\n"," "))
