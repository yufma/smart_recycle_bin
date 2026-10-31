"""Send one sample measurement through the sensor API (stdlib only)."""
import argparse
import getpass
import json
import os
import urllib.error
import urllib.request

def main(argv=None):
    parser = argparse.ArgumentParser(description="Reloop sensor packet sender")
    parser.add_argument("--url", default="http://127.0.0.1:8765")
    parser.add_argument("--bin", default="B-001", dest="bin_id")
    parser.add_argument("--compartment", type=str.upper, choices=("CAN", "PET", "GLASS", "OTHER"), required=True,
                        help="compartment measured by this sensor (required; no implicit default)")
    parser.add_argument("--fill", type=float, required=True)
    args = parser.parse_args(argv)
    if not 0 <= args.fill <= 100:
        parser.error("--fill must be between 0 and 100")
    key = os.environ.get("RELOOP_DEVICE_KEY") or getpass.getpass("Device key (input hidden): ")
    body = json.dumps({"bin_id": args.bin_id, "compartment": args.compartment, "fill_percent": args.fill}).encode()
    request = urllib.request.Request(args.url.rstrip("/") + "/api/device/readings", data=body,
                                     headers={"Content-Type": "application/json", "X-Device-Key": key}, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            print(response.read().decode())
    except urllib.error.HTTPError as error:
        print(f"HTTP {error.code}: {error.read().decode()}")
        return 1
    except urllib.error.URLError as error:
        print(f"Connection failed: {error.reason}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
