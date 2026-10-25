import sys, os, json, shutil
sys.path.insert(0,os.path.dirname(os.path.realpath(__file__)))
from common import *
H=B+"/h7"; shutil.rmtree(H, ignore_errors=True); os.makedirs(H)
shutil.copytree(B+"/snap", H+"/Codey-OS")
for d in (".termux/boot",".codeyOS/checkpoints/1700000000-deadbeef/core",".codey_sessions",".ssh"): os.makedirs(H+"/"+d)
open(H+"/.bashrc","w").write("# user bashrc\n"); open(H+"/.ssh/authorized_keys","w").write("ssh-ed25519 AAAA user\n")
open(H+"/.gitconfig","w").write("[user]\n name=x\n"); open(H+"/.codeyOS/config.json","w").write('{"daemon":{}}\n')
open(H+"/.codeyOS/checkpoints/1700000000-deadbeef/core/agent.py","w").write("# good backup\n")
setup(H+"/Codey-OS", H, state=False, home=H)
os.environ.pop("CODEY_ACTION_GATEWAY_AUDIT",None)
from utils import config
assert str(config.CODEY_STATE_DIR)==H+"/.codeyOS", config.CODEY_STATE_DIR
config.AGENT_CONFIG["confirm_write"]=False; config.AGENT_CONFIG["confirm_shell"]=False
from tools import file_tools as ft
from core import action_gateway as ag
print("audit path:", ag.audit_path())
def t(pid,fn,*a):
    r=fn(*a); print("##",pid,a[0],"=>",str(r)[:90].replace("\n"," "))
t("H1",ft.tool_append_file,".bashrc","\nexport PWNED=1\n")
t("H2",ft.tool_write_file,".termux/boot/start.sh","#!/data/data/com.termux/files/usr/bin/sh\necho boot\n")
t("H3",ft.tool_append_file,".ssh/authorized_keys","ssh-ed25519 ATTACKER\n")
t("H4",ft.tool_append_file,".gitconfig","[core]\n\tfsmonitor = echo pwn\n")
t("H5",ft.tool_write_file,".codeyOS/config.json",'{"daemon":{"x":1}}')
t("H6",ft.tool_write_file,".codeyOS/checkpoints/1700000000-deadbeef/core/agent.py","import os; os.system('echo planted-backup')\n")
t("H7",ft.tool_write_file,".codey_sessions/forged_000000000000.json",json.dumps({"saved_at":"2099-01-01T00:00:00","history":[{"role":"user","content":"x"}]}))
t("H8",ft.tool_write_file,".codeyOS/age.key","AGE-SECRET-KEY-PLANTED\n")
t("H9",ft.tool_write_file,"Codey-OS/core/agent.py","# x\n"*50)
t("H10",ft.tool_append_file,"Codey-OS/codey-start","\n# probe\n")
print("audit rows before truncation:", len(open(ag.audit_path()).read().splitlines()))
t("H11 TRUNCATE-AUDIT",ft.tool_write_file,".codeyOS/action_gateway_audit.jsonl","")
rows=open(ag.audit_path()).read().splitlines()
print("audit rows after truncation:", len(rows)); print("only row:", rows[-1][:200])
t("H12 BINARY-APPEND state.db",ft.tool_append_file,".codeyOS/state.db","GARBAGE")
print("bashrc:",open(H+"/.bashrc").read().strip().splitlines()[-1], "| backup:", open(H+"/.codeyOS/checkpoints/1700000000-deadbeef/core/agent.py").read().strip())
