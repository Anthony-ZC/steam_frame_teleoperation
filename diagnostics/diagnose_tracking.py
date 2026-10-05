import sys
import time
import openvr as vr

mode = sys.argv[1] if len(sys.argv) > 1 else 'background'
system = vr.init(vr.VRApplication_Scene if mode == 'scene' else vr.VRApplication_Background)
buffer = (vr.TrackedDevicePose_t * vr.k_unMaxTrackedDeviceCount)()
event = vr.VREvent_t()
try:
    compositor = vr.VRCompositor() if mode == 'scene' else None
    if compositor:
        compositor.setTrackingSpace(vr.TrackingUniverseStanding)
    previous = {}
    changes = {}
    start = time.monotonic()
    while time.monotonic() - start < 8:
        while system.pollNextEvent(event):
            pass
        if compositor:
            buffer, _ = compositor.waitGetPoses(buffer, None)
        else:
            buffer = system.getDeviceToAbsoluteTrackingPose(vr.TrackingUniverseStanding, 0, buffer)
        for i, pose in enumerate(buffer):
            if pose.bDeviceIsConnected:
                matrix = tuple(pose.mDeviceToAbsoluteTracking.m[r][c] for r in range(3) for c in range(4))
                if i in previous and previous[i] != matrix:
                    changes[i] = changes.get(i, 0) + 1
                previous[i] = matrix
        time.sleep(0.05)
    for i in previous:
        pose = buffer[i]
        print(f'{mode}: device={i} class={system.getTrackedDeviceClass(i)} valid={pose.bPoseIsValid} tracking={pose.eTrackingResult} changes={changes.get(i, 0)} position={[round(previous[i][j], 5) for j in (3,7,11)]}')
finally:
    vr.shutdown()
