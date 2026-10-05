# Standalone mode: Frame sender and PC receiver

A Python OpenVR background client runs **on Frame**, reads Frame's own VR
runtime and sends controller data to the PC over UDP. No video, no PC
SteamVR. Verified live on Frame on 2026-10-04 (both controllers, every data
group).

Setup, finding the IP addresses, home Wi‑Fi vs. direct link, the firewall
rule and the everyday commands are in the root README:
[Standalone mode](../README.md#standalone-mode). This page covers what happens
underneath.

| File | Runs on | Purpose |
|---|---|---|
| `frame_sender.py` | Frame (or PC with `--desktop`/`--demo`) | samples controllers and sends FVR2 packets |
| `udp_pose.py` | PC | `UDPReader`: receives, validates, hands poses to the viewer |
| `deploy_sender.ps1` | PC | packages, uploads and runs the sender or probe over SSH |
| `vendor/` | Frame | unmodified pyopenvr + Valve's Linux ARM64 `libopenvr_api` (licenses, provenance) |

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

Expect one password prompt per `ssh`/`scp` call (4 per run), or none with an SSH key ([root README](../README.md#optional-log-in-without-a-password-ssh-key-once)). Verify the SSH
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
    general/demo.py general/openvr_sampler.py general/input \
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
  sequence number, sender timestamp (diagnostic only; clocks are not synced).
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

Measured performance: root README [Benchmarks](../README.md#benchmarks).
