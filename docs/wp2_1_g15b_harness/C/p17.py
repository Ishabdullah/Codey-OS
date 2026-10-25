exec(open(__import__("os").path.join(__import__("os").path.dirname(__import__("os").path.realpath(__file__)),"h.py")).read())
install_fakes(); os.chdir(B+"/work")
from tools.shell_tools import classify_shell_command as c
R=SNAP  # scratch snapshot, not the real repo
for x in [f"{R}/codey-stop","codey-stop","bash codey-stop","codeydOS stop","codeydOS restart",f"python3 {R}/core/process_identity.py stop /x/pid svc",f"python3 {R}/core/service_lifecycle.py lock-exec all stop",f"python3 {R}/core/setup_dr_key.py --force",f"python3 {R}/tools/encrypt_cloudflare_token.py --force",f"python3 {R}/core/backup_secrets.py",f"python3 {R}/core/backup_documents.py",f"python3 -m restoricon_core.migrate_aigentik --apply","python3 -m restoricon_core.backfill_wo_351695937 --apply","python3 -m tools.provision_ai_agent_auth",f"python3 {R}/core/setup_litestream.py",f"python3 {R}/tools/release_model_cli.py","python3 -m restoricon_core.api.server --host 0.0.0.0 --port 8770",f"python3 {R}/main.py --import-lora /x --lora-force-adopt","python3 main.py --yolo --allow-self-mod 'task'","codeyOS --bg task","codeyOS --daemon"]:
    print(c(x),"|",x)
