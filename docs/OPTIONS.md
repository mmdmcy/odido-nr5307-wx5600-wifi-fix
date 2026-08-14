# Options after mode A (channel pin)

Research notes for **mode B** (WiFi-punt 5 GHz → 2.4 GHz 11v loop) and for **gateway-only 2.4 GHz → 5 GHz 11v** that can continue after the punt is unplugged. Nothing in this file was applied on the observed NR5307 except the earlier mode A pin (see [DIAGNOSIS.md](DIAGNOSIS.md)).

Take a **config backup** before any of (2) or (3). Do not factory-reset the WX5600 as a first step. Do not commit backups, PSKs, or client MAC lists.

## What you cannot have at once on stock Odido firmware

| Goal | EasyMesh **on** + WX5600 | EasyMesh **off** | Third-party mesh, Odido Wi‑Fi off |
|------|--------------------------|------------------|-----------------------------------|
| Downstairs coverage from the WX5600 | Yes | **No** — punt is not a standalone AP | N/A (punt unplugged) |
| Stop 11v band-steering kicks | **No** | Yes (then split SSIDs) | Yes |
| One SSID, both floors, phones pick nearer AP | Yes (but steering is bundled) | Not with the WX5600 | Yes (vendor mesh / client roaming) |

Odido community staff have said, on this GUI, **band steering is the Mesh switch**. QSTEER was already **off** in the observed case. There is still no “mesh coverage on, band steering off” control. Zyxel docs: EasyMesh **requires** identical 2.4 / 5 SSIDs (band steering) and a shared SSID for AP steering.

The WX5600-T0 on ISP firmware is a **mesh agent only**. Odido: WiFi-punten only work through the Zyxel mesh. Community: wired to a controller it clones SSIDs; without a controller it will not take a manual SSID. Unplugging it stops **punt** 5→2.4 steers. It does **not** stop **gateway** 2.4→5 steers if a dual-band client is stuck on 2.4.

## 1. Complain to Odido (free, no config change)

Legitimate reproduction:

- WiFi-punt **in** → iPhone Wi‑Fi ↔ cellular / FaceTime drops; Steering Status shows 11v **Reject** loops.
- WiFi-punt **out** → that **punt** loop stops; downstairs coverage dies.
- After mode A (5 GHz ch 36 / 80 MHz), a phone **next to the gateway** can still flap on **gateway 2.4 → gateway 5** Reject/Timeout, DHCP renew spam, `steer_status: UNFRIENDLY`.

Ask, in order: firmware that softens steering; a band-steering toggle with mesh still on; how the WiFi-punt is supposed to work without iPhones dropping; credit / take the punt back if it cannot do both.

