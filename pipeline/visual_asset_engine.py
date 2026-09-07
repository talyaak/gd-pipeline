# Visual Asset Engine (Python) — mirrors JS VisualAssetEngine for reskin pipeline
# Provides: load(), validate(), merge(), from_name()
# Resolves: palette.* refs, gradients.* refs, ref: cross-section refs, extends inheritance
# Output: ResolvedTheme dict with all colors as 0xRRGGBB ints, gradients as callables

import json
import re
from copy import deepcopy
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Set, Union


# ============================================================================
# UTILITIES
# ============================================================================

_HEX_COLOR_RE = re.compile(r'^#?[0-9a-fA-F]{6}$')


def is_hex_color(value: str) -> bool:
    return isinstance(value, str) and bool(_HEX_COLOR_RE.match(value))


def hex_to_number(hex_color: Union[str, int]) -> int:
    if isinstance(hex_color, int):
        return hex_color
    if not is_hex_color(hex_color):
        return 0xffffff
    return int(hex_color.replace('#', ''), 16)


def deep_merge(target: Dict, source: Dict) -> Dict:
    """Deep merge source into target, returning new dict."""
    result = deepcopy(target)
    for key, value in source.items():
        if isinstance(value, dict) and not isinstance(value, list):
            result[key] = deep_merge(result.get(key, {}), value)
        else:
            result[key] = deepcopy(value)
    return result


# ============================================================================
# GRADIENT FUNCTIONS
# ============================================================================

def create_linear_gradient(stops: List[Dict]) -> Callable[[float], int]:
    """Create a linear gradient function. stops: [{stop: float, color: int}, ...] sorted by stop."""
    sorted_stops = sorted(stops, key=lambda s: s['stop'])

    def gradient(t: float) -> int:
        t = max(0.0, min(1.0, t))
        if t <= sorted_stops[0]['stop']:
            return sorted_stops[0]['color']
        if t >= sorted_stops[-1]['stop']:
            return sorted_stops[-1]['color']
        for i in range(len(sorted_stops) - 1):
            if sorted_stops[i]['stop'] <= t <= sorted_stops[i + 1]['stop']:
                local_t = (t - sorted_stops[i]['stop']) / (sorted_stops[i + 1]['stop'] - sorted_stops[i]['stop'])
                c1 = sorted_stops[i]['color']
                c2 = sorted_stops[i + 1]['color']
                r = int(round(((c1 >> 16) & 0xff) + (((c2 >> 16) & 0xff) - ((c1 >> 16) & 0xff)) * local_t))
                g = int(round(((c1 >> 8) & 0xff) + (((c2 >> 8) & 0xff) - ((c1 >> 8) & 0xff)) * local_t))
                b = int(round((c1 & 0xff) + ((c2 & 0xff) - (c1 & 0xff)) * local_t))
                return (r << 16) | (g << 8) | b
        return sorted_stops[-1]['color']

    return gradient


def create_radial_gradient(stops: List[Dict], center: List[float], radius: float) -> Callable[[float, float, float, float], int]:
    """Create a radial gradient function."""
    linear_grad = create_linear_gradient(stops)
    cx, cy = center[0], center[1]

    def gradient(x: float, y: float, w: float, h: float) -> int:
        dx = (x / w) - cx
        dy = (y / h) - cy
        dist = (dx * dx + dy * dy) ** 0.5 / radius
        return linear_grad(dist)

    return gradient


def build_gradient(grad_spec: Dict, palette: Dict[str, str]) -> Optional[Callable]:
    if not grad_spec or 'type' not in grad_spec:
        return None

    resolved_stops = []
    for stop in grad_spec['stops']:
        resolved_stops.append({
            'stop': stop['stop'],
            'color': resolve_color_ref(stop['color'], palette)
        })

    if grad_spec['type'] == 'linear':
        return create_linear_gradient(resolved_stops)
    elif grad_spec['type'] == 'radial':
        center = grad_spec.get('center', [0.5, 0.5])
        radius = grad_spec.get('radius', 1.0)
        return create_radial_gradient(resolved_stops, center, radius)
    return None


# ============================================================================
# REFERENCE RESOLUTION
# ============================================================================

def resolve_color_ref(value: Union[str, int], palette: Dict[str, str]) -> int:
    if isinstance(value, int):
        return value
    if not isinstance(value, str):
        return 0xffffff

    if value.startswith('palette.'):
        key = value[8:]
        return hex_to_number(palette.get(key, '#ffffff'))

    if is_hex_color(value):
        return hex_to_number(value)

    return 0xffffff


