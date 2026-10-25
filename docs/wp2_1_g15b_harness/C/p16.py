exec(open(__import__("os").path.join(__import__("os").path.dirname(__import__("os").path.realpath(__file__)),"h.py")).read())
os.chdir(SNAP)
from tools.shell_tools import shell, classify_shell_command
from utils import config
config.AGENT_CONFIG["confirm_shell"]=False
cmd="python3 -m tools.provision_ai_agent_auth --username codey-ccos-crm-reader"
print("class:",classify_shell_command(cmd))
o1=shell(cmd,yolo=True); print("run1:",o1.replace("\n"," | ")[:700])
o2=shell(cmd,yolo=True); print("run2:",o2[:120].replace("\n"," | "))
import sqlite3,glob
for p in glob.glob(os.environ["HOME"]+"/.codey_restoricon/*.db"):
    c=sqlite3.connect(p); print(p,[r for r in c.execute("select id,revoked_at is not null from api_tokens")] if True else "")
