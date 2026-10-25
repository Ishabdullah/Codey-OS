exec(open(__import__("os").path.join(__import__("os").path.dirname(__import__("os").path.realpath(__file__)),"h.py")).read())
os.chdir(B+"/work"); install_fakes()
from utils import config
import core.agent as A
seen={}
def fake_run_agent(user_message=None,history=None,yolo=False,use_plan=False,no_plan=False,_in_subtask=False,_plan_rag_block="",**k):
    seen.update(dict(confirm_shell=config.AGENT_CONFIG.get("confirm_shell"),confirm_write=config.AGENT_CONFIG.get("confirm_write"),shell_fn=config.AGENT_CONFIG.get("_shell_fn"),yolo=yolo))
    return "ok",[]
A.run_agent=fake_run_agent
from ccos.core.plugin_manager import PluginManager
pm=PluginManager(); print("load agent:",pm.load("agent"))
print("before:",config.AGENT_CONFIG["confirm_shell"],config.AGENT_CONFIG["confirm_write"])
sentinel=lambda c:"X"
r=pm.call_capability("coding.run_agent",prompt="do x",yolo=True,confirm_shell=False,confirm_write=False,shell_fn=sentinel)
print("inner agent saw:",{k:(v if k!="shell_fn" else getattr(v,'__name__',v)) for k,v in seen.items()})
print("after:",config.AGENT_CONFIG["confirm_shell"],config.AGENT_CONFIG["confirm_write"])
print("audit:",open(B+"/state/audit.jsonl").read().splitlines()[-1])
print("authority of coding.run_agent:", pm._authority_for("coding.run_agent", pm._registry.get("coding.run_agent")))