def resolve_value(
    value: Any,
    context: Dict,
    palette: Dict[str, str],
    gradients: Dict[str, Callable],
    visited_refs: Optional[Set[str]] = None
) -> Any:
    if visited_refs is None:
        visited_refs = set()

    if value is None or not isinstance(value, str):
        return value

    # palette.* reference
    if value.startswith('palette.'):
        key = value[8:]
        return hex_to_number(palette.get(key, '#ffffff'))

    # gradients.* reference - returns the gradient function
    if value.startswith('gradients.'):
        key = value[10:]
        return gradients.get(key)

    # ref: cross-section reference
    if value.startswith('ref:'):
        ref_path = value[4:]
        if ref_path in visited_refs:
            raise ValueError(f'Circular reference detected: {ref_path}')
        visited_refs.add(ref_path)
        result = resolve_ref_path(context, ref_path, palette, gradients, visited_refs)
        visited_refs.remove(ref_path)
        return result

    # Direct hex color
    if is_hex_color(value):
        return hex_to_number(value)

    return value


def resolve_ref_path(root: Dict, path: str, palette: Dict, gradients: Dict, visited_refs: Set) -> Any:
    parts = path.split('.')
    current = root
    for part in parts:
        if current is None or not isinstance(current, dict):
            return None
        current = current.get(part)
    # If resolved value is itself a reference, resolve recursively
    if isinstance(current, str) and (current.startswith('palette.') or current.startswith('gradients.') or current.startswith('ref:')):
        return resolve_value(current, root, palette, gradients, visited_refs)
    return current


def resolve_object(
    obj: Any,
    context: Dict,
    palette: Dict[str, str],
    gradients: Dict[str, Callable],
    visited_refs: Optional[Set[str]] = None
) -> Any:
    if visited_refs is None:
        visited_refs = set()

    if obj is None:
        return None
    if isinstance(obj, list):
        return [resolve_object(item, context, palette, gradients, visited_refs) for item in obj]
    if isinstance(obj, dict):
        return {
            key: resolve_object(value, context, palette, gradients, visited_refs)
            for key, value in obj.items()
        }
    return resolve_value(obj, context, palette, gradients, visited_refs)


# ============================================================================
# SPEC VALIDATION
# ============================================================================

class VisualSpecError(ValueError):
    """Raised when visual spec validation fails."""
    pass


def validate_spec(spec: Dict) -> None:
    """Validate a visual spec dict. Raises VisualSpecError on failure."""
    if not spec or not isinstance(spec, dict):
        raise VisualSpecError('Visual spec must be a dict')

    if spec.get('version') != 1:
        raise VisualSpecError(f'Unsupported visual spec version: {spec.get("version")}. Expected 1.')

    name = spec.get('name')
    if not name or not isinstance(name, str):
        raise VisualSpecError('Visual spec must have a string "name" field')

    if 'extends' in spec and not isinstance(spec['extends'], str):
        raise VisualSpecError('"extends" must be a string')

    # Validate palette
    if 'palette' in spec:
        palette = spec['palette']
        if not isinstance(palette, dict):
            raise VisualSpecError('"palette" must be a dict')
        for key, value in palette.items():
            if not is_hex_color(value) and not isinstance(value, int):
                raise VisualSpecError(f'palette.{key}: expected hex color string or number, got {type(value).__name__}')

    # Validate gradients
    if 'gradients' in spec:
        gradients = spec['gradients']
        if not isinstance(gradients, dict):
            raise VisualSpecError('"gradients" must be a dict')
        for key, grad in gradients.items():
            if not grad or not isinstance(grad, dict):
                raise VisualSpecError(f'gradients.{key}: must be a dict')
            if grad.get('type') not in ('linear', 'radial'):
                raise VisualSpecError(f'gradients.{key}: type must be "linear" or "radial"')
            stops = grad.get('stops')
            if not isinstance(stops, list) or len(stops) < 2:
                raise VisualSpecError(f'gradients.{key}: stops must be a list with at least 2 entries')
            for stop in stops:
                if not isinstance(stop.get('stop'), (int, float)) or not (0 <= stop['stop'] <= 1):
                    raise VisualSpecError(f'gradients.{key}: stop must be a number between 0 and 1')
                color = stop.get('color')
                if not is_hex_color(color) and not (isinstance(color, str) and color.startswith('palette.')):
                    raise VisualSpecError(f'gradients.{key}: stop color must be hex or palette.* ref')

    # Validate shapes
    if 'shapes' in spec:
        shapes = spec['shapes']
        if not isinstance(shapes, dict):
            raise VisualSpecError('"shapes" must be a dict')
        for key, shape in shapes.items():
            if not shape or not isinstance(shape, dict):
                raise VisualSpecError(f'shapes.{key}: must be a dict')
            if shape.get('type') not in ('SoftCircle', 'SoftRect'):
                raise VisualSpecError(f'shapes.{key}: type must be "SoftCircle" or "SoftRect"')

    # Validate ui, particles, juice - permissive
    for section in ('ui', 'particles', 'juice'):
        if section in spec and not isinstance(spec[section], dict):
            raise VisualSpecError(f'"{section}" must be a dict')

    # Check for circular refs within the spec
    visited = set()

    def check_refs(obj: Any, path: str = '') -> None:
        if not obj or not isinstance(obj, dict):
            return
        if isinstance(obj, list):
            for i, item in enumerate(obj):
                check_refs(item, f'{path}[{i}]')
            return
        for key, value in obj.items():
            current_path = f'{path}.{key}' if path else key
            if isinstance(value, str) and value.startswith('ref:'):
                if value in visited:
                    raise VisualSpecError(f'Circular ref: {value} at {current_path}')
                visited.add(value)
                check_refs(value, current_path)
                visited.remove(value)
            else:
                check_refs(value, current_path)

    check_refs(spec)


