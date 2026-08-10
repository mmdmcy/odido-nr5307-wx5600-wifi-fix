# Diagnosis notes (sanitized)

How the NR5307 + WX5600 iPhone flap was isolated using the local HTTPS API. No personal network identifiers.

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

## Smoking-gun pattern

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

When the WX5600 is removed from the mesh, steering pressure drops and the phone stays up—matching user A/B tests.

## Why band steering + DFS/160 is a bad combo for some iPhones

Band steering wants the phone on 5 GHz. If the phone will not complete BSS transition onto the current 5 GHz BSS (DFS CAC quirks, 160 MHz, PMF/WPA3-transition edge cases, etc.), rejects accumulate. Controllers that escalate from “ask” (11v) to “force” (disassoc) produce exactly the Wi‑Fi ↔ cellular behaviour users report.

Pinning 5 GHz to **non-DFS channel 36 @ 80 MHz** made the observed iPhone **accept** 5 GHz (high PHY rate, stable association, DHCP spam stopped).

## Apply payload shape (5 GHz)

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

## What we did *not* need

- Factory reset of the WX5600  
- Moving the extender solely because backhaul RSSI was ~−69 dBm (backhaul still negotiated ~1.7 Gbps and the phone failed *next to* the gateway)  
- Splitting 2.4/5 SSIDs or disabling EasyMesh (those remain nuclear options if channel pinning is not enough)  

## Revert

Restore auto channel / previous bandwidth via the same Wireless UI or by adapting `scripts/fix_5ghz_channel.py`.
