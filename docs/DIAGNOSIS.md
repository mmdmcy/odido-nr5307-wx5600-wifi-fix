# Diagnosis notes

How the NR5307 + WX5600 iPhone flap was isolated using the local HTTPS API.

## Management surface

| Interface | Notes |
|-----------|--------|
| SSH / Telnet | Closed on the observed Odido build |
| `https://192.168.1.1/` | SPA web UI |
| JSON API | Same origin as the UI |

Useful unauthenticated probe:

```http
GET /getBasicInformation
```

Example shape:

```json
{
  "result": "ZCFG_SUCCESS",
  "ModelName": "NR5307",
  "SoftwareVersion": "V1.00(ACJG.1)NR53_b17D0430",
  "RemoAddr_Type": "LAN"
}
```

### Login

1. `GET /getRSAPublickKey` (may return `"RSAPublicKey":"None"` on HTTPS).
2. `POST /UserLogin` with JSON:

```json
{
  "Input_Account": "admin",
  "Input_Passwd": "<base64(password)>",
  "currLang": "en",
  "RememberPassword": 0,
  "SHA512_password": false
}
```

3. Keep the `Session` cookie. Mutating `/cgi-bin/…` calls need `sessionkey=<n>` from the login (or later) JSON.

On HTTPS with `RSAPublicKey: None`, the SPA does **not** AES-wrap the login body.

### Read endpoints used

| Path | Purpose |
|------|---------|
| `GET /cgi-bin/DAL?oid=wifi_easy_mesh` | EasyMesh on/off, controller role |
| `GET /cgi-bin/DAL?oid=wlan` | SSIDs, channel, bandwidth, security |
| `GET /cgi-bin/DAL?oid=wifi_others&DalGetOneObject=y&Index=5` | 5 GHz “others” (incl. DFS inactive list) |
| `GET /cgi-bin/DAL?oid=lanhosts` | Clients: band, connected AP, RSSI, active |
| `GET /cgi-bin/SteeringStatus_handle` | 11v steer attempts, Accept/Reject/Waiting |
| `GET /cgi-bin/WLANTable_handle` | Station tables + EasyMesh topology |
| `GET /cgi-bin/Wireless?oid=RDM_OID_WIFI_QSTEER` | QSTEER enable (was off in the observed case) |
| `GET /cgi-bin/DAL?oid=logset` | Syslog category toggles |
| `GET /cgi-bin/Log?action=GET_LOG&oid=RDM_OID_LOG_CLASSIFY&iid=[1,0,0,0,0,0]` | System log lines |

WX5600 on the LAN also answers `GET /getBasicInformation` (model `WX5600-T0`).

---

## Failure mode A — gateway 2.4 → 5 on DFS / 160 MHz

### Smoking-gun pattern

From `SteeringStatus_handle` → `result_record` entries like:

```text
steer: 11v
from: <gateway-2.4-bssid>
to:   <gateway-5-bssid>
result: Reject
```

repeating about once per minute for the same station, while:

- `result_sta` shows that station on 2.4 GHz, `support11v: YES`, `STEERABLE` (sometimes `IN_STEERING`)
- `wlan` shows 5 GHz **AutoChannelEnable** with a **DFS** channel and **160 MHz**
- Topology shows MAP **R3** controller + **R2** agent (interop smell; not proven root cause alone)
- DHCP syslog lines for that client fire many times per minute during the flap

When the WX5600 is removed from the mesh, steering pressure drops and the phone stays up.

### Why band steering + DFS/160 is a bad combo for some iPhones

Band steering wants the phone on 5 GHz. If the phone will not complete BSS transition onto the current 5 GHz BSS (DFS CAC quirks, 160 MHz, PMF/WPA3-transition edge cases, etc.), rejects accumulate. Controllers that escalate from “ask” (11v) to “force” (disassoc) produce exactly the Wi‑Fi ↔ cellular behaviour users report.

### Workaround that worked (mode A)

Pinning 5 GHz to **non-DFS channel 36 @ 80 MHz** allowed the affected iPhone to associate on gateway 5 GHz stably (high PHY rate; DHCP renew spam stopped). EasyMesh left enabled.

