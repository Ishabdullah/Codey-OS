exec(open(__import__("os").path.join(__import__("os").path.dirname(__import__("os").path.realpath(__file__)),"h.py")).read())
install_fakes(); os.chdir(SNAP)
from tools.shell_tools import classify_shell_command as c, shell
from utils import config
config.AGENT_CONFIG["confirm_shell"]=False
import tools.shell_tools as st
st.ask_confirm=lambda q:(print("PROMPT:",q),False)[1]
for x in ["bash setup_repo.sh","./setup_repo.sh","sh setup_repo.sh","bash tools/setup_skills.sh","bash install.sh","bash setup.sh"]:
    CALLS.clear(); out=shell(x,yolo=False)
    print(c(x),"|",x,"|ran:",[k[1][0] for k in CALLS if k[0]=="subprocess.run"],"|",out[:60])
