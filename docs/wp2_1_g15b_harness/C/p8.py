exec(open(__import__("os").path.join(__import__("os").path.dirname(__import__("os").path.realpath(__file__)),"h.py")).read())
os.environ["CODEY_BACKEND"]="openrouter"; os.environ["OPENROUTER_API_KEY"]="FAKE-OR-KEY"
os.chdir(B+"/work")
import urllib.request
REQ=[]
def fake(req,*a,**k):
    REQ.append((req.full_url, dict(req.header_items()), req.data)); raise OSError("blocked")
urllib.request.urlopen=fake
from core.inference_openrouter import get_remote_backend
b=get_remote_backend()
n0=len(open(B+"/state/audit.jsonl").read().splitlines())
b.infer([{"role":"user","content":"file content: password=FAKE-NETRC-SECRET from ~/.netrc"}])
u,h,d=REQ[0]
print("URL",u); print("headers",{k:(v[:18] if k.lower()=='authorization' else v) for k,v in h.items()}); print("body has secret:", b"FAKE-NETRC-SECRET" in d)
print("audit rows added:",len(open(B+"/state/audit.jsonl").read().splitlines())-n0)
# NEW: does the base URL accept plain http / arbitrary host from env? (config only)
import utils.config as C
print("base url source env OPENROUTER_BASE_URL default:",C.OPENROUTER_BASE_URL)
