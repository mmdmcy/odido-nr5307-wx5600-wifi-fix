# Odido NR5307 + WX5600: iPhone Wi‑Fi ↔ cellular flap fix

Workaround for **Odido Klik&Klaar** setups (Zyxel **NR5307** + **WX5600-T0** EasyMesh) where an **iPhone** repeatedly drops Wi‑Fi and falls back to cellular—even next to the main router—while the mesh WiFi-punt is online.

Unplugging the WX5600 often stops the problem. This repo documents a **mesh-preserving** fix instead: pin 5 GHz away from a hostile DFS / 160 MHz channel, and optionally enable wireless logging.

> Not affiliated with Odido or Zyxel. Use at your own risk.

## Who this is for

- ISP: Odido (Netherlands), Klik&Klaar 5G home internet
- Main unit: Zyxel NR5307 (example firmware: `V1.00(ACJG.1)NR53_b17D0430`)
- Mesh / WiFi-punt: Zyxel WX5600-T0 (example firmware: `V5.70(ACDW.0)b13`)
- Shared-SSID EasyMesh / MPro Mesh
- Symptom: iPhone Wi‑Fi ↔ cellular looping that goes away when the WiFi-punt is unplugged

Laptops often stay stable. iPhones are common targets because they advertise **802.11v** and show up as **STEERABLE** in the router’s steering status.

## Root cause

With the WX5600 joined to the mesh, the NR5307 runs **EasyMesh band steering** (802.11v BSS Transition).

Typical pattern:

1. 5 GHz is on **auto**, lands on a **DFS** channel (e.g. 64) at **160 MHz**
2. The controller repeatedly steers the iPhone **2.4 GHz → 5 GHz**
3. The iPhone **rejects** those steers
4. The Wi‑Fi association flaps; iOS falls back to cellular

Zyxel documents that band/AP steering may **drop** clients to move them. Odido community reports describe similar NR5307 steering behaviour.

On these firmwares there is usually **no separate “disable band steering only”** control while keeping a single mesh SSID.

## The fix

Keep EasyMesh and the WiFi-punt. Change only 5 GHz:

| Setting | Example before | Recommended after |
|---------|----------------|-------------------|
| 5 GHz channel | Auto → DFS **64** | Fixed **36** (non-DFS) |
| 5 GHz width | **160 MHz** | **80 MHz** |
| Wireless syslog | Off | **On** (optional, for diagnosis) |

2.4 GHz is left alone. The extender normally **follows** the controller’s 5 GHz channel through EasyMesh, so roaming across the home should keep working on the same SSID.

### Option A — Router web UI

1. Open `https://192.168.1.1/` (accept the certificate warning).
2. Log in as `admin` (password on the device label / Odido documentation).
3. Optionally enable **Wireless** under log settings (Maintenance → Log Setting; labels vary).
4. Open **Network → Wireless** advanced / channel settings for **5 GHz**.
5. Disable **auto channel**, set channel **36**, bandwidth **80 MHz**, apply.
6. Confirm the WiFi-punt’s 5 GHz also shows channel **36** (Steering Status / WLAN station pages help).

> With EasyMesh enabled, some channel controls are greyed out in the UI. If so, use Option B or contact Odido about a firmware/steering fix.

### Option B — Script (local API)

```bash
cp .env.example .env
# set PASSWORD= to your router admin password

# Dry run (default): show current 5 GHz config only
python3 scripts/fix_5ghz_channel.py

# Apply: enable Wireless logging + pin 5 GHz to ch 36 / 80 MHz
python3 scripts/fix_5ghz_channel.py --apply
```

Requires Python 3.9+, LAN access to the router, and no third-party packages.

More API detail: [docs/DIAGNOSIS.md](docs/DIAGNOSIS.md).

## How to confirm it’s the same bug

In the router UI (**System Monitor → Steering Status**), check the affected iPhone:

- Repeated **11v** steers from 2.4 → 5 GHz with result **Reject**
- Client stuck on **2.4 GHz** near the gateway despite being dual-band
- Problem appears **only** while the WX5600 is in the mesh
- 5 GHz is on a **DFS** channel (e.g. 52–64, 100–140), often at **160 MHz**

## Notes

- Do not publish router passwords, Wi‑Fi PSKs, device serials, or full client MAC lists.
- Factory-resetting the WX5600 is a poor first troubleshooting step and is not required for this workaround.
- Channel **36 / 80 MHz** is a practical default in the Netherlands; another non-DFS channel may be better if 36 is crowded.

## License

MIT — see [LICENSE](LICENSE).
