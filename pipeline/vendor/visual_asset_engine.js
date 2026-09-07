// Visual Asset Engine — unified parameterized interface for game visuals from declarative JSON spec
// Provides: VisualAssetEngine.load(spec), .fromName(name), .merge(base, override), .validate(spec)
// Resolves: palette.* refs, gradients.* refs, ref: cross-section refs, extends inheritance
// Output: ResolvedTheme with all colors as 0xRRGGBB numbers, gradients as callable functions

(function() {
  'use strict';

  // ============================================================================
  // UTILITIES
  // ============================================================================

  function isHexColor(str) {
    return typeof str === 'string' && /^#?[0-9a-fA-F]{6}$/.test(str);
  }

  function hexToNumber(hex) {
    if (typeof hex === 'number') return hex;
    if (!isHexColor(hex)) return 0xffffff;
    return parseInt(hex.replace('#', ''), 16);
  }

  function deepClone(obj) {
    return JSON.parse(JSON.stringify(obj));
  }

  function deepMerge(target, source) {
    const result = deepClone(target);
    for (const key of Object.keys(source)) {
      if (source[key] && typeof source[key] === 'object' && !Array.isArray(source[key])) {
        result[key] = deepMerge(result[key] || {}, source[key]);
      } else {
        result[key] = deepClone(source[key]);
      }
    }
    return result;
  }

  // ============================================================================
  // GRADIENT FUNCTIONS
  // ============================================================================

  function createLinearGradient(stops) {
    // stops: [{ stop: 0.0, color: 0xRRGGBB }, ...] sorted by stop
    const sorted = [...stops].sort((a, b) => a.stop - b.stop);
    return function(t) {
      t = Math.max(0, Math.min(1, t));
      if (t <= sorted[0].stop) return sorted[0].color;
      if (t >= sorted[sorted.length - 1].stop) return sorted[sorted.length - 1].color;
      for (let i = 0; i < sorted.length - 1; i++) {
        if (t >= sorted[i].stop && t <= sorted[i + 1].stop) {
          const localT = (t - sorted[i].stop) / (sorted[i + 1].stop - sorted[i].stop);
          const c1 = sorted[i].color;
          const c2 = sorted[i + 1].color;
          const r = Math.round(((c1 >> 16) & 0xff) + (((c2 >> 16) & 0xff) - ((c1 >> 16) & 0xff)) * localT);
          const g = Math.round(((c1 >> 8) & 0xff) + (((c2 >> 8) & 0xff) - ((c1 >> 8) & 0xff)) * localT);
          const b = Math.round((c1 & 0xff) + ((c2 & 0xff) - (c1 & 0xff)) * localT);
          return (r << 16) | (g << 8) | b;
        }
      }
      return sorted[sorted.length - 1].color;
    };
  }

  function createRadialGradient(stops, center, radius) {
    const sorted = [...stops].sort((a, b) => a.stop - b.stop);
    const cx = center[0], cy = center[1];
    return function(x, y, w, h) {
      const dx = (x / w) - cx;
      const dy = (y / h) - cy;
      const dist = Math.sqrt(dx * dx + dy * dy) / radius;
      return createLinearGradient(stops)(dist);
    };
  }

  function buildGradient(gradSpec, palette) {
    if (!gradSpec || !gradSpec.type) return null;
    const resolvedStops = gradSpec.stops.map(s => ({
      stop: s.stop,
      color: resolveColorRef(s.color, palette)
    }));
    if (gradSpec.type === 'linear') {
      return createLinearGradient(resolvedStops);
    } else if (gradSpec.type === 'radial') {
      return createRadialGradient(resolvedStops, gradSpec.center || [0.5, 0.5], gradSpec.radius || 1.0);
    }
    return null;
  }

  // ============================================================================
  // REFERENCE RESOLUTION
  // ============================================================================

  function resolveColorRef(value, palette) {
    if (typeof value === 'number') return value;
    if (typeof value !== 'string') return 0xffffff;

    // palette.* reference
    if (value.startsWith('palette.')) {
      const key = value.slice(8);
      return hexToNumber(palette[key] || '#ffffff');
    }
    // Direct hex color
    if (isHexColor(value)) {
      return hexToNumber(value);
    }
    return 0xffffff;
  }

  function resolveValue(value, context, palette, gradients, visitedRefs = new Set()) {
    if (value === null || value === undefined) return value;
    if (typeof value !== 'string') return value;

    // palette.* reference
    if (value.startsWith('palette.')) {
      const key = value.slice(8);
      return hexToNumber(palette[key] || '#ffffff');
    }

    // gradients.* reference - returns the gradient function
    if (value.startsWith('gradients.')) {
      const key = value.slice(10);
      return gradients[key] || null;
    }

    // ref: cross-section reference
    if (value.startsWith('ref:')) {
      const refPath = value.slice(4);
      if (visitedRefs.has(refPath)) {
        throw new Error(`Circular reference detected: ${refPath}`);
      }
      visitedRefs.add(refPath);
      const result = resolveRefPath(context, refPath, palette, gradients, visitedRefs);
      visitedRefs.delete(refPath);
      return result;
    }

    // Direct hex color
    if (isHexColor(value)) {
      return hexToNumber(value);
    }

    return value;
  }

  function resolveRefPath(root, path, palette, gradients, visitedRefs) {
    const parts = path.split('.');
    let current = root;
    for (const part of parts) {
      if (current === null || current === undefined || typeof current !== 'object') {
        return undefined;
      }
      current = current[part];
    }
    // If the resolved value is itself a reference, resolve it recursively
    if (typeof current === 'string' && (current.startsWith('palette.') || current.startsWith('gradients.') || current.startsWith('ref:'))) {
      return resolveValue(current, root, palette, gradients, visitedRefs);
    }
    return current;
  }

  function resolveObject(obj, context, palette, gradients, visitedRefs = new Set()) {
    if (obj === null || obj === undefined) return obj;
    if (Array.isArray(obj)) {
      return obj.map(item => resolveObject(item, context, palette, gradients, visitedRefs));
    }
    if (typeof obj === 'object') {
      const result = {};
      for (const [key, value] of Object.entries(obj)) {
        result[key] = resolveObject(value, context, palette, gradients, visitedRefs);
      }
      return result;
    }
    return resolveValue(obj, context, palette, gradients, visitedRefs);
  }

  // ============================================================================
  // SPEC VALIDATION
  // ============================================================================

  function validateSpec(spec) {
    if (!spec || typeof spec !== 'object') {
      throw new Error('Visual spec must be an object');
    }
    if (spec.version !== 1) {
      throw new Error(`Unsupported visual spec version: ${spec.version}. Expected 1.`);
    }
    if (!spec.name || typeof spec.name !== 'string') {
      throw new Error('Visual spec must have a string "name" field');
    }

    // Validate extends chain for cycles
    if (spec.extends) {
      if (typeof spec.extends !== 'string') {
        throw new Error('"extends" must be a string');
      }
      // Note: actual cycle detection across files happens at load time
    }

    // Validate palette
    if (spec.palette) {
      if (typeof spec.palette !== 'object') throw new Error('"palette" must be an object');
      for (const [key, value] of Object.entries(spec.palette)) {
        if (!isHexColor(value) && typeof value !== 'number') {
          throw new Error(`palette.${key}: expected hex color string or number, got ${typeof value}`);
        }
      }
    }

    // Validate gradients
    if (spec.gradients) {
      if (typeof spec.gradients !== 'object') throw new Error('"gradients" must be an object');
      for (const [key, grad] of Object.entries(spec.gradients)) {
        if (!grad || typeof grad !== 'object') throw new Error(`gradients.${key}: must be an object`);
        if (!grad.type || !['linear', 'radial'].includes(grad.type)) {
          throw new Error(`gradients.${key}: type must be "linear" or "radial"`);
        }
        if (!Array.isArray(grad.stops) || grad.stops.length < 2) {
          throw new Error(`gradients.${key}: stops must be an array with at least 2 entries`);
        }
        for (const stop of grad.stops) {
          if (typeof stop.stop !== 'number' || stop.stop < 0 || stop.stop > 1) {
            throw new Error(`gradients.${key}: stop must be a number between 0 and 1`);
          }
          if (!isHexColor(stop.color) && !stop.color.startsWith('palette.')) {
            throw new Error(`gradients.${key}: stop color must be hex or palette.* ref`);
          }
        }
      }
    }

    // Validate shapes
    if (spec.shapes) {
      if (typeof spec.shapes !== 'object') throw new Error('"shapes" must be an object');
      for (const [key, shape] of Object.entries(spec.shapes)) {
        if (!shape || typeof shape !== 'object') throw new Error(`shapes.${key}: must be an object`);
        if (!shape.type || !['SoftCircle', 'SoftRect'].includes(shape.type)) {
          throw new Error(`shapes.${key}: type must be "SoftCircle" or "SoftRect"`);
        }
      }
    }

    // Validate ui
    if (spec.ui) {
      if (typeof spec.ui !== 'object') throw new Error('"ui" must be an object');
      // ui validation is permissive - structure varies by component
    }

    // Validate particles
    if (spec.particles) {
      if (typeof spec.particles !== 'object') throw new Error('"particles" must be an object');
    }

    // Validate juice
    if (spec.juice) {
      if (typeof spec.juice !== 'object') throw new Error('"juice" must be an object');
    }

    // Check for circular refs in the spec itself (ref: cycles within same file)
    const visited = new Set();
    function checkRefs(obj, path = '') {
      if (!obj || typeof obj !== 'object') return;
      if (Array.isArray(obj)) {
        obj.forEach((item, i) => checkRefs(item, `${path}[${i}]`));
        return;
      }
      for (const [key, value] of Object.entries(obj)) {
        const currentPath = path ? `${path}.${key}` : key;
        if (typeof value === 'string' && value.startsWith('ref:')) {
          if (visited.has(value)) {
            throw new Error(`Circular ref: ${value} at ${currentPath}`);
          }
          visited.add(value);
          checkRefs(value, currentPath);
          visited.delete(value);
        } else {
          checkRefs(value, currentPath);
        }
      }
    }
    checkRefs(spec);
  }

  // ============================================================================
  // MAIN ENGINE CLASS
  // ============================================================================

  class VisualAssetEngine {
    static themeCache = new Map();

    // Load a visual spec, resolve all references, return a frozen theme object
    static load(spec) {
      validateSpec(spec);

      // Handle inheritance
      let workingSpec = spec;
      if (spec.extends) {
        const baseSpec = this.themeCache.get(spec.extends);
        if (!baseSpec) {
          throw new Error(`Base theme "${spec.extends}" not loaded. Load base theme first or include inline.`);
        }
        workingSpec = deepMerge(baseSpec._rawSpec, spec);
      }

      // Build palette (convert all to 0xRRGGBB numbers)
      const rawPalette = workingSpec.palette || {};
      const palette = {};
      for (const [key, value] of Object.entries(rawPalette)) {
        palette[key] = hexToNumber(value);
      }

      // Build gradients (create callable functions)
      const rawGradients = workingSpec.gradients || {};
      const gradients = {};
      for (const [key, gradSpec] of Object.entries(rawGradients)) {
        gradients[key] = buildGradient(gradSpec, palette);
      }

      // Build context for cross-section refs (raw spec for ref: resolution)
      const context = {
        palette: rawPalette,
        gradients: rawGradients,
        shapes: workingSpec.shapes || {},
        ui: workingSpec.ui || {},
        particles: workingSpec.particles || {},
        juice: workingSpec.juice || {}
      };

      // Resolve all sections
      const resolved = {
        _rawSpec: workingSpec,
        palette,
        gradients,
        shapes: resolveObject(workingSpec.shapes || {}, context, palette, gradients),
        ui: resolveObject(workingSpec.ui || {}, context, palette, gradients),
        particles: resolveObject(workingSpec.particles || {}, context, palette, gradients),
        juice: resolveObject(workingSpec.juice || {}, context, palette, gradients)
      };

      // Cache by name
      this.themeCache.set(spec.name, resolved);
      return resolved;
    }

    // Create a theme from a name (loads from window.THEME_SPECS if available)
    static fromName(name) {
      // Check cache first
      if (this.themeCache.has(name)) {
        return this.themeCache.get(name);
      }

      // Try to load from window.THEME_SPECS (injected by build)
      if (window.THEME_SPECS && window.THEME_SPECS[name]) {
        return this.load(window.THEME_SPECS[name]);
      }

      throw new Error(`Theme "${name}" not found. Available: ${Array.from(this.themeCache.keys()).join(', ')}`);
    }

    // Merge two themes (later overrides earlier, deep merge)
    static merge(base, override) {
      if (!base || !override) return base || override;
      return deepMerge(base, override);
    }

    // Validate a spec without resolving (throws on invalid structure)
    static validate(spec) {
      validateSpec(spec);
    }

    // Register a theme spec by name (for fromName to work without window.THEME_SPECS)
    static registerTheme(name, spec) {
      this.themeCache.set(name, this.load(spec));
      return this.themeCache.get(name);
    }

    // Clear cache (for testing)
    static clearCache() {
      this.themeCache.clear();
    }
  }

  // Expose globally
  window.VisualAssetEngine = VisualAssetEngine;

})();