"""Numpy-free controller sample shared by the PC readers and the Frame sender."""
from dataclasses import dataclass
from typing import Optional

FINGERS = ('thumb', 'index', 'middle', 'ring', 'pinky')
# Logical buttons, named after the right Frame controller. The left controller's
# mirrored d-pad (down/right/left/up) maps to a/b/x/y and its view button to menu.
BUTTONS = ('a', 'b', 'x', 'y', 'menu', 'system', 'bumper', 'thumbstick', 'thumbrest', 'trigger', 'grip')
TOUCH_ONLY = frozenset(('thumbrest',))


@dataclass
class ButtonState:
    pressed: bool = False
    touched: bool = False


@dataclass
class ControllerState:
    """One controller at one poll. Optional groups are None when disabled or unavailable."""
    name: str
    device_id: int
    matrix: list  # row-major 3x4 device-to-standing transform, meters
    tracking_result: int
    velocity: Optional[tuple] = None          # m/s, standing space
    angular_velocity: Optional[tuple] = None  # rad/s, standing space
    battery: Optional[float] = None           # 0..1
    charging: Optional[bool] = None
    controller_type: Optional[str] = None
    buttons: Optional[dict] = None            # BUTTONS name -> ButtonState (missing = no data)
    trigger: Optional[float] = None           # 0..1
    grip: Optional[float] = None              # 0..1
    thumbstick: Optional[tuple] = None        # (x, y) in -1..1
    finger_curl: Optional[tuple] = None       # FINGERS order, 0 open .. 1 curled
    finger_splay: Optional[tuple] = None      # 4 gaps thumb-index .. ring-pinky
    skeletal_level: Optional[int] = None      # 0 estimated, 1 partial, 2 full
    input_source: Optional[str] = None        # 'actions', 'legacy', 'actions+legacy'