---

## Failure mode B — WiFi-punt 5 → 2.4 (still open)

Observed the day after mode A was mitigated, with **ch 36 / 80 MHz still in place**.

### Smoking-gun pattern

```text
steer: 11v
from: <extender-5-bssid>
to:   <extender-2.4-bssid>
result: Reject   (many) / Accept (rare)
```

while:

- Client is associated to the **WX5600 5 GHz** BSS (not the gateway)
- Station RSSI on that 5 GHz BSS is weak (example ~−70 dBm)
- Steering status RSSI fields look “sick” / nonsensical for the target
- DHCP renew spam for that client during the flap
- Another iPhone on **gateway 5 GHz** can stay fine at the same time

So this is **not** “phone can’t join DFS 5 GHz”. The controller is trying to **push a weak 5 GHz client down to 2.4 GHz on the same WiFi-punt**. The iPhone rejects most of those BSS transitions; the association flaps; iOS uses cellular.

Temporary client-side relief (Airplane Mode toggle) can reassociate cleanly for a short time, then mode B returns when the phone is again on the punt with mediocre 5 GHz RSSI.

### Sticky AP (why two identical phones can differ upstairs)

Observed with both people **upstairs** and the WiFi-punt **downstairs**:

- One iPhone 13 stayed on the **gateway** 5 GHz (strong RSSI, high PHY rate) → fine after the mode A channel pin.
- The other iPhone 13 had been associated to the **extender** 5 GHz (weak RSSI upstairs) and kept getting **punt 5 → punt 2.4** Reject steers → flap / fall back to cellular.

So mode B is not “her model vs his model.” Same 11v / STEERABLE clients; different **which BSS they stuck to**. iPhones are often sticky roamers; EasyMesh is supposed to AP-steer them to the nearer box, but here band steering on the weak punt link dominates.

Re-check with `lanhosts` (`X_ZYXEL_ConnectedAP` / Neighbor) and `SteeringStatus_handle` (`from` / `to` BSSIDs) before assuming location = associated AP.

### Why channel pinning does not fix mode B

Mode A’s fix makes the **5 GHz BSS joinable**. Mode B assumes 5 GHz is already joinable and still steers **away** from it when the controller thinks 2.4 is “better” for a weak client. That policy lives inside EasyMesh / MPro Mesh band steering, not in the channel plan.

### What is *not* exposed on these firmwares

| Desired control | Observed |
|-----------------|----------|
| Disable band steering only | No dedicated toggle while EasyMesh stays on |
| Per-client “never steer” / sticky band | Not found in DAL / Wireless OIDs used so far |
| QSTEER as the culprit | `RDM_OID_WIFI_QSTEER` was already **off** |
| Separate 2.4 / 5 SSIDs with EasyMesh on | Zyxel docs: same-SSID / shared settings are forced when Mesh is enabled |

Zyxel’s own Mesh help text states MPro Mesh / EasyMesh includes **AP steering** and **band steering**, and that enabling Mesh copies main 2.4 settings onto 5 GHz.

---

## Candidate solutions for mode B (research only — not applied here)

Ordered from least to most invasive. None of these has been validated on this setup yet.

### 1. Wait for Odido firmware

