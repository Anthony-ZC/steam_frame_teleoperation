#!/usr/bin/env bash
# Guided rerun of the README benchmarks on Ubuntu, home Wi-Fi only (no direct link):
# PC load, data rate, absolute and relative latency. Procedure: benchmark_plan.md.
#
#   diagnostics/run_ubuntu_wifi_benchmark.sh FRAME_IP PC_IP [phase ...]
#
# Phases (default: all, in this order): deploy ping load streaming standalone.
# Run from the repository root with the venv active. Results go to
# artifacts/*_ubuntu_wifi_*.json; the script pauses before every setup change.
set -euo pipefail

if [[ $# -lt 2 ]]; then
    sed -n '2,9p' "$0"
    exit 1
fi
FRAME_IP=$1 PC_IP=$2
shift 2
PHASES=("$@")
[[ ${#PHASES[@]} -gt 0 ]] || PHASES=(deploy ping load streaming standalone)
RATES=(100 200 0)
FRAME="steamos@$FRAME_IP"
mkdir -p artifacts
trap 'kill $(jobs -p) 2>/dev/null || true' EXIT  # no leftover sender if a run fails

pause() { echo; read -rp ">>> $1 Press Enter when ready... "; }
name() { [[ $1 == 0 ]] && echo unlimited || echo "${1}hz"; }

# Frame sender over Wi-Fi; ends by itself after $2 seconds. Extra args: --sync.
frame_sender() {
    local hz=$1 seconds=$2
    shift 2
    ssh -o BatchMode=yes "$FRAME" "cd ~/frame_pose_sender && python3 -m non_pc_streaming.frame_sender --pc $PC_IP --hz $hz --seconds $seconds $*"
}

# Start the sender ($@) 2 s after the listener, which runs in the foreground.
with_sender() {
    local listener=$1
    shift
    ( sleep 2; "$@" >/dev/null ) &
    local sender=$!
    eval "$listener"
    wait "$sender" || echo "(sender exited with an error; check the run above)"
}

check_frame_idle() {
    ssh -o BatchMode=yes "$FRAME" "pkill -f '[n]on_pc_streaming.frame_sender'" || true
}

deploy() {
    tar -cf artifacts/frame-pose-sender.tar --exclude=__pycache__ config.toml \
        non_pc_streaming/__init__.py non_pc_streaming/frame_sender.py non_pc_streaming/vendor \
        general/__init__.py general/pose_wire.py general/config.py general/controller_state.py \
        general/clock_sync.py general/demo.py general/openvr_sampler.py general/input \
        diagnostics/__init__.py diagnostics/probe_controller.py
    ssh -o BatchMode=yes "$FRAME" 'mkdir -p ~/frame_pose_sender'
    scp -o BatchMode=yes artifacts/frame-pose-sender.tar "$FRAME:frame_pose_sender/sender.tar"
    ssh -o BatchMode=yes "$FRAME" 'cd ~/frame_pose_sender && rm -rf general non_pc_streaming diagnostics && tar -xf sender.tar && python3 --version'
}

ping_rtt() {
    ping -c 40 -i 0.25 "$FRAME_IP" | tail -2 | tee artifacts/ping_ubuntu_wifi.txt
}

load() {
    pause "PC LOAD 1/3: SteamVR running, stream OFF (headset not streaming)."
    python -m diagnostics.measure_stream_load --label ubuntu_wifi_stream_off --seconds 20
    pause "PC LOAD 2/3: stream ON over Wi-Fi, SteamVR dashboard OPEN in the headset."
    python -m diagnostics.measure_stream_load --label ubuntu_wifi_stream_on_dashboard_open --seconds 20
    pause "PC LOAD 3/3: stream ON, dashboard CLOSED, controllers awake."
    python -m diagnostics.measure_stream_load --label ubuntu_wifi_stream_on_dashboard_closed --seconds 20
}

streaming() {
    pause "STREAMING: stream ON over Wi-Fi, dashboard CLOSED, both controllers moving, viewer closed."
    check_frame_idle
    for hz in "${RATES[@]}"; do  # data rate: sender on this PC against PC SteamVR, loopback
        with_sender "python -m diagnostics.measure_udp_rate --sender-ip 127.0.0.1 --seconds 30 --label ubuntu_wifi_streaming_$(name "$hz")" \
            python -m non_pc_streaming.frame_sender --desktop --pc 127.0.0.1 --hz "$hz" --seconds 40
    done
    for hz in "${RATES[@]}"; do  # absolute latency of both modes; Frame sender over Wi-Fi
        pause "ABSOLUTE LATENCY $(name "$hz"): move the controllers briskly (swing, stop, repeat) for 20 s."
        with_sender "python -m diagnostics.measure_latency --sender-ip $FRAME_IP --sync --seconds 20 --label ubuntu_wifi_streaming_and_standalone_$(name "$hz")" \
            frame_sender "$hz" 30 --sync
    done
    for hz in "${RATES[@]}"; do  # relative latency, no clock sync
        pause "RELATIVE LATENCY $(name "$hz"): move the controllers briskly for 20 s."
        with_sender "python -m diagnostics.measure_latency --sender-ip $FRAME_IP --seconds 20 --label ubuntu_wifi_standalone_vs_streaming_$(name "$hz")" \
            frame_sender "$hz" 30
    done
}

standalone() {
    pause "STANDALONE: stop the stream and QUIT PC SteamVR; Frame awake in its home, controllers moving."
    if pgrep -x vrserver >/dev/null; then
        echo "PC SteamVR (vrserver) is still running; quit it first." >&2
        exit 1
    fi
    check_frame_idle
    for hz in "${RATES[@]}"; do  # data rate
        with_sender "python -m diagnostics.measure_udp_rate --sender-ip $FRAME_IP --seconds 30 --label ubuntu_wifi_standalone_$(name "$hz")" \
            frame_sender "$hz" 40
    done
    for hz in "${RATES[@]}"; do  # absolute latency
        with_sender "python -m diagnostics.measure_udp_rate --sender-ip $FRAME_IP --sync --seconds 30 --label ubuntu_wifi_standalone_sync_$(name "$hz")" \
            frame_sender "$hz" 40 --sync
    done
    # PC load while receiving at 200 Hz (poses not measured: PC SteamVR is closed)
    python -m diagnostics.measure_stream_load --label ubuntu_wifi_standalone_200hz --seconds 30 >/dev/null &
    local load=$!
    with_sender "python -m diagnostics.measure_udp_rate --sender-ip $FRAME_IP --seconds 30 --label ubuntu_wifi_standalone_200hz_packets" \
        frame_sender 200 40
    wait "$load"
    python -m diagnostics.measure_stream_load --compare artifacts/stream_load_ubuntu_wifi_*.json
}

for phase in "${PHASES[@]}"; do
    case $phase in
        deploy) deploy ;;
        ping) ping_rtt ;;
        load) load ;;
        streaming) streaming ;;
        standalone) standalone ;;
        *) echo "unknown phase: $phase" >&2; exit 1 ;;
    esac
done
echo; echo "Done. Results: artifacts/*ubuntu_wifi_*"
