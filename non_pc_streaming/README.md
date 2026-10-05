# Standalone mode: Frame sender and PC receiver

A Python OpenVR background client runs **on Frame**, reads Frame's own VR
runtime and sends controller data to the PC over UDP. No video, no PC
SteamVR. Verified live on Frame on 2026-10-04 (both controllers, every data
group).

The deployment steps are in the root README:
[Standalone mode](../README.md#standalone-mode). This page covers the network
choice, firewall and SSH details, cleanup and what happens underneath.

| File | Runs on | Purpose |
|---|---|---|
| `frame_sender.py` | Frame (or PC with `--desktop`/`--demo`) | samples controllers and sends FVR2 packets |
| `udp_pose.py` | PC | `UDPReader`: receives, validates, hands poses to the viewer |
| `deploy_sender.ps1` | PC | packages, uploads and runs the sender or probe over SSH |
| `vendor/` | Frame | unmodified pyopenvr + Valve's Linux ARM64 `libopenvr_api` (licenses, provenance) |

## Network: home Wi‑Fi or direct link?

On Frame, `ip -brief -4 addr` (LXTerminal) typically shows:

| Frame interface | What it is | Matching PC adapter |
|---|---|---|
| `wlan0` | Frame as a normal client of your home Wi‑Fi | the PC adapter on the same router subnet (it has a default gateway) |
| `wlanap` | Frame's own access point: the **direct link**, used by PC streaming together with Wi‑Fi | the PC adapter on the same subnet, with **no** default gateway (e.g. `Wi-Fi 6`) |
| `usb0` | networking over a USB cable, if connected | – |

| | Home Wi‑Fi (`wlan0`) | Direct link (`wlanap`) |
|---|---|---|
| Path | Frame → router → PC | Frame → PC, no router |
| Round trip (ping) | about 4 ms avg, up to 18 ms | about 1 ms avg, up to 5 ms |
| Delay variation (p99) | 4-6 ms in good runs, **130+ ms** in bad ones | about 3 ms in every run |
| Worst stall | up to about 190 ms (in 2 of 6 runs) | about 20-40 ms |
| Needs | both devices on the same router | the PC's streaming adapter connected to Frame (stayed up with PC SteamVR closed) |

**Use the direct link** when it is available. Both deliver every packet and
the same tracking rate; details in the
[benchmarks](../diagnostics/README.md#data-rate-and-timing-streaming-vs-standalone).
Addresses from DHCP can change; check again if a connection stops working.

### Ubuntu: no direct link yet

(2026-10-05, Ubuntu 26.04, kernel 7.0.) Frame's hotspot only uses 6 GHz, and
Linux disables every 6 GHz channel while the Wi‑Fi region is unset (`iw reg
get` shows `country 00`), so the adapter could not even see Frame. Setting the
region fixes that, now and after reboots:

```sh
sudo iw reg set US                                                              # now
echo 'options cfg80211 ieee80211_regdom=US' | sudo tee /etc/modprobe.d/cfg80211-regdom.conf  # at boot
```

(Use your own country code; undo with `sudo rm /etc/modprobe.d/cfg80211-regdom.conf`
and a reboot.) The adapter (`rtw89_8852cu`) then sees Frame's hotspot, but
joining still fails in the driver (`failed to insert STA entry for the AP
(error -22)`): Valve requires kernel 7.2 or newer for this adapter. Until
Ubuntu ships such a kernel, use home Wi‑Fi for both streaming and standalone.

## Firewall rule upkeep

The root README adds one inbound rule for UDP 9000. On Windows, update it if
Frame's address changes, or remove it:

```powershell
Set-NetFirewallRule -DisplayName "Frame pose UDP 9000" -RemoteAddress FRAME_WLAN0_IP,FRAME_WLANAP_IP
Remove-NetFirewallRule -DisplayName "Frame pose UDP 9000"
```

SSH needs no rule (outgoing from the PC).

## Test the UDP path on the PC first

Against PC SteamVR, without Frame in the loop:

```powershell
python -m non_pc_streaming.frame_sender --desktop --pc 127.0.0.1
```

## Log in without a password (SSH key, once)

Without a key, every `ssh`/`scp` call asks for the Frame password, and one
deploy makes four of them. Once, on the PC:

```powershell
ssh-keygen -t ed25519      # press Enter at the prompts (a passphrase is optional)
type $env:USERPROFILE\.ssh\id_ed25519.pub | ssh steamos@FRAME_IP "mkdir -p ~/.ssh && chmod 700 ~/.ssh && cat >> ~/.ssh/authorized_keys && chmod 600 ~/.ssh/authorized_keys"
```

On Ubuntu: `ssh-keygen -t ed25519`, then `ssh-copy-id steamos@FRAME_IP`. The
key then works for both Frame addresses (same headset, same user).

## Stop and clean up

```powershell
ssh steamos@FRAME_IP "pgrep -af '[n]on_pc_streaming.frame_sender|[d]iagnostics.probe_controller'"        # what runs
ssh steamos@FRAME_IP "pkill -f '[n]on_pc_streaming.frame_sender'; pkill -f '[d]iagnostics.probe_controller'"  # stop all
ssh steamos@FRAME_IP "rm -rf ~/frame_pose_sender"                                                          # remove files
```

The sender normally ends with its SSH session; leftovers come from a second
deploy window. Everything lives in `~/frame_pose_sender`: no root, no system
packages, no background service.

## What `deploy_sender.ps1` does

Every run:

1. Packs `artifacts/frame-pose-sender.tar`: `config.toml`, the sender,
   `vendor/`, the shared `general/` modules (packet format, sampler, config,
   demo, input bindings) and `diagnostics/probe_controller.py`. No
   `__pycache__`.
2. Creates `~/frame_pose_sender` on Frame (`ssh`) and uploads the tar (`scp`).
3. Replaces the previous `general/`, `non_pc_streaming/` and `diagnostics/`
   folders there, extracts, and checks for Python 3.11+.
4. Runs, in the same terminal until Ctrl+C:
   - default: the live sender (`-Hz N`, default 90; `-Hz 0` = unlimited);
   - `-Demo`: synthetic poses and inputs, to test the network alone;
   - `-Probe` (`-ProbeSeconds N`): the controller probe instead of the sender.

Expect one password prompt per `ssh`/`scp` call (4 per run), or none with an [SSH key](#log-in-without-a-password-ssh-key-once). Verify the SSH
host key on first connection. Credentials are never stored. Nothing is
installed system-wide and nothing keeps running after the SSH session ends.

Manual alternative on Windows: copy the tar with WinSCP, keep its folder
structure, then run the last command of the next section on Frame.

### On Ubuntu without the script

The same steps with standard Linux tools, from the repository root
(`FRAME_IP` / `PC_IP` as in the root README):

```sh
mkdir -p artifacts
tar -cf artifacts/frame-pose-sender.tar --exclude=__pycache__ config.toml \
    non_pc_streaming/__init__.py non_pc_streaming/frame_sender.py non_pc_streaming/vendor \
    general/__init__.py general/pose_wire.py general/config.py general/controller_state.py \
    general/clock_sync.py general/demo.py general/openvr_sampler.py general/input \
    diagnostics/__init__.py diagnostics/probe_controller.py
ssh steamos@FRAME_IP 'mkdir -p ~/frame_pose_sender'
scp artifacts/frame-pose-sender.tar steamos@FRAME_IP:frame_pose_sender/sender.tar
ssh steamos@FRAME_IP 'cd ~/frame_pose_sender && rm -rf general non_pc_streaming diagnostics && tar -xf sender.tar && python3 --version'

# then one of:
ssh -t steamos@FRAME_IP 'cd ~/frame_pose_sender && python3 -m non_pc_streaming.frame_sender --pc PC_IP --hz 90'      # live (--hz 0 = unlimited)
ssh -t steamos@FRAME_IP 'cd ~/frame_pose_sender && python3 -m non_pc_streaming.frame_sender --pc PC_IP --demo'       # network only
ssh -t steamos@FRAME_IP 'cd ~/frame_pose_sender && python3 -m diagnostics.probe_controller --seconds 30'             # probe
```

Repeat the `tar`/`scp`/extract steps after changing code or `config.toml`.

### Staged first test

1. `-Demo` proves the network route, firewall and receiver.
2. `-Probe` shows the Environment (runtime registry
   `~/.config/openvr/openvrpaths.vrpath`, running VR processes), whether a
   background OpenVR app starts, and which groups the local runtime delivers.
3. Live sender: only the groups the probe showed as available carry data;
   the rest arrive as "no data".

## Clock sync (optional, for absolute latency)

Off by default. `frame_sender.py --sync` (deploy script: `-Sync`) starts a small
responder (`general/clock_sync.py`) on UDP 9001 (`--sync-port`) that answers
only the `--pc` address. The PC measurement tools (`measure_udp_rate --sync`,
`measure_latency --sync`) send NTP-style requests and estimate the Frame/PC
clock offset and drift during the run, which turns the packet timestamp into
absolute latency. Accuracy is bounded by half the fastest round trip (reported
with every result). The PC needs no firewall rule: the replies answer its own
requests. Normal use (no `--sync`) opens no extra port.

## Receiver

`--udp` in the viewer listens on UDP 9000 (`--port`, `--bind PC_IP` to limit
the interface). `--sender-ip` accepts packets only from that address; poses
disappear 250 ms after the last packet (`--timeout`). One sender at a time.
UDP is unauthenticated: use a trusted network.

## Coordinates

Row-major 3x4 **device-origin** transforms in Frame's local standing space:
meters, +X right, +Y up, -Z forward. The viewer remaps display axes only.
Frame's local origin may differ from the PC streaming origin; recalibrate
before reusing a coordinate mapping (the viewer's relative pose avoids this).

## Packets

The sender emits **FVR2** (`general/pose_wire.py`); the receiver also accepts
the older pose-only FVR1.

- Header (32 B): magic, version, count, group bitmask, random session ID,
  sequence number, sender timestamp = the moment the poses were read on Frame
  (`perf_counter_ns`; meaningful on the PC only with clock sync, below).
- Per controller: pose entry (56 B: device, role, input source, tracking
  result, 3x4 matrix), then one block per enabled `[fields]` group: velocity
  (24 B), battery (5 B), buttons (6 B: has-data, pressed, touched bitmasks),
  analog (16 B: trigger, grip, stick x/y), fingers (37 B: curl x5, splay x4,
  skeletal level). NaN or 255 means "no data".
- The groups follow the `config.toml` deployed to Frame, so PC and headset
  configs may differ.
- Only fully tracked controllers are sent; an empty snapshot clears the
  viewer. Sequence numbers drop duplicates and reordering; a new session ID
  lets a restarted sender take over after the previous one times out.

Size: 32 B + 56 B per controller (poses only) up to 144 B per controller (all
groups). Two controllers: about 13-29 kB/s at 90 Hz, about 64 kB/s at 200 Hz (all groups).

## Limits

- Needs Frame awake and worn; the sender does not override sleep or tracking
  policies.
- While Frame's local dashboard is open, it takes the button/finger input; the
  sender reports this.
- If local background OpenVR access ever stops working (runtime update), the
  fallback is a native ARM64 or Android OpenXR app.

Measured performance: [diagnostics/README.md](../diagnostics/README.md#benchmarks).