# ============================================================================
# MAIN ENGINE CLASS
# ============================================================================

class VisualAssetEngine:
    """Python-side visual asset engine for reskin pipeline."""

    _theme_cache: Dict[str, Dict] = {}
    _theme_specs: Dict[str, Dict] = {}

    @classmethod
    def load(cls, spec: Dict) -> Dict:
        """Load a visual spec, resolve all references, return a frozen theme dict."""
        validate_spec(spec)

        # Handle inheritance
        working_spec = spec
        if spec.get('extends'):
            base_name = spec['extends']
            if base_name not in cls._theme_cache:
                raise VisualSpecError(f'Base theme "{base_name}" not loaded. Load base theme first or include inline.')
            working_spec = deep_merge(cls._theme_cache[base_name]['_raw_spec'], spec)

        # Build palette (convert all to 0xRRGGBB ints)
        raw_palette = working_spec.get('palette', {})
        palette = {key: hex_to_number(value) for key, value in raw_palette.items()}

        # Build gradients (create callable functions)
        raw_gradients = working_spec.get('gradients', {})
        gradients = {}
        for key, grad_spec in raw_gradients.items():
            gradients[key] = build_gradient(grad_spec, raw_palette)

        # Build context for cross-section refs
        context = {
            'palette': raw_palette,
            'gradients': raw_gradients,
            'shapes': working_spec.get('shapes', {}),
            'ui': working_spec.get('ui', {}),
            'particles': working_spec.get('particles', {}),
            'juice': working_spec.get('juice', {})
        }

        # Resolve all sections
        resolved = {
            '_raw_spec': working_spec,
            'palette': palette,
            'gradients': gradients,
            'shapes': resolve_object(working_spec.get('shapes', {}), context, raw_palette, gradients),
            'ui': resolve_object(working_spec.get('ui', {}), context, raw_palette, gradients),
            'particles': resolve_object(working_spec.get('particles', {}), context, raw_palette, gradients),
            'juice': resolve_object(working_spec.get('juice', {}), context, raw_palette, gradients)
        }

        # Cache by name
        cls._theme_cache[spec['name']] = resolved
        cls._theme_specs[spec['name']] = working_spec
        return resolved

    @classmethod
    def from_name(cls, name: str) -> Dict:
        """Get a theme by name from cache or loaded specs."""
        if name in cls._theme_cache:
            return cls._theme_cache[name]

        if name in cls._theme_specs:
            return cls.load(cls._theme_specs[name])

        raise VisualSpecError(f'Theme "{name}" not found. Available: {list(cls._theme_cache.keys())}')

    @classmethod
    def merge(cls, base: Dict, override: Dict) -> Dict:
        """Merge two themes (override takes precedence, deep merge)."""
        if not base:
            return override
        if not override:
            return base
        return deep_merge(base, override)

    @classmethod
    def validate(cls, spec: Dict) -> None:
        """Validate a spec without resolving."""
        validate_spec(spec)

    @classmethod
    def register_theme(cls, name: str, spec: Dict) -> Dict:
        """Register a theme spec by name."""
        cls._theme_specs[name] = spec
        return cls.load(spec)

    @classmethod
    def load_theme_file(cls, path: Union[str, Path]) -> Dict:
        """Load a theme from a JSON file."""
        with open(path, 'r') as f:
            spec = json.load(f)
        return cls.load(spec)

    @classmethod
    def clear_cache(cls) -> None:
        """Clear all cached themes."""
        cls._theme_cache.clear()
        cls._theme_specs.clear()


