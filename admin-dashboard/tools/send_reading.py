"""Send one sample measurement through the sensor API (stdlib only)."""
import argparse
import getpass
import json
import os
import urllib.error
import urllib.request

parser = argparse.ArgumentParser(description="Reloop sensor packet sender")
parser.add_argument("--url", default="http://127.0.0.1:8765")
parser.add_argument("--bin", default="B-001", dest="bin_id")
parser.add_argument("--fill", type=float, required=True)
args = parser.parse_args()
if not 0 <= args.fill <= 100:
    parser.error("--fill must be between 0 and 100")
key = os.environ.get("RELOOP_DEVICE_KEY") or getpass.getpass("Device key (input hidden): ")
body = json.dumps({"bin_id": args.bin_id, "fill_percent": args.fill}).encode()
request = urllib.request.Request(args.url.rstrip("/") + "/api/device/readings", data=body,
                                 headers={"Content-Type": "application/json", "X-Device-Key": key}, method="POST")
try:
    with urllib.request.urlopen(request, timeout=10) as response:
        print(response.read().decode())
except urllib.error.HTTPError as error:
    print(f"HTTP {error.code}: {error.read().decode()}")
    raise SystemExit(1)
except urllib.error.URLError as error:
    print(f"Connection failed: {error.reason}")
    raise SystemExit(1)
