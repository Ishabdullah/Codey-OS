exec(open(__import__("os").path.join(__import__("os").path.dirname(__import__("os").path.realpath(__file__)),"h.py")).read())
install_fakes(); os.chdir(B+"/work")
from tools.shell_tools import classify_shell_command as c
for x in ["env ALLOW_SELF_MOD=1 python3 main.py --yolo x","env CODEY_ACTION_GATEWAY_AUDIT=/dev/null python3 main.py --yolo x","python3 main.py --yolo --allow-self-mod x","python3 /data/data/com.termux/files/home/Codey-OS/main.py x --yolo --allow-self-mod --no-resume","python3 -c \"import os;os.environ['ALLOW_SELF_MOD']='1';os.system('python3 main.py --yolo x')\"","bash -lc 'ALLOW_SELF_MOD=1 CODEY_ACTION_GATEWAY_AUDIT=/dev/null python3 main.py --yolo x'","nice python3 main.py --yolo x","python3 -m main --yolo x"]:
    print(c(x),"|",x)
