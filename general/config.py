"""Load config.toml; stdlib only so the Frame sender can use it too."""
from dataclasses import dataclass
from pathlib import Path
import tomllib

FIELD_GROUPS = ('velocity', 'battery', 'buttons', 'analog', 'fingers')
INPUT_GROUPS = frozenset(('buttons', 'analog', 'fingers'))
RELATIVE_MODES = ('own_frame', 'world_axes')
APP_TYPES = ('background', 'overlay', 'scene')
DEFAULT_PATH = Path(__file__).resolve().parent.parent / 'config.toml'


@dataclass(frozen=True)
class Config:
    fields: frozenset = frozenset(FIELD_GROUPS)
    relative_enabled: bool = True
    relative_mode: str = 'own_frame'
    settle_seconds: float = 3.0
    app_type: str = 'background'
    legacy_fallback: bool = True


def _section(data, name, keys):
    section = data.get(name, {})
    if not isinstance(section, dict):
        raise ValueError(f'[{name}] must be a table')
    unknown = section.keys() - set(keys)
    if unknown:
        raise ValueError(f'unknown keys in [{name}]: {", ".join(sorted(unknown))}')
    return section


def _bool(section, name, key, default):
    value = section.get(key, default)
    if not isinstance(value, bool):
        raise ValueError(f'{name}.{key} must be true or false')
    return value


def parse(data):
    unknown = data.keys() - {'fields', 'relative_pose', 'input'}
    if unknown:
        raise ValueError(f'unknown config sections: {", ".join(sorted(unknown))}')
    fields = _section(data, 'fields', FIELD_GROUPS)
    relative = _section(data, 'relative_pose', ('enabled', 'mode', 'settle_seconds'))
    inputs = _section(data, 'input', ('app_type', 'legacy_fallback'))
    default = Config()
    mode = relative.get('mode', default.relative_mode)
    if mode not in RELATIVE_MODES:
        raise ValueError(f'relative_pose.mode must be one of {RELATIVE_MODES}')
    settle = relative.get('settle_seconds', default.settle_seconds)
    if isinstance(settle, bool) or not isinstance(settle, (int, float)) or not 0 <= settle < 3600:
        raise ValueError('relative_pose.settle_seconds must be a number in [0, 3600)')
    app_type = inputs.get('app_type', default.app_type)
    if app_type not in APP_TYPES:
        raise ValueError(f'input.app_type must be one of {APP_TYPES}')
    return Config(
        fields=frozenset(g for g in FIELD_GROUPS if _bool(fields, 'fields', g, True)),
        relative_enabled=_bool(relative, 'relative_pose', 'enabled', default.relative_enabled),
        relative_mode=mode,
        settle_seconds=float(settle),
        app_type=app_type,
        legacy_fallback=_bool(inputs, 'input', 'legacy_fallback', default.legacy_fallback))


def load(path=None):
    """Read PATH, or the repository config.toml; defaults if that file is absent."""
    target = Path(path) if path else DEFAULT_PATH
    if not target.exists():
        if path:
            raise FileNotFoundError(f'config file not found: {target}')
        return Config()
    with open(target, 'rb') as file:
        return parse(tomllib.load(file))
