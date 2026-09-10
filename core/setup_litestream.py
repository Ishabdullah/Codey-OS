import os
import sys
from pathlib import Path

def main():
    # Insert project root to sys.path
    project_root = Path(__file__).parent.parent.resolve()
    sys.path.insert(0, str(project_root))
    
    from utils.config import load_user_config, get_restoricon_api_config, CODEY_STATE_DIR

    out_path = CODEY_STATE_DIR / "litestream.yml"

    cfg = load_user_config()
    bucket = os.environ.get("GCS_BACKUP_BUCKET")
    if not bucket:
        bucket = cfg.get("gcs_backup_bucket", "codey-os-backups")

    # Resolve the DB Litestream replicates from the same source the API
    # server uses (U.39 / NEW-455) so backups always track the live DB.
    db_path = get_restoricon_api_config()["db_path"]

    yml = f"""dbs:
  - path: {db_path}
    replicas:
      - type: gcs
        bucket: {bucket}
        path: restoricon/restoricon_db
        encryption:
          type: age
          identities:
            - ~/.codeyOS/age.key
"""
    out_path.write_text(yml)

if __name__ == "__main__":
    main()
