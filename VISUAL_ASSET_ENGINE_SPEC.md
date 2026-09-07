# Visual Asset Engine Specification

**Status:** Draft — Phase 7+ of ONDEMAND_GENERATION.md roadmap
**Date:** 2026-09-14
**Context:** All 8 harnesses hand-built, reskin pipeline verified, human play milestone pending

---

## 1. Purpose

The visual-asset engine provides a **unified, parameterized interface** for generating game visuals from a declarative **visual spec** (JSON). It sits between the reskin pipeline and the existing vendor libraries (`art.js`, `ui.js`, `particle.js`, `juice.js`), allowing a reskin to swap not just colors/params but entire visual themes without touching harness game logic.

**Goal:** A reskin brief can specify `"visual_theme": "neon"` or `"visual_theme": "minimal"` and get coherently styled sprites, UI, particles, and juice effects — all from the same harness code.

---

## 2. Non-Goals

- **Not a sprite sheet generator** — no external asset loading, no build step
- **Not an LLM prompt target** — the visual spec is authored by humans (or a future dedicated agent), not free-form generated
- **Not a replacement for harness-specific art** — harnesses can still override/create custom visuals; the engine provides *defaults* and *themeable primitives*

---

## 3. Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        RESKIN PIPELINE                          │
│  brief.json  ──► validate_brief  ──► substitute_consts  ──►    │
│                                                      inject_mraid │
└──────────────────────────┬──────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│                   VISUAL ASSET ENGINE (NEW)                     │
│  visual_spec.json ──► VisualAssetEngine.load(spec)              │
│       │                              │                           │
│       ▼                              ▼                           │
│  ┌─────────┐  ┌─────────┐  ┌─────────┐  ┌─────────┐             │
│  │ art.js  │  │ ui.js   │  │particle.│  │juice.js │             │
│  │SoftShape│  │Button,  │  │Emitter  │  │Screen   │             │
│  │Noise,   │  │Popup,   │  │Vector2  │  │Shake,   │             │
│  │Gradient │  │Progress │  │         │  │Trail,   │             │
│  └─────────┘  └─────────┘  └─────────┘  └─────────┘             │
└──────────────────────────┬──────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│                     HARNESS GAME CODE                           │
│  imports: window.Art, window.UI, window.ParticleEngine,         │
│           window.Juice (all pre-bundled by build_harness_html)  │
└─────────────────────────────────────────────────────────────────┘
```

---

## 4. Visual Spec Format (JSON)

```json
{
  "version": 1,
  "name": "neon",
  "extends": "base",                    // optional: inherit from another theme
  "palette": {
    "primary": "#33e6ff",
    "secondary": "#ff33cc",
    "accent": "#ffe14d",
    "background": "#0a0a18",
    "surface": "#14142a",
    "text": "#ffffff",
    "textMuted": "#8888aa",
    "success": "#33ff88",
    "warning": "#ff9933",
    "danger": "#ff3355"
  },
  "gradients": {
    "background": {
      "type": "radial",
      "center": [0.5, 0.5],
      "radius": 1.0,
      "stops": [
        { "stop": 0.0, "color": "palette.background" },
        { "stop": 1.0, "color": "#050510" }
      ]
    },
    "buttonPrimary": {
      "type": "linear",
      "from": [0, 0],
      "to": [0, 1],
      "stops": [
        { "stop": 0.0, "color": "palette.primary" },
        { "stop": 1.0, "color": "#0099cc" }
      ]
    }
  },
  "shapes": {
    "gem": {
      "type": "SoftCircle",
      "radius": 20,
      "feather": 4,
      "quality": 2,
      "glow": { "color": "palette.primary", "alpha": 0.25, "scale": 1.3 },
      "body": { "color": "palette.primary", "stroke": { "width": 2, "color": "#ffffff", "alpha": 0.7 } },
      "shine": { "offset": [-6, -6], "radius": 6, "color": "#ffffff", "alpha": 0.5 }
    },
    "boardBackground": {
      "type": "SoftRect",
      "padding": 8,
      "bgColor": "palette.surface",
      "bgAlpha": 0.9,
      "borderColor": "palette.primary",
      "borderAlpha": 0.4,
      "borderWidth": 2,
      "radius": 10
    }
  },
  "ui": {
    "button": {
      "states": {
        "normal": "palette.primary",
        "hover": "gradients.buttonPrimary",
        "pressed": "#0077aa",
        "disabled": "#555555"
      },
      "text": { "fontSize": "24px", "fill": "palette.text" },
      "scaleHover": 1.05,
      "scalePressed": 0.95,
      "transitionMs": 100
    },
    "progressBar": {
      "background": "palette.surface",
      "fill": "gradients.buttonPrimary",
      "text": "palette.text",
      "height": 20,
      "radius": 4
    },
    "popup": {
      "width": 400,
      "height": 300,
      "background": "palette.background",
      "borderColor": "palette.primary",
      "borderWidth": 2,
      "overlayAlpha": 0.7,
      "titleStyle": { "fontSize": "32px", "fill": "palette.text" },
      "messageStyle": { "fontSize": "24px", "fill": "palette.text" },
      "buttonStyle": "ref:ui.button"
    }
  },
  "particles": {
    "matchBurst": {
      "count": 12,
      "life": 600,
      "speed": 120,
      "angleVariance": 180,
      "startSize": 6,
      "endSize": 0,
      "startColor": "palette.accent",
      "endColor": "palette.primary",
      "startAlpha": 1,
      "endAlpha": 0,
      "gravity": 50
    },
    "comboTrail": {
      "emitRate": 30,
      "life": 400,
      "speed": 40,
      "angleVariance": 30,
      "startSize": 4,
      "endSize": 1,
      "startColor": "palette.success",
      "endColor": "palette.primary",
      "startAlpha": 0.8,
      "endAlpha": 0
    }
  },
  "juice": {
    "screenShake": { "intensity": 8, "duration": 120 },
    "cameraFlash": { "color": "palette.accent", "duration": 80, "alpha": 0.3 },
    "scorePopup": {
      "fontSize": "28px",
      "fill": "palette.accent",
      "stroke": "#000000",
      "strokeThickness": 3,
      "floatDistance": 40,
      "floatDuration": 800,
      "fadeDuration": 800
    },
    "gemSelectionHighlight": {
      "color": "palette.accent",
      "alpha": 0.6,
      "pulseDuration": 600,
      "pulseAlphaRange": [0.3, 0.8]
    },
    "swapAnimation": {
      "duration": 150,
      "ease": "Cubic.easeOut",
      "revertShake": true
    },
    "cascade": {
      "fallSpeed": 600,
      "bounce": 0.15,
      "newGemDelay": 60,
      "matchFlashDuration": 100,
      "matchFlashColor": "palette.accent"
    },
    "introBanner": {
      "label": "SWAP TO MATCH 3+",
      "fontSize": "20px",
      "fill": "palette.accent",
      "background": "palette.surface",
      "slideDuration": 400
    },
    "movesCounter": {
      "warnThreshold": 5,
      "normalColor": "palette.text",
      "warnColor": "palette.danger",
      "fontSize": "18px"
    },
    "gameOverPanel": {
      "won": {
        "title": "LEVEL COMPLETE",
        "titleColor": "palette.success",
        "background": "palette.surface",
        "borderColor": "palette.success"
      },
      "lost": {
        "title": "OUT OF MOVES",
        "titleColor": "palette.danger",
        "background": "palette.surface",
        "borderColor": "palette.danger"
      },
      "scoreColor": "palette.accent",
      "targetColor": "palette.textMuted",
      "buttonStyle": "ref:ui.button",
      "ctaText": "PLAY NOW"
    }
  }
}
```

**Key features of the format:**
- **Palette references** — `"palette.primary"` resolves to the palette color
- **Gradient references** — `"gradients.buttonPrimary"` resolves to a gradient function
- **Cross-section references** — `"ref:ui.button"` reuses another section
- **Inheritance** — `"extends": "base"` merges with base theme (deep merge)
- **All values are serializable JSON** — no functions, no code

---

## 5. Engine API (TypeScript-style pseudocode)

```typescript
// pipeline/visual_asset_engine.js (new file)