Odido community staff have acknowledged that current NR5307 firmware steers devices onto 2.4 GHz **too aggressively**, and that a newer build improves this but was “not quite ready” at the time of those posts. Example thread: [NR5307 band-steering keeps my TV off 5GHz](https://community.odido.nl/klik-klaar-592/nr5307-band-steering-keeps-my-tv-off-5ghz-band-372278).

This is the only option that keeps full EasyMesh + single SSID **and** addresses the vendor policy. Trade-off: timeline is ISP-controlled.

### 2. Disable EasyMesh, then split 2.4 / 5 SSIDs

Documented pattern on other ISP-branded Zyxel boxes (and Odido community tips):

1. Network → Wireless → **MESH / EasyMesh** → **Off**
2. Untick **keep 2.4 and 5 the same**
3. Give bands different SSIDs (e.g. `Home` / `Home-5G`)
4. Put phones on the 5 GHz SSID only; leave IoT on 2.4

**Pros:** Stops EasyMesh band steering; lets you force phones onto 5 GHz.  
**Cons:** Breaks (or changes) how the WX5600 is managed as a mesh agent; may need re-pairing / wired AP mode / coverage redesign. Highest risk to “it just works” whole-home Wi‑Fi.

### 3. Keep NR5307 as modem-only; third-party mesh/AP

Odido users who stay unhappy with onboard Wi‑Fi often: disable Wi‑Fi on the NR5307 (or ignore it), Ethernet to a Deco / UniFi / etc. mesh.  
**Pros:** Escapes Odido steering entirely.  
**Cons:** Extra hardware; not a “settings tweak”.

### 4. WX5600 placement / backhaul quality

Mode B showed weak ~−70 dBm on extender 5 GHz. Better punt placement (or **wired Ethernet backhaul** to the WX5600 if cabling exists) can raise 5 GHz RSSI so the controller stops preferring 2.4 — *if* the trigger is purely RSSI. Unproven; does not remove aggressive steering code.

### 5. Soft experiments (low confidence)

- Try another non-DFS 5 GHz channel (40 / 44 / 48) if 36 is crowded downstairs  
- Lower 2.4 GHz TX power so 2.4 looks worse than weak 5 GHz (speculative; can hurt IoT)  
- Client Airplane Mode / forget-and-rejoin (temporary only)

These do **not** remove the steering engine.

### What not to do first

- Factory-reset the WX5600  
- Publish PSKs, serials, or full client MAC lists  
- Assume mode A’s channel pin “failed” — check `SteeringStatus_handle` direction (`from`/`to` BSSIDs) before changing channel again

---

## Configuration backup / restore (possible — not performed)

Yes. Stock Zyxel NR5307 firmware exposes **Maintenance → Backup/Restore**:

- **Backup** — download the current config file to a PC  
- **Restore** — upload a previously saved config (device typically reboots)  
- **Reset / Soft-Reset** — factory defaults (avoid unless intentional)

Official overview: [Zyxel NR Indoor Series — Backup/Restore](https://service-provider.zyxel.com/compact-help/NR-Indoor-Series/NR_Indoor_V1.00/h_Maintenance_Reboot.html) and the [NR5307 User’s Guide](https://spdl.zyxel.com/NR5307/user_guide/NR5307_Users_guide_01.pdf) (Backup/Restore chapter).

**Recommendations before any mode-B experiment:**

1. Take a Backup while the network is in a known-good (or known-current) state.  
2. Store the file **offline / private** — config backups usually contain Wi‑Fi PSKs and other secrets. **Do not commit them to git.**  
3. Prefer restore over factory reset if an experiment goes sideways.  
4. Confirm Odido’s build still exposes the same menu (ISP skins sometimes rename paths; function is standard on Zyxel).

This repo has **not** automated backup via API yet; UI download is enough.

---

## Apply payload shape (5 GHz) — mode A workaround

The web UI `doWifiApply` path PUTs `/cgi-bin/DAL?oid=wlan` with `div_wifiAdvance: true` and fields including `channel`, `bandwidth` (`"80"` not `"80MHz"`), `extcha`, plus existing SSID/security fields so nothing else is wiped.

Then:

```http
GET /cgi-bin/Wireless?action=WlCheck
```

Single-object PUT (not a one-element array) matched the SPA. Some PUT shapes returned HTTP 403 or `ZCFG_NO_SUCH_PARAMETER`; the GUI-shaped object returned `ZCFG_SUCCESS` on the firmware tested.

### Wireless logging

```http
PUT /cgi-bin/DAL?oid=logset
```

with the existing logset object and `"Wireless": true`.

## What we did *not* need for mode A

- Factory reset of the WX5600  
- Moving the extender solely because backhaul RSSI was ~−69 dBm (backhaul still negotiated ~1.7 Gbps and the phone failed *next to* the gateway)  
- Splitting 2.4/5 SSIDs or disabling EasyMesh (those remain options for **mode B**)

## Revert (mode A)

Restore auto channel / previous bandwidth via the same Wireless UI or by adapting `scripts/fix_5ghz_channel.py`.
