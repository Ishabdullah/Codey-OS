import os
import subprocess
import tarfile
from pathlib import Path
from google.cloud import storage

def backup_secrets():
    codey_os_dir = Path.home() / ".codeyOS"
    backup_files = [
        codey_os_dir / "config.json",
        codey_os_dir / "gcp_credentials.json",
    ]
    
    tar_path = "/data/data/com.termux/files/home/secrets.tar.gz"
    enc_path = "/data/data/com.termux/files/home/secrets.tar.gz.age"
    
    with tarfile.open(tar_path, "w:gz") as tar:
        for f in backup_files:
            if f.exists():
                tar.add(f, arcname=f.name)
                
    # Encrypt
    subprocess.run(["age", "-r", "age1gmuh2y5wfyaquzj8ltl2dmephdnrrdnc9x2ctvv5a759c5268clsrqxntp", "-o", enc_path, tar_path], check=True)
    
    bucket_name = "codey-os-backups"
    import json
    cfg_path = codey_os_dir / "config.json"
    if cfg_path.exists():
        with open(cfg_path) as f:
            bucket_name = json.load(f).get("gcs_backup_bucket", bucket_name)
            
    client = storage.Client()
    bucket = client.bucket(bucket_name)
    blob = bucket.blob("restoricon/secrets_backup/secrets.tar.gz.age")
    blob.upload_from_filename(enc_path)
    
    # Cleanup
    os.remove(tar_path)
    os.remove(enc_path)
    print("Secrets backed up successfully to GCS.")

if __name__ == "__main__":
    backup_secrets()
