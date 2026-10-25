import sys, os, json
sys.path.insert(0,os.path.dirname(os.path.realpath(__file__)))
from common import *
SNAP=B+"/snap"
ws=B+"/ws/w1"
import shutil
shutil.rmtree(ws, ignore_errors=True); shutil.rmtree(B+"/outside", ignore_errors=True)
os.makedirs(ws+"/.git/hooks"); os.makedirs(ws+"/sub/.git/hooks"); os.makedirs(B+"/outside")
open(B+"/outside/secret.txt","w").write("TOPSECRET-OUT\n")
open(ws+"/README.md","w").write("orig readme\n"*20)
os.symlink(B+"/outside", ws+"/lnk_out"); os.symlink(B+"/outside/secret.txt", ws+"/lnk_file")
os.symlink(B+"/outside/new.txt", ws+"/dangle"); os.symlink(SNAP+"/core", ws+"/lnk_core")
os.symlink(ws+"/.git", ws+"/lnk_git"); os.symlink(ws+"/README.md", ws+"/alias.txt")
os.symlink(SNAP+"/bench", ws+"/lnk_bench")
setup(SNAP, ws)
from utils import config
config.AGENT_CONFIG["confirm_write"]=False; config.AGENT_CONFIG["confirm_shell"]=False
from tools import file_tools as ft, patch_tools as pt
out=[]
def t(pid, desc, fn, *a):
    try: r=fn(*a)
    except Exception as e: r="EXC "+repr(e)
    r=str(r)[:300]
    print("##",pid,desc,"=>",r); out.append((pid,desc,r))
t("FT01","write_file lnk_out/x.txt (symlink dir to outside)", ft.tool_write_file,"lnk_out/x.txt","pwn")
t("FT02","write_file lnk_file (symlink file to outside)", ft.tool_write_file,"lnk_file","pwn")
t("FT03","write_file dangle (dangling symlink to outside)", ft.tool_write_file,"dangle","pwn")
t("FT04","write_file lnk_core/zz_new.py (symlink to CODE_DIR/core, no allow_self_mod)", ft.tool_write_file,"lnk_core/zz_new.py","x=1\n")
t("FT05","write_file lnk_git/hooks/pre-commit", ft.tool_write_file,"lnk_git/hooks/pre-commit","#!/bin/sh\necho pwn\n")
t("FT06","write_file .git/hooks/pre-commit", ft.tool_write_file,".git/hooks/pre-commit","#!/bin/sh\n")
t("FT07","write_file sub/.git/hooks/pre-commit (nested repo hook)", ft.tool_write_file,"sub/.git/hooks/pre-commit","#!/bin/sh\necho pwn\n")
t("FT08","append_file sub/.git/config", ft.tool_append_file,"sub/.git/config","[core]\n\thooksPath=/x\n")
t("FT09","write_file ../escape.txt", ft.tool_write_file,"../escape.txt","pwn")
t("FT10","write_file a/../../escape2.txt", ft.tool_write_file,"a/../../escape2.txt","pwn")
t("FT11","patch_file ABS outside secret w/ nonmatching old_str (read)", pt.tool_patch_file, B+"/outside/secret.txt","NOPE","x")
t("FT12","patch_file ~ expansion HOME/.hidden (read)", pt.tool_patch_file, "~/.hidden_cred","NOPE","x")
t("FT13","patch_file lnk_file (symlink to outside; matching old_str)", pt.tool_patch_file,"lnk_file","TOPSECRET-OUT","PATCHED")
t("FT14","read_file ABS outside", ft.tool_read_file, B+"/outside/secret.txt")
t("FT15","read_file lnk_file", ft.tool_read_file,"lnk_file")
t("FT16","write_file alias.txt -> README.md (WRITE_PROTECTED bypass via symlink name; confirm would block on stdin EOF)", ft.tool_write_file,"alias.txt","replaced via alias\n"*20)
t("FT17","write_file README.md direct (control: WRITE_PROTECTED confirm, stdin EOF)", ft.tool_write_file,"README.md","replaced direct\n"*20)
t("FT18","write_file with NUL in path", ft.tool_write_file,"a\0b.txt","x")
t("FT19","write_file lnk_bench/zz.py (HIGH, no allow_self_mod, ws outside)", ft.tool_write_file,"lnk_bench/zz.py","x=1\n")
print(open(ws+"/README.md").read()[:60])
print("outside secret now:", open(B+"/outside/secret.txt").read())
print("outside ls:", os.listdir(B+"/outside"))
print("sub hook:", os.path.exists(ws+"/sub/.git/hooks/pre-commit"), "root hook:", os.path.exists(ws+"/.git/hooks/pre-commit"))
print("core new:", os.path.exists(SNAP+"/core/zz_new.py"))
print("escape files:", os.path.exists(B+"/ws/escape.txt"), os.path.exists(B+"/escape2.txt"))
