exec(open(__import__("os").path.join(__import__("os").path.dirname(__import__("os").path.realpath(__file__)),"h.py")).read())
import subprocess as sp, asyncio, tempfile, time
os.chdir(B+"/work")
# (c) does asyncio unix server expose peer_uid/peer_pid extra info?
async def main():
    seen={}
    async def h(r,w):
        seen["peer_uid"]=w.get_extra_info("peer_uid"); seen["peer_pid"]=w.get_extra_info("peer_pid")
        seen["keys_probe"]={k:(w.get_extra_info(k) is not None) for k in ("peername","sockname","socket","peercred")}
        w.write(b"ok"); await w.drain(); w.close()
    sock=B+"/work/t.sock"
    try: os.unlink(sock)
    except FileNotFoundError: pass
    srv=await asyncio.start_unix_server(h,path=sock)
    r,w=await asyncio.open_unix_connection(sock)
    await r.read(10); w.close()
    srv.close(); await srv.wait_closed()
    return seen
print("C peer_uid/peer_pid:",asyncio.run(main()))
# (d) TIOCSTI on a pty we own, from a child with that pty as controlling tty
import pty, fcntl, termios
code=r'''
import os,pty,fcntl,termios,sys
m,s=pty.openpty()
os.setsid()
try:
    fcntl.ioctl(s,termios.TIOCSCTTY,0)
except Exception as e:
    print("TIOCSCTTY fail",repr(e))
try:
    fcntl.ioctl(s,termios.TIOCSTI,b"y")
    print("TIOCSTI ok")
    import select
    r,_,_=select.select([m],[],[],0.2)
    print("injected visible to reader side:",bool(r))
except Exception as e:
    print("TIOCSTI fail",repr(e))
'''
r=sp.run(["python3","-I","-c",code],capture_output=True,text=True,timeout=10)
print("D TIOCSTI probe:",r.stdout.strip().replace("\n"," | "),r.stderr.strip()[:200])
try:
    print("D2 legacy_tiocsti sysctl:",open("/proc/sys/dev/tty/legacy_tiocsti").read().strip())
except Exception as e: print("D2 sysctl unreadable",repr(e))
# (e) cmdline exposure of a token passed as argv (fabricated), cloudflared-style
p=sp.Popen(["python3","-I","-c","import time;time.sleep(6)","cloudflared","tunnel","run","--token","FAKE-CF-TUNNEL-TOKEN-123"],stdout=sp.DEVNULL,stderr=sp.DEVNULL)
time.sleep(0.5)
from tools.shell_tools import shell, classify_shell_command
from utils import config
config.AGENT_CONFIG["confirm_shell"]=False
cmd=f"cat /proc/{p.pid}/cmdline"
out=shell(cmd,yolo=True)
print("E class:",classify_shell_command(cmd),"| shell(yolo) output:",repr(out[:200]))
p.wait()