# Convenience functions matching the spec API
def load(spec: Dict) -> Dict:
    return VisualAssetEngine.load(spec)


def from_name(name: str) -> Dict:
    return VisualAssetEngine.from_name(name)


def merge(base: Dict, override: Dict) -> Dict:
    return VisualAssetEngine.merge(base, override)


def validate(spec: Dict) -> None:
    VisualAssetEngine.validate(spec)


if __name__ == '__main__':
    # Self-test
    import sys

    base_spec = {
        'version': 1,
        'name': 'base',
        'palette': {
            'primary': '#33e6ff',
            'secondary': '#ff33cc',
            'background': '#0a0a18',
            'surface': '#14142a',
            'text': '#ffffff',
        },
        'gradients': {
            'buttonPrimary': {
                'type': 'linear',
                'from': [0, 0],
                'to': [0, 1],
                'stops': [
                    {'stop': 0.0, 'color': 'palette.primary'},
                    {'stop': 1.0, 'color': '#0099cc'}
                ]
            }
        },
        'shapes': {
            'gem': {
                'type': 'SoftCircle',
                'radius': 20,
                'feather': 4,
                'quality': 2,
                'color': 'palette.primary'
            }
        },
        'ui': {
            'button': {
                'states': {
                    'normal': 'palette.primary',
                    'hover': 'gradients.buttonPrimary',
                    'pressed': '#0077aa'
                }
            }
        },
        'particles': {
            'matchBurst': {
                'count': 12,
                'life': 600,
                'startColor': 'palette.primary',
                'endColor': 'palette.secondary'
            }
        },
        'juice': {
            'screenShake': {'intensity': 8, 'duration': 120}
        }
    }

    print('Testing VisualAssetEngine...')
    theme = VisualAssetEngine.load(base_spec)
    print(f'  Palette: {theme["palette"]}')
    print(f'  Gradient callable: {callable(theme["gradients"]["buttonPrimary"])}')
    print(f'  Gradient(0.5): {theme["gradients"]["buttonPrimary"](0.5):#08x}')
    print(f'  Shape resolved color: {theme["shapes"]["gem"]["color"]:#08x}')
    print(f'  UI button normal: {theme["ui"]["button"]["states"]["normal"]:#08x}')
    print(f'  UI button hover callable: {callable(theme["ui"]["button"]["states"]["hover"])}')
    print(f'  Particle startColor: {theme["particles"]["matchBurst"]["startColor"]:#08x}')
    print(f'  Juice screenShake: {theme["juice"]["screenShake"]}')

    # Test inheritance
    neon_spec = {
        'version': 1,
        'name': 'neon',
        'extends': 'base',
        'palette': {
            'accent': '#ffe14d',
        },
        'juice': {
            'cameraFlash': {'color': 'palette.accent', 'duration': 80}
        }
    }
    neon_theme = VisualAssetEngine.load(neon_spec)
    print(f'\nNeon theme (inherits base):')
    print(f'  Has primary: {"primary" in neon_theme["palette"]}')
    print(f'  Has accent: {"accent" in neon_theme["palette"]}')
    print(f'  cameraFlash color: {neon_theme["juice"]["cameraFlash"]["color"]:#08x}')

    # Test merge
    merged = VisualAssetEngine.merge(theme, {'palette': {'primary': '#ff0000'}})
    print(f'\nMerged primary: {merged["palette"]["primary"]:#08x}')

    # Test validate
    VisualAssetEngine.validate(base_spec)
    print('\nValidation passed.')

    print('\nAll tests passed!')