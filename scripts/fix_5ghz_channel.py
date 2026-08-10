#!/usr/bin/env python3
"""
Pin Odido/Zyxel NR5307 5 GHz to a non-DFS channel and enable Wireless logging.

Default is dry-run (read-only). Pass --apply to make changes.

  cp .env.example .env   # set PASSWORD=
  python3 scripts/fix_5ghz_channel.py
  python3 scripts/fix_5ghz_channel.py --apply

Environment:
  PASSWORD       router admin password (required)
  ROUTER_HOST    default 192.168.1.1
  ROUTER_USER    default admin
  CHANNEL        default 36
  BANDWIDTH      default 80   (API uses 20/40/80/160, not "80MHz")
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import ssl
import sys
import time
import urllib.error
import urllib.request
from http.cookiejar import CookieJar
from pathlib import Path


def load_dotenv(path: Path) -> None:
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, val = line.split("=", 1)
        os.environ.setdefault(key.strip(), val.strip().strip('"').strip("'"))


class RouterClient:
    def __init__(self, host: str, user: str, password: str) -> None:
        self.base = f"https://{host}"
        self.user = user
        self.password = password
        self.sessionkey: int | None = None
        ctx = ssl._create_unverified_context()
        self.opener = urllib.request.build_opener(
            urllib.request.HTTPSHandler(context=ctx),
            urllib.request.HTTPCookieProcessor(CookieJar()),
        )

    def call(self, method: str, path: str, data=None, timeout: float = 90):
        url = self.base + path
        if (
            method in ("POST", "PUT", "DELETE")
            and "cgi-bin" in path
            and self.sessionkey is not None
        ):
            url += ("&" if "?" in path else "?") + f"sessionkey={self.sessionkey}"
        body = None
        headers = {
            "Accept": "application/json, text/javascript, */*; q=0.01",
            "X-Requested-With": "XMLHttpRequest",
            "Referer": self.base + "/",
            "Origin": self.base,
            "User-Agent": "nr5307-wifi-fix/1.0",
        }
        if data is not None:
            body = json.dumps(data, separators=(",", ":")).encode()
            headers["Content-Type"] = "application/json; charset=UTF-8"
        req = urllib.request.Request(url, data=body, headers=headers, method=method)
        try:
            with self.opener.open(req, timeout=timeout) as resp:
                raw = resp.read().decode(errors="replace")
                try:
                    payload = json.loads(raw)
                except json.JSONDecodeError:
                    payload = raw
                if isinstance(payload, dict) and "sessionkey" in payload:
                    self.sessionkey = payload["sessionkey"]
                return resp.status, payload
        except urllib.error.HTTPError as e:
            raw = e.read().decode(errors="replace")
            try:
                payload = json.loads(raw)
            except json.JSONDecodeError:
                payload = raw
            return e.code, payload

    def login(self) -> None:
        status, info = self.call("GET", "/getBasicInformation")
        if status != 200 or not isinstance(info, dict):
            raise SystemExit(f"Cannot reach router basic info: HTTP {status} {info!r}")
        print(
            f"Router: {info.get('ModelName')}  firmware={info.get('SoftwareVersion')}"
        )
        self.call("GET", "/getRSAPublickKey")
        status, result = self.call(
            "POST",
            "/UserLogin",
            {
                "Input_Account": self.user,
                "Input_Passwd": base64.b64encode(self.password.encode()).decode(),
                "currLang": "en",
                "RememberPassword": 0,
                "SHA512_password": False,
            },
        )
        if status != 200 or not isinstance(result, dict) or result.get("result") != "ZCFG_SUCCESS":
            raise SystemExit(f"Login failed: HTTP {status} {result!r}")
        print(f"Logged in as {result.get('loginAccount')} (level={result.get('loginLevel')})")


def main_ssid(objects: list, band_substr: str):
    for obj in objects:
        if obj.get("MainSSID") and obj.get("wlEnable") and band_substr in obj.get("band", ""):
            return obj
    return None


def summarize_radio(obj: dict) -> str:
    return (
        f"band={obj.get('band')} channel={obj.get('channel')} "
        f"auto={obj.get('AutoChannelEnable')} bw={obj.get('bandwidth')} "
        f"enable={obj.get('wlEnable')}"
    )


def enable_wireless_logging(client: RouterClient, apply: bool) -> None:
    status, logset = client.call("GET", "/cgi-bin/DAL?oid=logset")
    if status != 200 or not isinstance(logset, dict) or not logset.get("Object"):
        raise SystemExit(f"logset read failed: {status} {logset!r}")
    obj = dict(logset["Object"][0])
    print(f"Wireless logging currently: {obj.get('Wireless')}")
    if obj.get("Wireless") is True:
        print("Wireless logging already enabled.")
        return
    if not apply:
        print("Dry-run: would set Wireless=true on logset.")
        return
    obj["Wireless"] = True
    status, result = client.call("PUT", "/cgi-bin/DAL?oid=logset", obj)
    if status != 200 or not isinstance(result, dict) or result.get("result") != "ZCFG_SUCCESS":
        raise SystemExit(f"logset PUT failed: {status} {result!r}")
    print("Wireless logging enabled.")


def pin_5ghz(client: RouterClient, channel: int, bandwidth: str, apply: bool) -> None:
    status, wlan = client.call("GET", "/cgi-bin/DAL?oid=wlan")
    if status != 200 or not isinstance(wlan, dict) or not wlan.get("Object"):
        raise SystemExit(f"wlan read failed: {status} {wlan!r}")

    obj24 = main_ssid(wlan["Object"], "2.4")
    obj5 = main_ssid(wlan["Object"], "5")
    if not obj5:
        raise SystemExit("Could not find enabled main 5 GHz SSID object (Index usually 5).")

    if obj24:
        print("2.4 GHz (unchanged by this tool):", summarize_radio(obj24))
    print("5 GHz before:", summarize_radio(obj5))

    already = (
        obj5.get("channel") == channel
        and obj5.get("AutoChannelEnable") is False
        and str(obj5.get("bandwidth", "")).startswith(bandwidth)
    )
    if already:
        print("5 GHz already matches requested channel/bandwidth.")
        return

    if not apply:
        print(
            f"Dry-run: would set 5 GHz to channel={channel}, bandwidth={bandwidth} MHz, auto=off."
        )
        return

    # Mirror the web UI doWifiApply advance payload (keeps SSID/security fields intact).
    put = {
        "oneSsidEnable": obj5.get("oneSsidEnable", True),
        "Index": obj5.get("Index", 5),
        "wlEnable": obj5.get("wlEnable", True),
        "X_ZYXEL_Multicast_Fwd": obj5.get("X_ZYXEL_Multicast_Fwd", True),
        "SSID": obj5["SSID"],
        "upRate": obj5.get("upRate", 0),
        "downRate": obj5.get("downRate", 0),
        "MaxAssociatedDevices": obj5.get("MaxAssociatedDevices", 32),
        "wlHide": obj5.get("wlHide", False),
        "secMode": 255,
        "wpaMode": "wpa2wpa3psk"
        if "WPA3" in str(obj5.get("SecurityMode", ""))
        else "wpa2psk",
        "AutoGenPSK": obj5.get("AutoGenPSK", True),
        "psk_value": obj5.get("PskDisplay") or obj5.get("AutoGenPSKValue") or "",
        "encryp": obj5.get("encryp", "aes"),
        "RekeyingInterval": obj5.get("RekeyingInterval", 3600),
        "X_ZYXEL_Preauth": obj5.get("X_ZYXEL_Preauth", False),
        "X_ZYXEL_ReauthInterval": obj5.get("X_ZYXEL_ReauthInterval", 36000),
        "RadiusServerIPAddr": obj5.get("RadiusServerIPAddr", "0.0.0.0"),
        "RadiusServerPort": obj5.get("RadiusServerPort", 1812),
        "RadiusSecret": obj5.get("RadiusSecret", ""),
        "div_wifiAdvance": True,
        "channel": channel,
        "bandwidth": str(bandwidth),
        "extcha": "0",
        "subnetObjAction": "",
        "div_wifiSubnet": False,
        "mlo_change": False,
    }

    status, result = client.call("PUT", "/cgi-bin/DAL?oid=wlan", put)
    if status != 200 or not isinstance(result, dict) or result.get("result") != "ZCFG_SUCCESS":
        raise SystemExit(f"wlan PUT failed: HTTP {status} {result!r}")
    print("wlan PUT:", result.get("result"))

    status, check = client.call("GET", "/cgi-bin/Wireless?action=WlCheck")
    print("WlCheck:", check)

    print("Waiting 15s for radio apply / mesh sync...")
    time.sleep(15)

    status, wlan = client.call("GET", "/cgi-bin/DAL?oid=wlan")
    obj5 = main_ssid(wlan["Object"], "5")
    print("5 GHz after:", summarize_radio(obj5) if obj5 else "missing")

    status, steer = client.call("GET", "/cgi-bin/SteeringStatus_handle")
    if status == 200 and isinstance(steer, list) and steer:
        print("Controller radios:", steer[0].get("result_ctl"))
        print("Extender radios:", steer[0].get("result_ext"))


def main() -> int:
    repo_root = Path(__file__).resolve().parents[1]
    load_dotenv(repo_root / ".env")
    load_dotenv(Path.cwd() / ".env")

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Actually change logset + 5 GHz channel (default is dry-run)",
    )
    parser.add_argument("--host", default=os.environ.get("ROUTER_HOST", "192.168.1.1"))
    parser.add_argument("--user", default=os.environ.get("ROUTER_USER", "admin"))
    parser.add_argument("--channel", type=int, default=int(os.environ.get("CHANNEL", "36")))
    parser.add_argument(
        "--bandwidth",
        default=os.environ.get("BANDWIDTH", "80"),
        help='API bandwidth token: 20, 40, 80, or 160',
    )
    args = parser.parse_args()

    password = os.environ.get("PASSWORD", "")
    if not password:
        print("Set PASSWORD in .env or the environment.", file=sys.stderr)
        return 2

    if args.apply:
        print("APPLY mode: will modify router settings.")
    else:
        print("Dry-run mode (pass --apply to change settings).")

    client = RouterClient(args.host, args.user, password)
    client.login()
    enable_wireless_logging(client, apply=args.apply)
    pin_5ghz(client, channel=args.channel, bandwidth=args.bandwidth, apply=args.apply)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
