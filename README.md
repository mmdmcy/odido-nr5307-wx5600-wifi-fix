# Odido NR5307 + WX5600: iPhone Wi‑Fi ↔ cellular flap

Workarounds and diagnosis for **Odido Klik&Klaar** setups (Zyxel **NR5307** + **WX5600-T0** EasyMesh) where an **iPhone** repeatedly drops Wi‑Fi and falls back to cellular while the mesh WiFi-punt is online.

> Not affiliated with Odido or Zyxel. Use at your own risk.

## Who this is for

- ISP: Odido (Netherlands), Klik&Klaar 5G home internet
- Main unit: Zyxel NR5307 (example firmware: `V1.00(ACJG.1)NR53_b17D0430`)
- Mesh / WiFi-punt: Zyxel WX5600-T0 (example firmware: `V5.70(ACDW.0)b13`)
- Shared-SSID EasyMesh / MPro Mesh
- Symptom: iPhone Wi‑Fi ↔ cellular looping that improves when the WiFi-punt is unplugged (or after a short Airplane Mode reset)

Laptops often stay stable. iPhones are common targets because they advertise **802.11v** and show up as **STEERABLE** in the router’s steering status.

## Two failure modes

There are at least **two** EasyMesh steering loops. Check **System Monitor → Steering Status** (`from` / `to` BSSIDs) before changing anything.

| Mode | Steer direction | Typical radio state | Status |
|------|-----------------|---------------------|--------|
| **A** | Gateway **2.4 → 5** | 5 GHz **auto DFS** (e.g. 64) @ **160 MHz** | Mitigated by pinning **ch 36 / 80 MHz** |
| **B** | WiFi-punt **5 → 2.4** | 5 GHz already fixed non-DFS; client on **extender** with weak 5 GHz RSSI | **Open** — channel pin does not stop it |

On these firmwares there is usually **no separate “disable band steering only”** control while keeping a single mesh SSID. QSTEER was already off in the observed case; steering still comes from EasyMesh.

Odido community staff have acknowledged overly aggressive 2.4 GHz steering on current NR5307 firmware ([example thread](https://community.odido.nl/klik-klaar-592/nr5307-band-steering-keeps-my-tv-off-5ghz-band-372278)).

## Mode A fix (mesh-preserving)

Keep EasyMesh and the WiFi-punt. Change only 5 GHz:

| Setting | Example before | Recommended after |
|---------|----------------|-------------------|
| 5 GHz channel | Auto → DFS **64** | Fixed **36** (non-DFS) |
| 5 GHz width | **160 MHz** | **80 MHz** |
| Wireless syslog | Off | **On** (optional, for diagnosis) |

2.4 GHz is left alone. The extender normally **follows** the controller’s 5 GHz channel through EasyMesh.

### Option A — Router web UI

1. Open `https://192.168.1.1/` (accept the certificate warning).
2. Log in as `admin` (password on the device label / Odido documentation).
3. Optionally enable **Wireless** under log settings (Maintenance → Log Setting; labels vary).
4. Open **Network → Wireless** advanced / channel settings for **5 GHz**.
5. Disable **auto channel**, set channel **36**, bandwidth **80 MHz**, apply.
6. Confirm the WiFi-punt’s 5 GHz also shows channel **36**.

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

## Mode B — still researching

After mode A is fixed, a second iPhone (or the same phone) can still flap while associated to the **WX5600** — including when the person is **upstairs**, if the phone stayed sticky on the downstairs punt. Steering Status then shows repeated **11v Reject** from **extender 5 GHz → extender 2.4 GHz**, plus DHCP renew spam. Airplane Mode can help briefly; the loop often returns. Two identical iPhones can disagree simply because one latched onto the gateway and the other onto the punt.

Candidate approaches (details and trade-offs in [docs/DIAGNOSIS.md](docs/DIAGNOSIS.md)):

1. **Odido firmware** that softens band steering (best if you want to keep EasyMesh + one SSID)
2. **Disable EasyMesh**, then split 2.4 / 5 SSIDs (stops steering; may change how the WiFi-punt works)
3. **Third-party AP/mesh** behind the NR5307 used as modem-only
4. Better **WiFi-punt placement** or wired backhaul (may raise 5 GHz RSSI; does not remove the steering engine)

**Before trying (2):** take a configuration backup (see below). Do not factory-reset as a first step.

## How to confirm which bug you have

In the router UI (**System Monitor → Steering Status**), for the flapping iPhone:

**Mode A**

- Repeated **11v** steers **2.4 → 5** on the **gateway**, result **Reject**
- Client stuck on gateway **2.4 GHz**
- 5 GHz on a **DFS** channel, often **160 MHz**

**Mode B**

- Repeated **11v** steers **5 → 2.4** on the **WiFi-punt**, mostly **Reject**
- Client on **extender 5 GHz** with mediocre RSSI
- 5 GHz may already be pinned to a non-DFS channel

## Configuration backup

Yes — use **Maintenance → Backup/Restore** on the NR5307 to download a config file before invasive experiments, and restore it if something goes wrong. Treat the file as **secret** (it can contain Wi‑Fi passwords); do not put it in git. See [docs/DIAGNOSIS.md](docs/DIAGNOSIS.md#configuration-backup--restore-possible--not-performed).

## Notes

- Do not publish router passwords, Wi‑Fi PSKs, device serials, or full client MAC lists.
- Factory-resetting the WX5600 is a poor first troubleshooting step.
- Channel **36 / 80 MHz** is a practical default in the Netherlands for mode A; another non-DFS channel may be better if 36 is crowded.

## License

MIT — see [LICENSE](LICENSE).
