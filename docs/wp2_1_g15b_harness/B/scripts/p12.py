import sys, os, shutil
sys.path.insert(0,os.path.dirname(os.path.realpath(__file__)))
from common import *
ws="/sdcard/Download/g15b_hunterB_tmp"
shutil.rmtree(ws,ignore_errors=True); os.makedirs(ws+"/.git/hooks")
open(ws+"/README.md","w").write("orig\n"*30)
try:
    setup(B+"/snap", ws)
    from utils import config
    config.AGENT_CONFIG["confirm_write"]=False
    from tools import file_tools as ft
    print("##K1 write_file('.GIT/hooks/pre-commit'):", ft.tool_write_file(".GIT/hooks/pre-commit","#!/bin/sh\necho pwn\n"))
    print("##K1b actually landed in .git/hooks/pre-commit:", os.path.exists(ws+"/.git/hooks/pre-commit"), sorted(os.listdir(ws)))
    print("##K2 control write_file('.git/hooks/x'):", ft.tool_write_file(".git/hooks/x","y"))
    print("##K3 write_file('ReadMe.md') (WRITE_PROTECTED is 'README.md'/'readme.md'; stdin EOF):", ft.tool_write_file("ReadMe.md","changed\n"*30))
    print("##K3b README.md content now:", open(ws+"/README.md").read()[:16].replace("\n","|"))
finally:
    shutil.rmtree(ws,ignore_errors=True); print("cleanup exists:", os.path.exists(ws))