Staff have acknowledged aggressive NR5307 2.4 GHz steering ([example](https://community.odido.nl/klik-klaar-592/nr5307-band-steering-keeps-my-tv-off-5ghz-band-372278)). Timeline is ISP-controlled. They will not fund a third-party mesh.

## 2. Disable EasyMesh, then split 2.4 / 5 SSIDs (free, kills the WX5600)

Documented on Odido NR5307 / other Zyxel ISP boxes ([community walkthrough](https://community.odido.nl/klik-klaar-592/klik-klaar-wifi-slecht-bekabeld-wel-goed-375208); same pattern on other Zyxel meshes).

1. Maintenance → **Backup/Restore**.
2. Network → Wireless → **MESH / EasyMesh** → **Off** → Apply (Wi‑Fi restarts ~40 s).
3. Untick **keep 2.4 and 5 the same**.
4. Distinct names, e.g. `Home` (2.4) and `Home-5G` (5). Same password is fine.
5. Phones: forget the old network; join **only** the 5 GHz SSID; disable Auto-Join on 2.4.
6. Leave 2.4 up for 2.4-only clients (older consoles, some IoT, some desktops).

**Original Nintendo Switch (Switch 1) is 2.4 GHz only.** It cannot use `Home-5G`. It needs the 2.4 SSID, and without a downstairs AP that signal is whatever the NR5307 can push through the floor. Use **WPA2** or **WPA2/WPA3 mixed**, not WPA3-only, or the Switch may refuse the network.

**Why this should stop the iPhone glitch:** 11v band steering needs one SSID on both radios. Split names → nothing to steer to. Community reports on this modem: flap stopped after Mesh off + phones on the 5 GHz name only. **Not yet applied** on the setup that produced these notes.

**API (GUI-equivalent, not applied here):**

```http
PUT /cgi-bin/DAL?oid=wifi_easy_mesh
```

JSON object (not an array), fields from the current GET:

```json
{
  "EasyMeshEnable": false,
  "Controller_mode": 1
}
```

Include `BH_band` if the GET returned it. The SPA then waits ~40 s and calls `GET /cgi-bin/Wireless?action=WlCheck`. Splitting SSIDs is the existing `doWifiApply` PUT to `oid=wlan` with `oneSsidEnable: false` and a different `SSID` per band `Index`.

**Revert:** restore the backup, or turn EasyMesh on again (WX5600 will only work as an agent once mesh is on).

## 3. Third-party mesh behind the NR5307 (buy hardware; no floor cable)

**Full replacement of Odido Wi‑Fi + WX5600, not of the 5G modem.** Klik&Klaar stays on the NR5307. No official bridge / IP passthrough is required (Odido has said they will not ship bridge mode). A **dumb AP / mesh in Access Point mode** is enough: same LAN, NR5307 keeps NAT and DHCP.

```text
NR5307  =  5G modem + router, Wi‑Fi OFF
   short Ethernet in the same room
     →  mesh unit A  ←—— wireless backhaul ——→  mesh unit B downstairs
```

No Ethernet **between floors**. Same idea as the WX5600’s wireless backhaul. Unplug the WX5600. Do not run Odido Wi‑Fi and the third-party mesh at the same time.

**Access Point mode, not router mode** (avoid double NAT; worse for calls and games).

Consumer 2-packs (TP-Link Deco and similar) do this. A current Wi‑Fi 6 2-pack is often €100+. Older used 2-packs (e.g. Deco M5/M4) are commonly much cheaper and are enough for Switch 1 + phone calls. Place unit B in the room that needs 2.4 GHz (Switch) and 5 GHz (phones).

This **does** address iPhone 11v flaps (EasyMesh is gone) and downstairs coverage without a cable. It does **not** fix a weak or jittery 5G WAN (whole house including Ethernet would hitch). A wireless hop is not as good as a wired backhaul.

Do not flash OpenWrt onto an ISP-loaned WX5600/NR5307. Upstream OpenWrt support for WX5600-T0 exists (MediaTek MT7986) but install is serial / vendor-specific and the hardware is typically **bruikleen**.

Writing an access point from scratch is not realistic: use vendor firmware or OpenWrt `hostapd` on hardware you own.

## 4. Placement / wired backhaul to the WX5600

May raise extender 5 GHz RSSI so mode B fires less often. Does **not** remove the steering engine. Many homes cannot run a cable downstairs; the observed WX5600 was in **repeater** (wireless backhaul) mode.

## 5. Soft / client-only (temporary)

Airplane Mode, forget-and-rejoin, stand next to the gateway. Often fails once `steer_status` is **UNFRIENDLY** or the phone sticks to 2.4 on a shared SSID. Does not turn the engine off.

## 5G WAN vs Wi‑Fi flap

Indoor FWA can be “fair” (LTE + NR-NSA, RSRP in the −100 dBm class) and still jitter. That is **not** the iPhone 4G icon loop.

- Only phones / only some rooms / FaceTime / Wi‑Fi ↔ cellular → steering / association.  
- TV, Ethernet PC, and phones all die together → cellular WAN; moving/rotating the NR5307 or an ISP ticket, not a new mesh.

## Nintendo Switch 1

2.4 GHz only. A 5 GHz-only SSID plan leaves it offline. Downstairs it needs a **local 2.4 GHz AP** (WX5600 with mesh on, or third-party unit B). Unplugging the punt makes downstairs Switch performance worse by design.

## Recommended order

1. Backup; Odido ticket with punt-in vs punt-out and Steering Status direction.  
2. If downstairs can wait: **EasyMesh off + split SSIDs**; phones on 5 GHz only.  
3. If downstairs + phones both matter and no floor cable: **third-party 2-pack in AP mode**, Odido Wi‑Fi off, WX5600 unplugged (used kit is fine).  
4. Do not mix Zyxel EasyMesh and a third-party mesh on the same SSID.
