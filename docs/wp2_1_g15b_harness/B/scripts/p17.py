import sys, os, shutil
sys.path.insert(0,os.path.dirname(os.path.realpath(__file__)))
from common import *
H=B+"/h17"; shutil.rmtree(H, ignore_errors=True); os.makedirs(H)
shutil.copytree(B+"/snap", H+"/Codey-OS"); CD=H+"/Codey-OS"
os.symlink(CD+"/core/zzloop2", CD+"/core/zzloop"); os.symlink(CD+"/core/zzloop", CD+"/core/zzloop2")
setup(CD, CD); os.environ["CODEY_STATE_DIR"]=H+"/state"
from utils import config
config.AGENT_CONFIG["confirm_write"]=False
from tools import file_tools as ft, patch_tools as pt
import sys; print("##python", sys.version.split()[0])
for p in ("core/zzloop/x.py","core/zzloop","core/zzloop2/y.txt"):
    try: c=ft.classify_write_action(p)
    except BaseException as e: c="EXC "+repr(e)
    print("##L classify",p,"->",c)
    for fn,name in ((ft.tool_write_file,"write"),(ft.tool_append_file,"append")):
        try: r=fn(p,"x=1\n")
        except BaseException as e: r="EXC "+repr(e)
        print("##L",name,p,"->",str(r)[:110])
try: r=pt.tool_patch_file("core/zzloop/x.py","a","b")
except BaseException as e: r="EXC "+repr(e)
print("##L patch ->",str(r)[:110])