class VisualAssetEngine {
  // Load a visual spec, resolve all references, return a frozen theme object
  static load(spec: VisualSpec): ResolvedTheme;

  // Create a theme from a name (loads from pipeline/vendor/themes/<name>.json)
  static fromName(name: string): ResolvedTheme;

  // Merge two themes (later overrides earlier, deep merge)
  static merge(base: ResolvedTheme, override: Partial<ResolvedTheme>): ResolvedTheme;

  // Validate a spec without resolving (throws on invalid structure)
  static validate(spec: VisualSpec): void;
}

// ResolvedTheme is a plain object with all references resolved:
// {
//   palette: { primary: 0x33e6ff, ... },  // all colors as 0xRRGGBB numbers
//   gradients: { background: (x,y)=>0xRRGGBB, ... },  // ready-to-call functions
//   shapes: { gem: { ...resolved options... }, ... },
//   ui: { button: { states: { normal: 0x33e6ff, ... }, ... }, ... },
//   particles: { matchBurst: { ...resolved options... }, ... },
//   juice: { screenShake: { intensity: 8, ... }, ... }
// }

// Usage in harness game code:
const theme = VisualAssetEngine.fromName('neon');
// or for reskin:
const theme = VisualAssetEngine.load(brief.visual_theme);

// Then pass theme to factory functions:
const gem = Art.SoftCircle.create(scene, x, y, theme.shapes.gem);
const btn = UI.Button.create(scene, x, y, 'PLAY', theme.ui.button, onClick);
const emitter = ParticleEngine.ParticleEmitter.create(theme.particles.matchBurst);
Juice.ScreenShake.trigger(scene, theme.juice.screenShake);
```

---

## 6. Integration Points

### 6.1 Reskin Pipeline (`pipeline/reskin.py`)

Add a new step after `inject_mraid_gating`:

```python
def apply_visual_theme(reskinned_js: str, brief: dict, manifest: dict) -> str:
    """Inject the resolved visual theme into the game JS as a global constant."""
    theme_name = brief.get("visual_theme", "default")
    theme_path = Path(__file__).parent.parent / "vendor" / "themes" / f"{theme_name}.json"
    if not theme_path.exists():
        return reskinned_js  # no theme = use harness defaults

    spec = load_json(theme_path)
    # Validate spec
    VisualAssetEngine.validate(spec)  # Python-side validation (mirror of JS)
    # Resolve theme
    theme = VisualAssetEngine.load(spec)
    # Serialize as JS constant
    theme_js = f"const VISUAL_THEME = {json.dumps(theme, separators=(',', ':'))};\n"
    return theme_js + reskinned_js
