import os
import re
import sys
import json
import time
import shutil
import urllib.request
import urllib.error
import subprocess
import logging
import argparse
import platform
import hashlib
from typing import Optional, Tuple

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(os.path.join(os.environ.get("TEMP", "C:\\"), "helium_updater.log"))
    ]
)

REPO_API_URL = "https://api.github.com/repos/imputnet/helium-windows/releases/latest"

def get_installed_version() -> Optional[str]:
    """Reads the installed version by looking at adjacent sequence-numbered directories."""
    if getattr(sys, 'frozen', False):
        executable_dir = os.path.dirname(os.path.abspath(sys.executable))
    else:
        executable_dir = os.path.dirname(os.path.abspath(__file__))
    version_regex = re.compile(r"^\d+\.\d+\.\d+\.\d+$")
    versions = []
    
    for item in os.listdir(executable_dir):
        path = os.path.join(executable_dir, item)
        if os.path.isdir(path) and version_regex.match(item):
            versions.append(item)
            
    if not versions:
        logging.warning("No version directory found next to updater.")
        return None
        
    # Sort logically (by integer parts, not lexically)
    versions.sort(key=lambda s: [int(u) for u in s.split('.')])
    return versions[-1]

def get_latest_release() -> Tuple[Optional[str], Optional[str], Optional[str]]:
    """Contacts GitHub API to find the latest version and download URL."""
    try:
        req = urllib.request.Request(
            REPO_API_URL,
            headers={"User-Agent": "Helium-Updater"}
        )
        with urllib.request.urlopen(req, timeout=10) as response:
            data = json.loads(response.read().decode('utf-8'))
            
            tag_name = data.get("tag_name", "").lstrip("v")
            assets = data.get("assets", [])
            download_url = None
            installer_name = ""
            
            # Identify current architecture
            machine = platform.machine().lower()
            if 'arm' in machine or 'aarch64' in machine:
                target_arch = 'arm64'
            else:
                target_arch = 'x64'
            
            for asset in assets:
                name = asset.get("name", "").lower()
                if "installer" in name and name.endswith(".exe") and target_arch in name:
                    download_url = str(asset.get("browser_download_url", ""))
                    installer_name = str(asset.get("name", ""))
                    break
                    
            sha256_url = None
            if download_url:
                expected_sha_name = f"{installer_name}.sha256".lower()
                for asset in assets:
                    if asset.get("name", "").lower() == expected_sha_name:
                        sha256_url = asset.get("browser_download_url")
                        break
                        
            return tag_name, download_url, sha256_url
    except Exception as e:
        logging.error(f"Failed to fetch latest release API: {e}")
        return None, None, None

def is_newer_version(local: Optional[str], remote: Optional[str]) -> bool:
    """Returns True if the remote version is logically greater than local."""
    if local is None or remote is None:
        return False
        
    try:
        local_parts = [int(x) for x in str(local).split('.')]
        remote_parts = [int(x) for x in str(remote).split('.')]
        return remote_parts > local_parts
    except ValueError:
        logging.error(f"Cannot parse versions for comparison: local={local}, remote={remote}")
        return False

def download_update(url: Optional[str], output_path: str) -> bool:
    """Downloads the file with retries."""
    if not url:
        return False
        
    max_retries = 3
    for attempt in range(1, max_retries + 1):
        try:
            logging.info(f"Downloading {url} to {output_path} (Attempt {attempt}/{max_retries})")
            req = urllib.request.Request(url, headers={"User-Agent": "Helium-Updater"})
            with urllib.request.urlopen(req, timeout=30) as response, open(output_path, 'wb') as out_file:
                shutil.copyfileobj(response, out_file)
            logging.info("Download completed successfully.")
            return True
        except Exception as e:
            logging.error(f"Download failed: {e}")
            time.sleep(2)
    return False

