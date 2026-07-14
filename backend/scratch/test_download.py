import urllib.request
from pathlib import Path

BACKEND_DIR = Path("c:/Users/Admin/Documents/DEV/ADMCINCO/app-cinco/backend")
LOCAL_IMAGE_DIR = BACKEND_DIR / "static" / "images"

filename = "sello_cinco.png"
remote_url = f"https://www.cincosas.com/images/{filename}"
local_path = LOCAL_IMAGE_DIR / filename

try:
    LOCAL_IMAGE_DIR.mkdir(parents=True, exist_ok=True)
    req = urllib.request.Request(
        remote_url, 
        headers={'User-Agent': 'Mozilla/5.0'}
    )
    with urllib.request.urlopen(req, timeout=5) as response:
        if response.status == 200:
            content = response.read()
            local_path.write_bytes(content)
            print(f"SUCCESS: Downloaded {filename} of size {len(content)} bytes to {local_path}")
        else:
            print(f"FAILED: HTTP status {response.status}")
except Exception as e:
    print(f"ERROR: Failed to download: {e}")