```

### 6.2 Build Script (`scripts/build_harness_html.sh`)

No changes needed — the engine JS is just another vendor file bundled alongside juice.js.

### 6.3 Vendor Bundle

Add `pipeline/vendor/visual_asset_engine.js` to the vendor bundle in `build_harness_html.sh`:

```bash
cat pipeline/vendor/phaser.min.js
cat pipeline/vendor/juice.js
cat pipeline/vendor/art.js
cat pipeline/vendor/ui.js
cat pipeline/vendor/particle.js
cat pipeline/vendor/visual_asset_engine.js   # NEW
cat pipeline/vendor/mraid.js                # if INCLUDE_MRAID=true
cat "${SRC_GAME_JS}"
```

### 6.4 Harness Game Code (Optional Adoption)

Harnesses **opt in** by reading `window.VISUAL_THEME` if present:

```javascript
// In harness .game.js create():
const theme = window.VISUAL_THEME || DEFAULT_THEME;  // fallback to hardcoded

// Use theme for gem visuals
const gemSprite = Art.SoftCircle.create(this, x, y, theme.shapes.gem);

// Use theme for UI
this.retryButton = UI.Button.create(this, x, y, 'RETRY', theme.ui.button, () => ...);

// Use theme for particles
const burst = ParticleEngine.ParticleEmitter.create(theme.particles.matchBurst);