def apply_update(payload_path: str) -> bool:
    """Executes the installer silently."""
    try:
        logging.info(f"Applying update: {payload_path}")
        # mini_installer uses --silent and --system-level flags.
        result = subprocess.run(
            [payload_path, "--silent", "--system-level"],
            capture_output=True,
            text=True
        )
        logging.info(f"Installer exited with code: {result.returncode}")
        if result.returncode == 0:
            return True
        else:
            logging.error(f"Installer failed. STDOUT: {result.stdout}\nSTDERR: {result.stderr}")
            return False
    except Exception as e:
        logging.error(f"Failed to execute installer: {e}")
        return False

def install_scheduled_task():
    """Registers the updater as a Scheduled Task that runs on every user logon."""
    executable = os.path.abspath(sys.executable if getattr(sys, 'frozen', False) else __file__)
    task_name = "HeliumAutoUpdater"
    
    cmd = [
        "schtasks", "/Create", "/F",
        "/SC", "ONLOGON",
        "/TN", task_name,
        "/TR", f'"{executable}"',
        "/RL", "HIGHEST"
    ]
    try:
        subprocess.run(cmd, check=True)
        logging.info("Scheduled task 'HeliumAutoUpdater' installed successfully.")
    except subprocess.CalledProcessError as e:
        logging.error(f"Failed to install scheduled task: {e}")
        sys.exit(1)

def verify_sha256(path: str, expected_hash_str: str) -> bool:
    """Verifies the SHA256 of the downloaded file."""
    # The sidecar often has the format "HASH filename" or just "HASH"
    expected = expected_hash_str.split()[0].strip().lower()
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest().lower() == expected

def main():
    parser = argparse.ArgumentParser(description="Helium Browser Auto-Updater")
    parser.add_argument("--install", action="store_true", help="Installs a Windows Scheduled Task for the updater")
    args = parser.parse_args()
    
    logging.info("Starting Helium Auto-Updater...")
    
    if args.install:
        install_scheduled_task()
        sys.exit(0)
    
    local_version = get_installed_version()
    logging.info(f"Local version: {local_version or 'Unknown'}")
    
    remote_version, download_url, sha256_url = get_latest_release()
    logging.info(f"Remote version: {remote_version or 'Unknown'}")
    
    if not remote_version or not download_url or not sha256_url:
        logging.error("Could not obtain update information (including SHA256) from the network. Exiting.")
        sys.exit(1)
        
    if not local_version or is_newer_version(local_version, remote_version):
        logging.info("An update is required. Proceeding to download.")
        
        temp_dir = os.environ.get("TEMP", "C:\\")
        payload_path = os.path.join(temp_dir, "helium_updater_payload.exe")
        
        # Clean up any previous broken downloads
        if os.path.exists(payload_path):
            try:
                os.remove(payload_path)
            except OSError:
                pass
                
        if download_update(download_url, payload_path):
            # Fetch expected SHA256
            try:
                logging.info("Downloading SHA256 signature sidecar...")
                req = urllib.request.Request(str(sha256_url), headers={"User-Agent": "Helium-Updater"})
                with urllib.request.urlopen(req, timeout=10) as response:
                    expected_sha = response.read().decode('utf-8').strip()
            except Exception as e:
                logging.error(f"Failed to download SHA256 sidecar: {e}")
                sys.exit(1)
                
            logging.info("Verifying SHA256 signature...")
            if verify_sha256(payload_path, expected_sha):
                logging.info("SHA256 signature verified successfully.")
                success = apply_update(payload_path)
                try:
                    os.remove(payload_path)
                except OSError:
                    pass
                if success:
                    logging.info("Update applied successfully.")
                else:
                    logging.error("Update application failed.")
                    sys.exit(1)
            else:
                try:
                    os.remove(payload_path)
                except OSError:
                    pass
                logging.error("SHA256 verification failed. The downloaded installer may be corrupted or tampered with.")
                sys.exit(1)
        else:
            logging.error("Failed to download the update payload.")
            sys.exit(1)
    else:
        logging.info("Helium is up to date. No action needed.")

if __name__ == "__main__":
    main()
