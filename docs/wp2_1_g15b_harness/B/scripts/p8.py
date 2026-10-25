import sys, os, shutil
sys.path.insert(0,os.path.dirname(os.path.realpath(__file__)))
from common import *
H=B+"/h8"; shutil.rmtree(H, ignore_errors=True); os.makedirs(H)
shutil.copytree(B+"/snap", H+"/Codey-OS")
CD=H+"/Codey-OS"
setup(CD, CD)
from utils import config
assert config.AGENT_CONFIG["confirm_write"] is True     # REPL default
assert not config.AGENT_CONFIG.get("allow_self_modification")
import utils.logger as lg
asked=[]
def rec(q): asked.append(q); return False
lg.confirm=rec
import tools.patch_tools as pt; pt.ask_confirm=rec
from tools import file_tools as ft
def t(pid,fn,*a):
    n=len(asked); r=fn(*a); print("##",pid,a[0],"=> prompts:",len(asked)-n,"|",str(r)[:80].replace("\n"," "))
t("R1 write_file NEW core file",ft.tool_write_file,"core/zz_new.py","x = 1\n")
t("R2 write_file EXISTING core file (control)",ft.tool_write_file,"core/state.py",open(CD+"/core/state.py").read()+"\n# edit\n")
t("R3 append_file EXISTING core file",ft.tool_append_file,"core/action_gateway.py","\n# appended\n")
t("R4 append_file EXISTING WRITE_PROTECTED CODEY.md/README.md",ft.tool_append_file,"README.md","\nappended\n")
t("R5 write_file EXISTING README.md (control)",ft.tool_write_file,"README.md","x"*3000)
t("R6 patch_file core (control)",pt.tool_patch_file,"core/state.py","# edit","# edit2")
print("core/zz_new.py exists:",os.path.exists(CD+"/core/zz_new.py"),"| action_gateway tail:",repr(open(CD+"/core/action_gateway.py").read()[-20:]))