// Use theme for juice
Juice.ScreenShake.trigger(this, theme.juice.screenShake);
```

**Backward compatibility:** If `VISUAL_THEME` is not defined (e.g., running the raw harness HTML without reskin), the harness uses its own hardcoded constants — **no behavior change for existing harness HTML files.**

---

## 7. File Structure Changes

```
pipeline/
├── vendor/
│   ├── art.js                 (existing)
│   ├── ui.js                  (existing)
│   ├── particle.js            (existing)
│   ├── juice.js               (existing)
│   ├── mraid.js               (existing)
│   ├── visual_asset_engine.js (NEW — this spec)
│   └── themes/                (NEW directory)
│       ├── base.json          (NEW — minimal fallback theme)
│       ├── neon.json          (NEW — example from Section 4)
│       ├── minimal.json       (NEW — low-juice variant)
│       └── retro.json         (NEW — pixel-art style variant)
├── visual_asset_engine.py     (NEW — Python-side validation/resolution for reskin)
└── reskin.py                  (MODIFIED — add apply_visual_theme step)
scripts/
└── build_harness_html.sh      (MODIFIED — add visual_asset_engine.js to bundle)
```

---

## 8. Implementation Phases

### Phase 7A: Core Engine (this spec → code)
- [ ] Write `pipeline/vendor/visual_asset_engine.js` implementing the API in Section 5
- [ ] Write `pipeline/visual_asset_engine.py` with `load()`, `validate()`, `merge()` for reskin pipeline
- [ ] Create `pipeline/vendor/themes/base.json` (minimal valid theme)
- [ ] Update `scripts/build_harness_html.sh` to include `visual_asset_engine.js`
- [ ] Update `pipeline/reskin.py` to call `apply_visual_theme` when `visual_theme` in brief

### Phase 7B: Theme Library
- [ ] Create `neon.json`, `minimal.json`, `retro.json` in `vendor/themes/`
- [ ] Add `visual_theme` field to all 8 briefs in `briefs/`
- [ ] Test reskin pipeline with `visual_theme: "neon"` for all 8 genres

### Phase 7C: Harness Adoption (Optional, per-harness)
- [ ] Update one harness (e.g., `match_3.game.js`) to read `VISUAL_THEME` and use it
- [ ] Verify reskinned build with theme looks correct
- [ ] Roll out to other harnesses as desired

---

## 9. Validation Strategy

1. **Unit tests** (Python): `pipeline/visual_asset_engine.py` — spec loading, reference resolution, inheritance, merge
2. **Unit tests** (JS): `visual_asset_engine.js` — same, runnable in Node or browser console
3. **Integration test**: Reskin pipeline with `visual_theme` produces HTML that passes Playwright verification
4. **Visual regression**: Screenshot comparison of themed vs non-themed harness (manual)

---

## 10. Risks & Mitigations

| Risk | Mitigation |
|------|------------|
| Theme JSON grows too large | Keep themes focused; split into `base` + small overrides |
| Harnesses diverge in theme usage | Document expected theme keys; validate in `VisualAssetEngine.validate()` |
| Performance (RenderTexture creation) | Themes are resolved once at load; factories cache RenderTextures per shape config |
| Circular references in spec | `validate()` detects cycles in `extends` and `ref:` |

---

## 11. Acceptance Criteria for Phase 7A

- [ ] `visual_asset_engine.js` loads in browser, exposes `VisualAssetEngine` globally
- [ ] `VisualAssetEngine.fromName('base')` returns a fully resolved theme object
- [ ] `VisualAssetEngine.load(spec)` resolves all `palette.*`, `gradients.*`, `ref:*` references
- [ ] `VisualAssetEngine.validate(spec)` throws on invalid structure (missing required keys, unknown refs, cycles)
- [ ] `pipeline/visual_asset_engine.py` mirrors JS behavior (same inputs → same resolved theme)
- [ ] `scripts/build_harness_html.sh` bundles `visual_asset_engine.js` without errors
- [ ] `pipeline/reskin.py` injects `VISUAL_THEME` constant when brief has `visual_theme`
- [ ] All 8 existing reskin e2e tests still pass (no regression)
- [ ] New test: reskin with `visual_theme: "base"` passes Playwright verification

---

## 12. Future Extensions (Post-Phase 7)

- **Procedural sprite atlas**: Generate a single texture atlas from theme shapes at load time
- **Theme variants per placement**: `visual_theme_interstitial`, `visual_theme_rewarded` in brief
- **LLM-assisted theme generation**: A dedicated agent that writes theme JSON from a mood board
- **Dynamic theme switching**: `VisualAssetEngine.applyTheme(newTheme)` for live preview

---

*End of spec. Ready for implementation review.*