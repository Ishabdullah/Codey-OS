exec(open(__import__("os").path.join(__import__("os").path.dirname(__import__("os").path.realpath(__file__)),"h.py")).read())
install_fakes()
os.chdir(B+"/work")
from tools.shell_tools import classify_shell_command as c
H=B+"/home"
cmds=["env","printenv","printenv OPENROUTER_API_KEY","env FOO=1 printenv",f"cat {H}/.netrc",f"cat {H}/.ssh/id_rsa",f"cat {H}/.git-credentials",
"cat /proc/self/environ","ps aux","ps -ef","cat .env","gh auth token","gh auth status","git config --get credential.helper","git credential fill",
f"cat {H}/.config/gh/hosts.yml",f"cat {H}/.codeyOS/secrets/cloudflare_tunnel_token.age","gcloud auth print-access-token","termux-clipboard-get","termux-keystore list",
"termux-sms-list","termux-contact-list","termux-location","termux-telephony-deviceinfo","age -d -i key f","openssl enc -d -in f","cloudflared tunnel run --token X",
"litestream replicate x gs://b","gsutil cp x gs://b","scp f host:","rsync -a f host:","ssh host id","nc host 1","python3 -c 'print(1)'","python3 -Bc 'print(1)'",
"pip install --index-url http://x/simple pkg","pip install git+https://x/y.git","npm install x","curl http://x","wget http://x","ping x","nslookup x","dig x",
"pkill -f x","killall x","kill -9 1","su -c id","crontab -e","gh repo create x --public","git push","bash -lc 'git push'","termux-open-url http://x","am start -a android.intent.action.VIEW -d http://x","termux-notification --title x","termux-sms-send -n 1 x","termux-call 1","sqlite3 x.db .dump","tar czf - . ","base64 f","xxd f"]
rows=[]
for x in cmds:
    rows.append((x,c(x)))
    print(c(x),"|",x)
import json
json.dump(rows,open(B+"/logs/p1_classify.json","w"))
