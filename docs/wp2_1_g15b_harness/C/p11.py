exec(open(__import__("os").path.join(__import__("os").path.dirname(__import__("os").path.realpath(__file__)),"h.py")).read())
install_fakes(); os.chdir(B+"/work")
from pathlib import Path
import core.loader_v2 as L
uid=os.getuid()
def mkproc(root,pid,ticks,u,state="S",boot="aaaaaaaa-0000-0000-0000-000000000001"):
    r=Path(root); (r/"sys/kernel/random").mkdir(parents=True,exist_ok=True); (r/"sys/kernel/random/boot_id").write_text(boot+"\n")
    d=r/str(pid); d.mkdir(parents=True,exist_ok=True)
    fields=[state,"1"]+["0"]*17+[str(ticks)]+["0"]*10
    (d/"stat").write_text(f"{pid} (llama-server) "+" ".join(fields)+"\n")
    (d/"status").write_text(f"Name:\tllama-server\nUid:\t{u}\t{u}\t{u}\t{u}\n")
import shutil
def case(name, setup, expected_ticks=100, expected_uid=uid, expected_boot="aaaaaaaa-0000-0000-0000-000000000001", pid=4242):
    root=B+"/work/fakeproc_"+name; shutil.rmtree(root,ignore_errors=True); setup(root)
    exp={"pid":pid,"boot_id":expected_boot,"start_ticks":expected_ticks,"uid":expected_uid}
    CALLS.clear()
    out=L._kill_single_pid_term_then_kill(pid,0.2,expected=exp,proc_root=Path(root))
    kills=[c[1] for c in CALLS if c[0]=="os.kill"]
    print(f"{name}|outcome={out.outcome} attempted={out.attempted} replaced={out.replaced}|os.kill calls={kills}")
case("control_matching", lambda r: mkproc(r,4242,100,uid))
case("recycled_pid_diff_start_ticks", lambda r: mkproc(r,4242,999,uid))
case("expected_uid_not_ours", lambda r: mkproc(r,4242,100,uid), expected_uid=uid+1)
case("proc_boot_id_missing_unreadable", lambda r: (mkproc(r,4242,100,uid), os.remove(r+"/sys/kernel/random/boot_id")))
case("different_boot", lambda r: mkproc(r,4242,100,uid,boot="bbbbbbbb-0000-0000-0000-000000000002"))
case("pid_gone", lambda r: (mkproc(r,1111,1,uid)))
case("zombie", lambda r: mkproc(r,4242,100,uid,state="Z"))
case("pid_1_invalid", lambda r: mkproc(r,1,100,uid), pid=1)
case("bool_pid", lambda r: mkproc(r,1,100,uid), pid=True)
