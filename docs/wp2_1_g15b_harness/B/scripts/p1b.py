import sys, os
sys.path.insert(0,os.path.dirname(os.path.realpath(__file__)))
from common import *
SNAP=B+"/snap"; ws=B+"/ws/w1"
setup(SNAP, ws)
from utils import config
config.AGENT_CONFIG["confirm_write"]=False
from tools import patch_tools as pt
r=pt.tool_patch_file(B+"/outside/secret.txt","NOPE","x"); print(repr(r[-80:]))
r=pt.tool_patch_file("~/.hidden_cred","NOPE","x"); print(repr(r[-40:]))
