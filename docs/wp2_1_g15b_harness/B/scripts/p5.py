import sys, os
sys.path.insert(0,os.path.dirname(os.path.realpath(__file__)))
from common import *
SNAP=B+"/snap"; setup(SNAP, B+"/ws/w5")
from tools.shell_tools import classify_shell_command as c
for cmd in ["sed -i s/a/b/ bench/verify.py","sed -i s/a/b/ bench/tasks/t01_slugify/prompt.txt","cp x.py bench/gate.py",
  "tee bench/suite.lock","python3 -c 'from bench.lock import write_lock; write_lock()'","python3 bench/lock.py",
  "mv x core/agent.py","cp x "+SNAP+"/core/agent.py","sed -i s/a/b/ "+SNAP+"/core/action_gateway.py","rm "+SNAP+"/bench/suite.lock",
  "cp x "+SNAP+"/main.py","tee "+SNAP+"/lib/service_manager.sh","ln -sf /etc/passwd "+SNAP+"/core/zz","touch "+SNAP+"/core/zz.py"]:
    print("##",c(cmd),"|",cmd)
