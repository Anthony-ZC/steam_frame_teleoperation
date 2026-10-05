"""Regenerate actions.json and bindings_<type>.json in this folder.

Run `python -m general.input.make_manifest` after adding a controller type
(as reported by `python -m diagnostics.probe_controller`) to CONTROLLER_TYPES.
Bindings can also be edited live in SteamVR > Settings > Controllers.
"""
import json
from pathlib import Path
from general.controller_state import BUTTONS
from general.openvr_sampler import ACTION_SET as SET, BUTTON_ACTIONS

ANALOG = ('trigger', 'grip')
# controller type -> {hand: {logical button: component under /user/hand/<hand>/input/}}.
# Frame: from SteamVR/drivers/frame_controller/resources/input/frame_controller_profile.json;
# the left controller mirrors a/b/x/y onto its d-pad and has 'view' instead of 'menu'.
FRAME_RIGHT = {b: b for b in BUTTONS}
FRAME_LEFT = dict(FRAME_RIGHT, a='dpad_down', b='dpad_right', x='dpad_left', y='dpad_up', menu='view')
INDEX = {b: b for b in ('a', 'b', 'system', 'thumbstick', 'trigger', 'grip')}
CONTROLLER_TYPES = {
    'frame_controller': {'left': FRAME_LEFT, 'right': FRAME_RIGHT},
    'knuckles': {'left': INDEX, 'right': INDEX},
}
HERE = Path(__file__).resolve().parent


def actions():
    result = [{'name': f'{SET}/in/{b}_{kind}', 'type': 'boolean'} for b, kind in BUTTON_ACTIONS]
    result += [{'name': f'{SET}/in/trigger', 'type': 'vector1'},
               {'name': f'{SET}/in/grip', 'type': 'vector1'},
               {'name': f'{SET}/in/thumbstick', 'type': 'vector2'}]
    result += [{'name': f'{SET}/in/skeleton_{hand}', 'type': 'skeleton',
                'skeleton': f'/skeleton/hand/{hand}'} for hand in ('left', 'right')]
    return result


def bindings(controller_type, layout):
    sources, skeleton = [], []
    for hand, components in layout.items():
        for button, component in components.items():
            path = f'/user/hand/{hand}/input/{component}'
            out = lambda name: {'output': f'{SET}/in/{name}'}
            inputs = {kind: out(f'{button}_{kind}') for b, kind in BUTTON_ACTIONS if b == button}
            if button == 'thumbstick':
                sources.append({'path': path, 'mode': 'joystick', 'inputs': dict(inputs, position=out(button))})
            elif button in ANALOG:
                sources.append({'path': path, 'mode': 'trigger', 'inputs': dict(inputs, pull=out(button))})
            else:
                sources.append({'path': path, 'mode': 'button', 'inputs': inputs})
        skeleton.append({'output': f'{SET}/in/skeleton_{hand}',
                         'path': f'/user/hand/{hand}/input/skeleton/{hand}'})
    return {'controller_type': controller_type, 'name': f'Teleop probe ({controller_type})',
            'bindings': {SET: {'sources': sources, 'skeleton': skeleton}}}


def main():
    manifest = {
        'default_bindings': [{'controller_type': t, 'binding_url': f'bindings_{t}.json'}
                             for t in CONTROLLER_TYPES],
        'actions': actions(),
        'action_sets': [{'name': SET, 'usage': 'leftright'}],
        'localization': [{'language_tag': 'en_US', SET: 'Teleoperation'}],
    }
    files = {'actions.json': manifest}
    files.update({f'bindings_{t}.json': bindings(t, layout) for t, layout in CONTROLLER_TYPES.items()})
    for name, content in files.items():
        (HERE / name).write_text(json.dumps(content, indent=2) + '\n', encoding='utf-8')
        print(f'wrote {HERE / name}')


if __name__ == '__main__':
    main()
