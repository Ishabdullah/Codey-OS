import argparse
import json
import logging
import os
import subprocess
import sys
import time
import tempfile
from pathlib import Path
from google.cloud import storage

sys.path.insert(0, str(Path(__file__).parent.parent.resolve()))
from utils.config import get_restoricon_doc_store_path

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def get_bucket_name():
    config_path = os.path.expanduser("~/.codeyOS/config.json")
    if os.path.exists(config_path):
        try:
            with open(config_path, "r") as f:
                config = json.load(f)
                return config.get("gcs_backup_bucket", "codey-os-backups")
        except Exception as e:
            logging.error(f"Error reading config.json: {e}")
    return "codey-os-backups"

def get_public_key():
    key_path = os.path.expanduser("~/.codeyOS/age.key")
    if not os.path.exists(key_path):
        logging.error(f"Identity key not found at {key_path}")
        return None
    try:
        with open(key_path, "rb") as f:
            pubkey = subprocess.check_output(["age-keygen", "-y"], stdin=f).decode('utf-8').strip()
        return pubkey
    except subprocess.CalledProcessError as e:
        logging.error(f"Error extracting public key: {e}")
        return None

def encrypt_file(source_file, temp_file_path, pubkey):
    try:
        subprocess.check_call(["age", "-r", pubkey, "-o", temp_file_path, source_file])
        return True
    except subprocess.CalledProcessError as e:
        logging.error(f"Error encrypting file {source_file}: {e}")
        return False

def write_state_atomically(state, state_file):
    try:
        tmp_fd, tmp_path = tempfile.mkstemp(dir=os.path.dirname(state_file))
        with os.fdopen(tmp_fd, "w") as f:
            json.dump(state, f)
        os.replace(tmp_path, state_file)
    except Exception as e:
        logging.error(f"Error writing state atomically: {e}")

def do_backup():
    # Setup GCS credentials
    cred_path = os.path.expanduser("~/.codeyOS/gcp_credentials.json")
    if os.path.exists(cred_path):
        os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = cred_path
    else:
        logging.warning(f"GCP credentials not found at {cred_path}")

    bucket_name = get_bucket_name()
    pubkey = get_public_key()
    if not pubkey:
        logging.error("Cannot proceed without a valid public key.")
        return

    doc_store_path = get_restoricon_doc_store_path()
    if not os.path.exists(doc_store_path):
        logging.info(f"Document store not found at {doc_store_path}, nothing to backup.")
        return

    state_file = os.path.expanduser("~/.codeyOS/document_upload_state.json")
    state = {}
    if os.path.exists(state_file):
        try:
            with open(state_file, "r") as f:
                state = json.load(f)
        except Exception as e:
            logging.error(f"Error reading state file: {e}")
            state = {}

    try:
        client = storage.Client()
        bucket = client.bucket(bucket_name)
    except Exception as e:
        logging.error(f"Error initializing GCS client or bucket: {e}")
        return

    state_changed = False
    for root, _, files in os.walk(doc_store_path):
        for file in files:
            file_path = os.path.join(root, file)
            relative_path = os.path.relpath(file_path, doc_store_path)
            
            try:
                mtime = os.path.getmtime(file_path)
            except OSError as e:
                logging.error(f"Error getting mtime for {file_path}: {e}")
                continue

            if relative_path not in state or mtime > state[relative_path]:
                logging.info(f"File {relative_path} is new or modified, uploading...")
                
                with tempfile.NamedTemporaryFile(delete=False, suffix=".age") as temp_file:
                    temp_file_path = temp_file.name
                    
                try:
                    if encrypt_file(file_path, temp_file_path, pubkey):
                        gcs_blob_path = f"restoricon/documents_backup/{relative_path}.age"
                        blob = bucket.blob(gcs_blob_path)
                        blob.upload_from_filename(temp_file_path)
                        logging.info(f"Successfully uploaded {gcs_blob_path}")
                        
                        state[relative_path] = mtime
                        state_changed = True
                    else:
                        logging.error(f"Failed to encrypt {file_path}")
                except Exception as e:
                    logging.error(f"Error uploading {file_path} to GCS: {e}")
                finally:
                    if os.path.exists(temp_file_path):
                        os.remove(temp_file_path)
    
    if state_changed:
        write_state_atomically(state, state_file)

def main():
    parser = argparse.ArgumentParser(description="Incremental Document Backup")
    parser.add_argument("--daemon", action="store_true", help="Run as a background daemon")
    parser.add_argument("--interval", type=int, default=3600, help="Interval in seconds for daemon loop (default: 3600)")
    args = parser.parse_args()

    if args.daemon:
        logging.info(f"Starting backup daemon with interval {args.interval} seconds.")
        while True:
            do_backup()
            logging.info(f"Backup cycle complete. Sleeping for {args.interval} seconds.")
            time.sleep(args.interval)
    else:
        logging.info("Starting one-time backup.")
        do_backup()
        logging.info("Backup complete.")

if __name__ == "__main__":
    main()
