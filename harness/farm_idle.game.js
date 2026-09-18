// Hand-built farm idle harness. Arcade idle genre (My Perfect Hotel / Pizza Ready family).
// Theme: farm life. Core loop: joystick move farmer -> harvest plot -> sell at stall -> buy upgrades.

const LOGICAL_W = 720;  // Logical world width (fixed reference)
let W = LOGICAL_W;     // Current logical width (may change with zoom under RESIZE)
let H = 1412;          // Current logical height (dynamic under RESIZE)

const WORLD_W = 1440;  // Fixed logical world width -- independent of viewport, never changes on resize
const WORLD_H = 2000;  // Fixed logical world height -- independent of viewport, never changes on resize

// RESIZE mode: worldZoom = viewportWidth / LOGICAL_W
// visibleWorldHeight = viewportHeight / worldZoom
// This preserves uniform world scaling — no stretched circles/hit targets.
let worldZoom = 1.0;       // computed on resize: viewportWidth / LOGICAL_W
let visibleWorldHeight = H; // computed on resize: viewportHeight / worldZoom
let viewportWidth = 0;      // current CSS viewport width
let viewportHeight = 0;     // current CSS viewport height
const CTA_LINK = "https://example.com/game";

const STATE = { START: 'start', PLAYING: 'playing' };

// Farmer
const MOVE_SPEED = 300;       // logical pixels/sec (was 150, ~2x for brisk feel)
const FARMER_RADIUS = 32;     // 20 * 1.6

// Joystick (floating, display-on-touch)
const JOYSTICK_RADIUS = 80;   // visual/logical radius of the joystick base

// Auto-collect magnet
const MAGNET_RADIUS = 60;     // coins/crops within this radius fly to farmer automatically
const START_HINT_DISMISS_DIST = 100;  // farmer must move this far from spawn to auto-dismiss the start hint

// Carry stack (real-device defect #1 fix): the carried-crop stack has an
// explicit, enforced upper bound. Without this, _addToCarryStack() grew the
// stack (and its per-item radius/Y offset) forever whenever crops were
// harvested faster than they could be sold -- a real-device screenshot
// showed dozens of stacked sprites spiraling outward. Harvesting is blocked
// once the stack is full (see _harvestPlot / _updateHelper) rather than
// silently dropping the crop, so nothing is lost -- the plot just stays
// ready until the player (or helper) sells and frees capacity.
const CARRY_STACK_MAX = 8;
// Goods added to the carry stack per single harvest (defect #5: a harvest
// must visibly burst multiple goods, not add exactly one), bounded by
// CARRY_STACK_MAX -- see _addHarvestBurst().
const HARVEST_BURST_SIZE = 3;

// Plots
const PLOT_COUNT = 5;
const PLOT_SIZE = 96;         // 60 * 1.6
const PLOT_GAP = 16;          // 10 * 1.6
const CROP_GROW_MS = 4000;
const CROP_SELL_VALUE = 10;

// Collectible type registry: sell values, weights, colors, yields
const COLLECTIBLE_TYPES = {
  crop: {
    sellValue: 10, weight: 1,
    carryColor: 0x8bc34a, carryStroke: 0x4caf50,
    worldColor: 0x8bc34a,
    playerYield: 3, helperYield: 1,
    receivesPlotSellBonus: true,
  },
  egg: {
    sellValue: 15, weight: 1,
    carryColor: 0xfff3c4, carryStroke: 0xf9a825,
    worldColor: 0xfff3c4,
    playerYield: 1, helperYield: 1,
    receivesPlotSellBonus: false,
  },
};

// Upgrade: More Crop Plots (repeatable)
const PLOT_UPGRADE_BASE_COST = 50;
const PLOT_UPGRADE_COST_GROWTH = 150;

// Upgrade: Faster Movement Boots (fixed chain, 3 tiers)
const BOOTS_UPGRADE_COST_T1 = 100;
const BOOTS_UPGRADE_COST_T2 = 250;
const BOOTS_UPGRADE_COST_T3 = 500;
const BOOTS_SPEED_MULT = 1.3;

// Upgrade: Helper Animal (fixed chain, 2 tiers)
const HELPER_UPGRADE_COST_T1 = 200;
const HELPER_UPGRADE_COST_T2 = 500;
const HELPER_INTERVAL_T1 = 8000;
const HELPER_INTERVAL_T2 = 4000;
const HELPER_MAX_CARRY = 3;  // helper carries up to 3 crops before selling

// CTA
const CTA_ENABLED = 0;

// Haptics
const HAPTICS_ENABLED = 1;

// Colors (substitutable via manifest COLORS param)
const COLORS = [0x8bc34a, 0xffd700, 0xe65100, 0xffb300, 0xff7043, 0x8d6e63];

// Layout constants (all scaled 1.6x from 450x800 base)
const PLOT_AREA_TOP = 192;            // 120 * 1.6
const PLOTS_PER_ROW = Math.floor((W - PLOT_GAP) / (PLOT_SIZE + PLOT_GAP));  // 6
const MAX_PLOT_ROWS = 3;
const MAX_PLOTS = PLOTS_PER_ROW * MAX_PLOT_ROWS;  // 18
const PLOT_BUFF_SELL_VALUE_BONUS = 2;
const PLOT_BUFF_GROW_SPEED_MULT = 0.92;
const PLOT_BUFF_MIN_GROW_MS = 500;
const STALL_X = 96;                   // 60 * 1.6
// STALL_Y/PAD_Y below are unused legacy placeholders (fixed-world sub-dispatch):
// the stall and pad's live positions are now solely determined by
// _computeStallLayout() / _computePadLayout(), which return fixed world
// coordinates independent of viewport size or safe-area insets. Nothing
// reads STALL_Y/PAD_Y anymore -- kept only so this diff stays additive.
const STALL_Y = 1252;                 // 1412 - 112 - 48 = 1252 (legacy, unused)
const STALL_W = 160;                  // 100 * 1.6
const STALL_H = 112;                  // 70 * 1.6
const PAD_X = 464;                    // (W - PAD_W) = 720 - 256 = 464, was 390 = 450 - 60
const PAD_Y = 1252;                   // 1412 - 112 - 48 = 1252 (legacy, unused)
const PAD_W = 256;                    // 160 * 1.6
const PAD_H = 112;                    // 70 * 1.6
const COINS_Y = 64;                   // 40 * 1.6
const WORLD_BACKGROUND_COLOR = '#8fbc8f';  // named so it/textures can be swapped without hunting magic values
// Fixed world Y coordinates for the stall and upgrade pad (this sub-dispatch).
// The plot grid's maximum extent is PLOT_AREA_TOP(192) + 96 + (MAX_PLOT_ROWS-1)*(PLOT_SIZE+PLOT_GAP) + PLOT_SIZE
// = 192 + 96 + 2*112 + 96 = 608. WORLD_H is 2000, so 700/900 leave a comfortable
// gap below the plot grid with room to spare and no overlap between stall and pad.
const STALL_FIXED_Y = 700;
const PAD_FIXED_Y = 900;
const UPGRADE_PANEL_TOP = 672;        // 420 * 1.6

// Safe-area insets (CSS pixels, updated on resize)
let safeInsets = { top: 0, right: 0, bottom: 0, left: 0 };
let isLandscape = false;
let rotateOverlay = null;

// Haptic vibration helper
function vibrate(ms) {
  if (!HAPTICS_ENABLED) return;
  if (typeof navigator !== 'undefined' && navigator.vibrate) {
    try { navigator.vibrate(ms); } catch (e) { /* iOS Safari throws if not supported */ }
  }
}

// Read safe-area insets from CSS custom properties
function updateSafeInsets() {
  const style = getComputedStyle(document.documentElement);
  safeInsets = {
    top: parseInt(style.getPropertyValue('--safe-top') || '0', 10),
    right: parseInt(style.getPropertyValue('--safe-right') || '0', 10),
    bottom: parseInt(style.getPropertyValue('--safe-bottom') || '0', 10),
    left: parseInt(style.getPropertyValue('--safe-left') || '0', 10)
  };
}

// Initial read
updateSafeInsets();
window.addEventListener('resize', () => {
  updateSafeInsets();
  const scene = window.__GAME__?.scene?.scenes?.[0];
  if (scene && scene._layoutHUD) scene._layoutHUD();
});

class PlayScene extends Phaser.Scene {
  constructor() {
    super('PlayScene');
  }

  create() {
    this.state = STATE.START;
    this.game.state = STATE.START;
    this.coins = 0;
    this.carrying = null;
    this.farmerTarget = null;
    this.isDragging = false;
    this.joystickActive = false;
    this.joystickCenter = null;
    this.joystickThumb = null;
    this.joystickBase = null;
    this.joystickVector = { x: 0, y: 0 };

    this.plots = [];
    this.producers = [];

    this.plotUpgradeCount = 0;
    this.bootsTier = 0;
    this.helperTier = 0;
    this.helperTimer = 0;
    this.helpers = [];
    this.sellValueBonus = 0;
    this.growSpeedMult = 1;
    this.plotGridCapped = false;
    this.chickenTier = 0;
    this.coop = null;

    this.cameras.main.setBackgroundColor(WORLD_BACKGROUND_COLOR);

    // Section D: two-camera split (world camera follows/zooms/scrolls; a
    // second, non-following UI camera renders HUD, its own scroll fixed by
    // centerOn rather than by startFollow).
    //
    // A same-camera setScrollFactor(0) fix was tried and rejected first --
    // measured pixel evidence showed HUD objects rendering offset by
    // roughly the world camera's own scroll amount. Root cause (confirmed
    // by Instinct's reviewer against Phaser 3.80.1 source): unrelated to
    // scrollFactor -- forcing the UI camera's scroll to literal (0,0) is
    // WRONG given Phaser's default camera origin is centered (0.5, 0.5),
    // not top-left. With a centered origin, scroll=(0,0) does NOT place
    // logical (0,0) at the physical top-left corner -- it centers the
    // camera around a point offset by the origin, which is exactly the
    // wrong-looking offset that was pixel-measured. The correct way to pin
    // logical (0,0) at physical (0,0) top-left, at ANY origin setting, is
    // `camera.centerOn(LOGICAL_W / 2, visibleWorldHeight / 2)` -- Phaser
    // computes the scroll value THAT centering actually requires (not
    // simply (0,0)) and that's what must be called every resize, not
    // setScroll(0,0). See _onResize for where this is applied.
    //
    // Groups (not Containers) track membership only -- no reparenting, no
    // coordinate-space change, so every existing x/y calculation elsewhere
    // in this file (_layoutHUD, _computeTopHudLayout, _activateJoystick's
    // pointer/worldZoom math, etc.) keeps working completely unchanged.
    // camera.ignore(group) is NOT a live subscription: objects added to a
    // group AFTER ignore() was called on that group are not automatically
    // ignored. _registerWorldObject/_registerHudObject below apply the
    // ignore() to each object individually, at registration time, so this
    // is correct however/whenever an object is created -- always register
    // through one of these two methods, never add to worldGroup/hudGroup
    // directly.
    this.worldGroup = this.add.group();
    this.hudGroup = this.add.group();

    // UI camera: same zoom as the world camera (worldZoom, set in
    // _onResize) -- every HUD layout function in this file already reasons
    // in the 720-logical-width coordinate system that worldZoom scales to
    // the physical viewport, so matching zooms means none of that math
    // needs to change, only which camera renders the result. Placeholder
    // viewport here; _onResize resizes it to the real dimensions on the
    // very next resize tick (which Phaser's RESIZE scale mode fires
    // automatically shortly after boot). Transparent background (no
    // backgroundColor set) so it never paints over the world camera's
    // render beneath it. Never call setBounds on this camera -- it must
    // never be capable of scrolling under its own logic (no follow, no
    // input pan) -- its scroll only ever moves because centerOn recomputes
    // it deliberately on resize.
    this.uiCamera = this.cameras.add(0, 0, 1, 1);
    this.uiCamera.setName('ui');
    // Cameras render in this.cameras.cameras array order, earliest first --
    // uiCamera, added after the default main camera, already renders last
    // (on top) without needing explicit reordering.

    // _registerWorldObject(obj): obj is a world entity (moves with the
    // world camera's scroll/follow). Adds it to worldGroup for bookkeeping
    // and immediately makes the UI camera ignore it, so it can never be
    // double-rendered or hit-tested against the wrong camera's transform.
    this._registerWorldObject = (obj) => {
      this.worldGroup.add(obj);
      this.uiCamera.ignore(obj);
      return obj;
    };
    // _registerHudObject(obj): obj is a screen-fixed HUD entity. Adds it to
    // hudGroup and immediately makes the WORLD camera ignore it.
    this._registerHudObject = (obj) => {
      this.hudGroup.add(obj);
      this.cameras.main.ignore(obj);
      return obj;
    };
    // _withNewChildrenRegistered(registerFn, factoryCall): several Juice
    // effects (ParticleBurst, TapHint) create 1-N new display objects
    // internally and don't return references to them -- factoryCall runs,
    // then every scene child created during that call (diffed by
    // this.children.list length before/after) is passed to registerFn.
    // Necessary so short-lived particles/effects are never left
    // unregistered (which would render them in BOTH cameras).
    this._withNewChildrenRegistered = (registerFn, factoryCall) => {
      const startLen = this.children.list.length;
      const result = factoryCall();
      for (let i = startLen; i < this.children.list.length; i++) {
        registerFn(this.children.list[i]);
      }
      return result;
    };

    // --- Build static world ---
    this.grassG = this.add.graphics();
    this.grassG.fillStyle(0x7cb342, 1);
    this.grassG.fillRect(0, PLOT_AREA_TOP, W, H - PLOT_AREA_TOP);
    this._registerWorldObject(this.grassG);

    for (let i = 0; i < PLOT_COUNT; i++) {
      const pos = this._plotPosition(i);
      this._createPlot(i, pos.x, pos.y);
    }

    // Farmer
        this.farmer = this.add.circle(W / 2, PLOT_AREA_TOP + 320, FARMER_RADIUS, 0xe65100);
        this.farmer.setStrokeStyle(5, 0xbf360c, 1);
        this.farmer.setDepth(10);  // gameplay foreground, above plots
        this._registerWorldObject(this.farmer);

    this.cameras.main.startFollow(this.farmer, true, 0.12, 0.12);
    this.cameras.main.roundPixels = true;

    // Carried crop indicator - now a stack container
        this.carryStack = this.add.container(this.farmer.x, this.farmer.y - 56);
        this.carryStack.setDepth(10);  // gameplay foreground, above plots
        this.carryStack.setVisible(false);
        this._registerWorldObject(this.carryStack);
    this.carryItems = [];
    Object.defineProperty(this, 'carrySprites', {
      get() { return this.carryItems.map(item => item.sprite); },
      configurable: true,
    });

    // Explicit visible capacity readout for the carry stack (defect #5 /
    // ties directly into the defect #1 cap fix): shows current/max so the
    // bound is legible to the player, not just enforced silently.
    this.carryCountText = this.add.text(0, -70, '', {
      fontFamily: 'monospace', fontSize: '16px', color: '#fff'
    }).setOrigin(0.5);
    this.carryStack.add(this.carryCountText);
    // Registered individually, not just via the parent carryStack -- Group
    // membership/ignore() on a Container is not guaranteed to recurse to
    // children (Instinct reviewer condition 3).
    this._registerWorldObject(this.carryCountText);

    // Backward compatibility for tests
    this.carrying = null;
    this.carryIndicator = {
      x: this.farmer.x,
      y: this.farmer.y - 56,
      visible: false,
      setVisible: function(val) { this.visible = val; },
      getBounds: () => ({ x: this.farmer.x - 19, y: this.farmer.y - 75, width: 38, height: 38 })
    };

    // Coins display (HUD - will be repositioned on resize) - TOP LEFT
    this.coinsText = this.add.text(16, COINS_Y, 'Coins: 0', {
      fontFamily: 'monospace', fontSize: '38px', color: '#000'
    }).setOrigin(0, 0.5);
    this._registerHudObject(this.coinsText);

    // Progress bar top-center: coins toward the next affordable upgrade
        // (real-device defect #4 -- see _cheapestUpgradeCost()).
        this.progressBarBg = this.add.rectangle(W / 2, COINS_Y, 400, 24, 0x222222, 0.7);
                 this.progressBarBg.setDepth(0);  // bg layer, below fill and text
                 this.progressBarBg.setStrokeStyle(2, 0x444444, 1);
        this.progressBarFill = this.add.rectangle(W / 2 - 200 + 4, COINS_Y, 0, 16, 0xffd700, 1);
        this.progressBarFill.setOrigin(0, 0.5);
        this.progressBarFill.setDepth(1);  // above bg, below text
        this.progressText = this.add.text(W / 2, COINS_Y, 'Next upgrade: 0 / ' + PLOT_UPGRADE_BASE_COST, {
          fontFamily: 'monospace', fontSize: '18px', color: '#fff',
          stroke: '#000', strokeThickness: 4
        }).setOrigin(0.5).setDepth(2);  // text with black outline on top
        this._registerHudObject(this.progressBarBg);
        this._registerHudObject(this.progressBarFill);
        this._registerHudObject(this.progressText);

    // HUD container -- the upgrade sheet (built in _openUpgradeSheet) is
    // added into this. Registered as HUD itself, but per Instinct reviewer
    // condition 3, its children are ALSO registered individually at their
    // own creation sites (in _openUpgradeSheet) rather than relying on this
    // container-level registration to recurse.
    this.hudContainer = this.add.container(0, 0);
    this.hudContainer.setDepth(1000);
    this._registerHudObject(this.hudContainer);

    // Upgrade pad (in-world affordance) - tapping opens bottom sheet
    this.padG = this.add.graphics();
    this.padG.fillStyle(0xffb300, 1);
    this.padG.fillRoundedRect(0, 0, PAD_W, PAD_H, 8);
    this.padG.setInteractive(new Phaser.Geom.Rectangle(0, 0, PAD_W, PAD_H), Phaser.Geom.Rectangle.Contains);
    this.padG.on('pointerdown', () => this._openUpgradeSheet());
    this.padText = this.add.text(PAD_X + PAD_W / 2, PAD_Y + PAD_H / 2, 'UPGRADES', {
      fontFamily: 'monospace', fontSize: '20px', color: '#000', align: 'center'
    }).setOrigin(0.5);
    this._registerWorldObject(this.padG);
    this._registerWorldObject(this.padText);

    // Stall
    this.stallG = this.add.graphics();
    this.stallG.fillStyle(0x8b4513, 1);
    this.stallG.fillRoundedRect(0, 0, STALL_W, STALL_H, 8);
    this.stallG.fillRect(16, -32, STALL_W - 32, 32);
    this.stallText = this.add.text(STALL_X + STALL_W / 2, STALL_Y + STALL_H / 2, 'MARKET', {
      fontFamily: 'monospace', fontSize: '20px', color: '#fff', align: 'center'
    }).setOrigin(0.5);
    this._registerWorldObject(this.stallG);
    this._registerWorldObject(this.stallText);

    // Start hint (replaces persistent banner) - tap/arrow hint near farmer
    this.startHint = this.add.graphics();
    this.startHint.setVisible(false);
    this.startHintText = this.add.text(0, 0, 'TAP TO MOVE', {
      fontFamily: 'monospace', fontSize: '24px', color: '#fff',
      backgroundColor: '#2e7d32', padding: { x: 16, y: 8 }
    }).setOrigin(0.5).setVisible(false);
    this.startHintPulse = null;
    this._registerWorldObject(this.startHint);
    this._registerWorldObject(this.startHintText);

    // Upgrade bottom sheet (modal, in HUD layer)
    this.upgradeSheet = null;
    this.sheetVisible = false;

    // Intro banner + tap hint (using Juice). y comes from the same shared
    // top-HUD layout as coinsText/progressBar (_computeTopHudLayout()), but
    // that alone is NOT sufficient: real safe-area insets are often not
    // known yet at this point in create() (they arrive later via a CSS/
    // MRAID update), so a Y computed once HERE can go stale the moment
    // _layoutHUD() next runs with the real values -- coinsText/progressBar
    // get repositioned then, the banner did not, and the two drifted apart
    // again exactly like the first fix's bug. Fixed properly this time:
    // find the banner's actual text object (IntroBanner.create() only
    // returns a destroy() closure, not the object) and keep a reference so
    // _layoutHUD() can reposition it on every real layout pass, the same
    // as every other top-HUD element, for as long as it's still alive.
    const { bannerY } = this._computeTopHudLayout();
        const introBanner = Juice.IntroBanner.create(this, { label: 'HARVEST \u2022 SELL \u2022 UPGRADE', y: bannerY, color: '#e65100' });
    this._introBannerText = this.children.list[this.children.list.length - 1];
    this._registerHudObject(this._introBannerText);
    // TapHint is positioned at the farmer's world coordinates -- world object.
    const introHint = this._withNewChildrenRegistered(
      this._registerWorldObject,
      () => Juice.TapHint.create(this, this.farmer.x, this.farmer.y, { color: 0xe65100, radius: 64 })
    );
    this.time.delayedCall(2500, () => {
      introBanner.destroy();
      introHint.destroy();
      this._introBannerText = null;
    });

    // Input: Floating joystick (touch/click anywhere in play area)
    // Pointerdown starts the joystick at the pointer position
    this.input.on('pointerdown', (pointer) => {
      if (isLandscape) {
        return;
      }
      // Input arbitration: don't activate joystick if pointer is over
      // an interactive UI element (BUY buttons, etc.) - prevents
      // accidental joystick spawn when tapping UI.
      const hits = this.input.hitTestPointer(pointer);
      if (hits.length > 0) {
        return;
      }
      this._begin();
      this._activateJoystick(pointer.x, pointer.y);
    });

    // Pointermove updates the joystick vector
    this.input.on('pointermove', (pointer) => {
      if (!this.joystickActive || isLandscape) {
        return;
      }
      this._updateJoystick(pointer.x, pointer.y);
    });

    // Pointerup hides the joystick
    this.input.on('pointerup', () => {
      if (this.joystickActive) {
        this._deactivateJoystick();
      }
    });

    // Also handle gameout (pointer leaves the game canvas) - deactivate
    // joystick. Deliberately NOT 'pointerout': Phaser's scene-level input
    // plugin also emits 'pointerout' whenever the pointer moves off ANY
    // interactive game object underneath it (processOverOutEvents, called
    // every frame from updateInputPlugins) -- not just when it leaves the
    // canvas. With 'pointerout' here, dragging the joystick across the
    // upgrade pad's hit area (padG, setInteractive()) fired this handler
    // and killed the joystick mid-drag, well within canvas bounds. Root-
    // caused via live instrumentation (wrapped _deactivateJoystick,
    // captured the call stack: onMouseMove -> updateInputPlugins -> update
    // -> processOverOutEvents -> emit('pointerout')). 'gameout' is Phaser's
    // actual InputManager-level canvas-leave event, unaffected by what's
    // underneath the pointer.
    this.input.on('gameout', () => {
      if (this.joystickActive) {
        this._deactivateJoystick();
      }
    });

    this.input.keyboard.on('keydown-SPACE', () => { if (!isLandscape) this._begin(); });

    // Scale Manager resize handler - re-anchor HUD elements
    this.scale.on('resize', this._onResize, this);

    // Orientation detection
    this._checkOrientation();
    window.addEventListener('orientationchange', () => this._checkOrientation());
    window.matchMedia('(orientation: landscape)').addEventListener('change', (e) => this._checkOrientation());

    window.__GAME__ = this.game;
    this.game.registry.set('score', 0);

    // Initial HUD layout
    this._layoutHUD();
  }

  _activateJoystick(x, y) {
    // Clamp joystick center to playable area (above upgrade sheet, in logical coords)
    const layout = this.computeLayout();
    const maxY = layout.visibleWorldHeight - JOYSTICK_RADIUS;
    const clampedY = Phaser.Math.Clamp(y / layout.worldZoom, JOYSTICK_RADIUS, maxY);
    const clampedX = Phaser.Math.Clamp(x / layout.worldZoom, JOYSTICK_RADIUS, LOGICAL_W - JOYSTICK_RADIUS);

    this.joystickCenter = { x: clampedX, y: clampedY };
    this.joystickActive = true;
    this.joystickVector = { x: 0, y: 0 };

    // Create joystick base (visual)
    this.joystickBase = this.add.circle(clampedX, clampedY, JOYSTICK_RADIUS, 0x4caf50, 0.3);
    this.joystickBase.setStrokeStyle(3, 0x2e7d32, 0.8);
    this._registerHudObject(this.joystickBase);

    // Create joystick thumb (visual)
    this.joystickThumb = this.add.circle(clampedX, clampedY, JOYSTICK_RADIUS * 0.5, 0x8bc34a, 0.8);
    this.joystickThumb.setStrokeStyle(2, 0x2e7d32, 1);
    this._registerHudObject(this.joystickThumb);
  }

  _updateJoystick(x, y) {
    if (!this.joystickCenter) return;

    // Convert screen pointer coords to logical coords for clamping
    const layout = this.computeLayout();
    const logX = x / layout.worldZoom;
    const logY = y / layout.worldZoom;

    // Calculate vector from center to current pointer position (logical coords)
    let dx = logX - this.joystickCenter.x;
    let dy = logY - this.joystickCenter.y;
    const dist = Math.sqrt(dx * dx + dy * dy);

    // Clamp input vector magnitude to 1.0 (don't stop at visual edge)
    if (dist > JOYSTICK_RADIUS) {
      dx = (dx / dist) * JOYSTICK_RADIUS;
      dy = (dy / dist) * JOYSTICK_RADIUS;
    }

    // Normalize to [-1, 1] range for movement
    this.joystickVector.x = dx / JOYSTICK_RADIUS;
    this.joystickVector.y = dy / JOYSTICK_RADIUS;

    // Move thumb visually (clamped to visual radius)
    if (this.joystickThumb) {
      this.joystickThumb.x = this.joystickCenter.x + dx;
      this.joystickThumb.y = this.joystickCenter.y + dy;
    }
  }

  _deactivateJoystick() {
    this.joystickActive = false;
    this.joystickVector = { x: 0, y: 0 };
    this.joystickCenter = null;

    if (this.joystickBase) {
      this.joystickBase.destroy();
      this.joystickBase = null;
    }
    if (this.joystickThumb) {
      this.joystickThumb.destroy();
      this.joystickThumb = null;
    }
  }

  _checkOrientation() {
    const wasLandscape = isLandscape;
    const isTouchDevice = window.matchMedia('(pointer: coarse)').matches
      || navigator.maxTouchPoints > 0;
    isLandscape = isTouchDevice && window.matchMedia('(orientation: landscape)').matches;

    if (isLandscape && !wasLandscape) {
      this._showRotateOverlay();
      // No permanent upgrade panel - use modal bottom sheet instead
      if (this.upgradeSheet) this.upgradeSheet.setVisible(false);
    } else if (!isLandscape && wasLandscape) {
      this._hideRotateOverlay();
      updateSafeInsets();
      this._layoutHUD();
      if (this.upgradeSheet) this.upgradeSheet.setVisible(true);
    }
  }

  _onResize(gameSize, baseSize, displaySize, resolution) {
    // Required order (Section D two-camera split, Instinct's reviewer
    // condition 5, with the centerOn correction from the engine research):
    // compute worldZoom/H -> resize both viewports -> set UI zoom -> center
    // the UI camera (NOT setScroll(0,0) -- see the create() comment by
    // uiCamera's creation for why) -> setBounds ONLY on main -> deadzone/
    // follow -> _layoutHUD + sheet rebuild -> register/ignore new HUD
    // children (the sheet rebuild itself registers its own new objects via
    // _registerHudObject, so no separate step is needed here).

    // 1) Recalculate world zoom and visible world height.
    viewportWidth = displaySize.width;
    viewportHeight = displaySize.height;
    worldZoom = viewportWidth / LOGICAL_W;
    visibleWorldHeight = viewportHeight / worldZoom;
    W = LOGICAL_W;
    H = visibleWorldHeight;

    // 2) Resize BOTH camera viewports to the real physical dimensions.
    const cam = this.cameras.main;
    cam.setViewport(0, 0, viewportWidth, viewportHeight);
    this.uiCamera.setViewport(0, 0, viewportWidth, viewportHeight);

    // 3) UI zoom matches the world camera's zoom -- see the create()
    // comment by uiCamera's creation for why (every HUD layout function
    // reasons in the same 720-logical-width space worldZoom scales).
    this.uiCamera.setZoom(worldZoom);
    // Main camera zoom (uniform scale, no stretched circles/hit targets).
    cam.setZoom(worldZoom);

    // 4) Pin the UI camera so logical (0,0) lands at physical (0,0) --
    // NOT by forcing scroll to literal (0,0) (Phaser's default camera
    // origin is centered at 0.5/0.5, so scroll=(0,0) does NOT put logical
    // (0,0) at the physical top-left corner with a centered origin; that
    // was the actual root cause of the pixel-measured HUD offset in the
    // first attempt, confirmed against Phaser 3.80.1 source). centerOn
    // computes whatever scroll value is ACTUALLY required for this
    // viewport/zoom to center logical (LOGICAL_W/2, visibleWorldHeight/2)
    // -- and by construction that also places logical (0,0) at physical
    // (0,0), matching every existing HUD layout calculation in this file.
    this.uiCamera.centerOn(LOGICAL_W / 2, visibleWorldHeight / 2);

    // 5) World bounds set ONLY on the main camera, and only ever to the
    // FIXED WORLD_W/WORLD_H constants -- never derived from viewport
    // dimensions. Never call setBounds on uiCamera: giving it bounds would
    // clamp/interfere with the centerOn scroll it actually needs.
    cam.setBounds(0, 0, WORLD_W, WORLD_H);

    // 5.5) One-time explicit initial framing (Section D acceptance round,
    // "starting-hub framing"). Before this, the camera's boot position was
    // an ACCIDENTAL side-effect of startFollow's bounds-clamped settling --
    // correct by construction, but nowhere stated as intentional, so it
    // could silently regress if farmer spawn point, deadzone math, or
    // world size ever change. This makes that first-frame composition an
    // explicit, named, one-time step instead. It intentionally reproduces
    // the exact same clamped position that already resulted from
    // startFollow + setBounds (verified: identical camera.worldView before
    // and after this change, at all 4 real-device viewports) -- this is an
    // architectural change, not a visual one. Runs exactly once, on the
    // first-ever _onResize call (boot), never again on subsequent resizes
    // (e.g. orientation change) -- those must keep using ongoing
    // deadzone/follow behavior, never re-snap the camera.
    if (!this._hasFramedInitialView) {
      const targetX = Phaser.Math.Clamp(this.farmer.x, LOGICAL_W / 2, WORLD_W - LOGICAL_W / 2);
      const targetY = Phaser.Math.Clamp(this.farmer.y, visibleWorldHeight / 2, WORLD_H - visibleWorldHeight / 2);
      cam.centerOn(targetX, targetY);
      this._hasFramedInitialView = true;
    }

    // 6) Deadzone (viewport-relative, recomputed every resize) and follow.
    // startFollow itself is only called once, in create() -- nothing to
    // redo here, this step is the deadzone half of "deadzone/follow".
    cam.setDeadzone(W * 0.35, H * 0.25);

    // 7) Layout pass + upgrade sheet rebuild (registers any newly created
    // sheet children as part of its own construction, via
    // _registerHudObject -- see _openUpgradeSheet).
    updateSafeInsets();
    this._layoutHUD();
    this._layoutUpgradeSheet();
  }

  computeLayout() {
    return { worldZoom, visibleWorldHeight };
  }

  _safeBottomLogical() {
    const displayHeight = this.scale.displaySize.height;
    const scaleY = displayHeight / H;
    return safeInsets.bottom / scaleY;
  }

  // Single source of truth for EVERY top-HUD element's Y position (coins
  // counter, next-upgrade progress row, and the temporary intro slogan
  // banner). Instinct's 2nd-round review on this branch: moving only the
  // progress row in the first fix "shifted the collision, it did not
  // remove it" -- the intro banner (a separate, temporary element created
  // once in create() with its own hardcoded y, never touched by the first
  // fix) still collided with the coins label at 390x650. Computing all
  // three Ys here, stacked with guaranteed gaps derived from each
  // element's own known height, makes their bounds structurally unable to
  // intersect at any viewport -- not just the ones tested. coinsY/progressY
  // are unchanged from the first fix (already verified correct across the
  // full viewport suite); only the banner is newly computed, positioned
  // below the persistent 2-row HUD block instead of a magic-number y that
  // predated the progress row's existence.
  _computeTopHudLayout() {
    const displayHeight = this.scale.displaySize.height;
    const scaleY = displayHeight / H;
    const safeTopLogical = safeInsets.top / scaleY;

    const coinsY = Math.max(COINS_Y, safeTopLogical + 32);
    const progressY = coinsY + 36; // clears coinsText's 38px font height
    // Banner sits below the progress row with enough gap to clear the
    // progress bar's own height (24px) and its own font height (13px).
    const bannerY = progressY + 12 + 8 + 10;

    return { coinsY, progressY, bannerY };
  }

  // Single source of truth for the stall/market's live position (real-device
  // defect #3 root-cause fix). _layoutHUD() uses this to place the visible
  // stall graphics/text; _updateMagnet() (sell detection), _sellAtStall()
  // (particle effect), and helper auto-sell targeting all read the SAME
  // computed value instead of the separate STALL_Y constant, so they can
  // never drift apart from what the player actually sees on screen.
  _computeStallLayout() {
      // Fixed world position, independent of viewport size or safe-area
      // insets -- the stall is a genuine world entity now, not HUD-relative.
      return {
        x: STALL_X,
        y: STALL_FIXED_Y,
        centerX: STALL_X + STALL_W / 2,
        centerY: STALL_FIXED_Y + STALL_H / 2
      };
    }

    _computePadLayout() {
      // Fixed world position, independent of viewport size or safe-area
      // insets -- the upgrade pad is a genuine world entity now, not
      // HUD-relative. Single source of truth for every runtime consumer
      // (rendering, real-tap hit testing) so they can never drift apart.
      return {
        x: PAD_X,
        y: PAD_FIXED_Y,
        centerX: PAD_X + PAD_W / 2,
        centerY: PAD_FIXED_Y + PAD_H / 2
      };
    }

  _layoutHUD() {
      // Anchor HUD elements to screen edges with safe-area insets
      // Convert CSS safe insets to logical game coordinates
      const displayWidth = this.scale.displaySize.width;
      const displayHeight = this.scale.displaySize.height;
      const scaleX = displayWidth / W;
      const scaleY = displayHeight / H;

      const safeTopLogical = safeInsets.top / scaleY;
      const safeRightLogical = safeInsets.right / scaleX;
      const safeBottomLogical = safeInsets.bottom / scaleY;
      const safeLeftLogical = safeInsets.left / scaleX;

      // Coin counter, progress row, and (if still alive) the intro banner
      // all come from the SAME shared layout computation -- see
      // _computeTopHudLayout() -- so their bounds cannot intersect.
      const { coinsY, progressY, bannerY } = this._computeTopHudLayout();
      if (this.coinsText) {
        this.coinsText.setPosition(Math.max(16 + safeLeftLogical, 16), coinsY);
      }

      // Intro banner (temporary, ~2.5s): repositioned here on every real
      // layout pass, not just once at creation time -- real safe-area
      // insets are often not known yet when the banner is first created in
      // create(), so a Y computed only once there goes stale the instant
      // _layoutHUD() next runs with the real values (this was the actual
      // root cause of Instinct's 2nd-round HUD-collision finding).
      if (this._introBannerText) {
        this._introBannerText.setPosition(W / 2, bannerY);
      }

      // Progress bar: top-center, on its OWN row below the coin counter.
      // Real-device defect (HUD collision at 390x650): this used to share
      // the same Y as coinsText, both horizontally spanning the full HUD
      // width (coinsText left-aligned, progress bar centered) -- on a real
      // narrow-viewport render the two collided. Stacking them on separate
      // rows removes the horizontal-collision risk entirely, regardless of
      // exact viewport width or text content length, rather than trying to
      // dodge it with per-viewport pixel thresholds.
      if (this.progressBarBg && this.progressBarFill && this.progressText) {
        const y = progressY;
        this.progressBarBg.setPosition(W / 2, y);
        this.progressBarFill.setPosition(W / 2 - 200 + 4, y);
        this.progressText.setPosition(W / 2, y);
      }

      // Stall: position with safe-area bottom buffer (dynamic Y, above pad).
      // Uses _computeStallLayout() -- the single source of truth also read
      // by _updateMagnet()/_sellAtStall()/helper targeting -- so the
      // rendered position can never drift from the sell-detection target.
      if (this.stallG && this.stallText) {
        const stall = this._computeStallLayout();
        this.stallG.setPosition(stall.x, stall.y);
        this.stallG.clear();
        this.stallG.fillStyle(0x8b4513, 1);
        this.stallG.fillRoundedRect(0, 0, STALL_W, STALL_H, 8);
        this.stallG.fillRect(16, -32, STALL_W - 32, 32);
        this.stallText.setPosition(stall.centerX, stall.y + STALL_H / 2);
      }

      // Upgrade pad: fixed world position (_computePadLayout()), no longer
            // recomputed from viewport size or safe-area insets on every resize.
            if (this.padG && this.padText) {
              const pad = this._computePadLayout();
              this.padG.setPosition(pad.x, pad.y);
              this.padG.clear();
              this.padG.fillStyle(0xffb300, 1);
              this.padG.fillRoundedRect(0, 0, PAD_W, PAD_H, 8);
              this.padText.setPosition(pad.centerX, pad.y + PAD_H / 2);
            }

      // Start hint: positioned in _showStartHint(), just ensure it's visible if needed
      // No persistent center banner anymore
    }

  _showRotateOverlay() {
    if (rotateOverlay) return;
    // Create DOM overlay (simpler than Phaser text for full-screen)
    rotateOverlay = document.createElement('div');
    rotateOverlay.id = 'rotate-overlay';
    rotateOverlay.style.cssText = `
      position: fixed; top: 0; left: 0; width: 100vw; height: 100vh;
      background: #1a1a2e; color: #fff; z-index: 9999;
      display: flex; align-items: center; justify-content: center;
      font-family: monospace; font-size: 24px; text-align: center;
      padding: 20px; box-sizing: border-box;
    `;
    rotateOverlay.innerHTML = 'ROTATE TO PORTRAIT';
    document.body.appendChild(rotateOverlay);
  }

  _hideRotateOverlay() {
    if (rotateOverlay) {
      rotateOverlay.remove();
      rotateOverlay = null;
    }
  }

  _begin() {
    // Landscape lockout is enforced at the interaction layer (pointerdown/
    // keydown listeners are gated on !isLandscape, and the full-screen
    // rotate overlay blocks clicks getting through anyway) -- not here, so
    // that a direct/programmatic call to _begin() (tests, the generic
    // execution harness) isn't silently a no-op just because the current
    // viewport's aspect ratio happens to read as landscape.
    if (this.state === STATE.START) {
      this.state = STATE.PLAYING;
      this.game.state = STATE.PLAYING;
      this.startHint.setVisible(true);
      this.startHintText.setVisible(true);
      this._showStartHint();
    } else {
        }
      }

      _showStartHint() {
        // Position hint near farmer, above them with pulse animation
        if (!this.startHint || !this.startHintText) return;
        // Remember where the farmer was when the hint appeared, so update()
        // can tell when he's moved far enough to dismiss it (real-device
        // playtest bug: this hint used to be positioned once here and never
        // moved again, so it went stale/stranded as soon as the farmer
        // walked away -- see _repositionStartHint()).
        this._startHintOriginX = this.farmer.x;
        this._startHintOriginY = this.farmer.y;
        this._repositionStartHint();
    // Pulse animation
    if (this.startHintPulse) this.startHintPulse.stop();
    this.startHintPulse = this.tweens.add({
      targets: [this.startHint, this.startHintText],
      alpha: { from: 1, to: 0.4 },
      duration: 800,
      yoyo: true,
      repeat: -1
    });
  }

  _repositionStartHint() {
    // Recompute the hint's position from the farmer's CURRENT position and
    // redraw the pointer arrow. Called once from _showStartHint() and again
    // every frame from update() while the hint is visible, so it tracks the
    // farmer as he moves instead of staying pinned to his spawn point.
    // Split out from _showStartHint() specifically so the per-frame call
    // doesn't also restart the pulse tween every frame.
    const fx = this.farmer.x;
    const fy = this.farmer.y;
    // Ensure hint doesn't overlap the plot row. _plotPosition() places row 0
    // at PLOT_AREA_TOP + 96 (not PLOT_AREA_TOP itself -- that extra offset
    // is header/progress-bar space above the plots), so the row's actual
    // bottom edge is _plotPosition(0).y + PLOT_SIZE. startHintText has
    // origin(0.5), so hintY is its vertical CENTER -- the floor must also
    // clear the text's own half-height above that center, not just add a
    // flat margin to the plot's bottom edge (an earlier version of this
    // fix used PLOT_AREA_TOP + PLOT_SIZE + 20, which landed inside the
    // plot row's own vertical span; a later version fixed the plot-row
    // offset but still only added a flat +20, leaving the text's top edge
    // a few px inside the plot row on short viewports).
    const plotRowBottom = this._plotPosition(0).y + PLOT_SIZE;
    const hintHalfHeight = this.startHintText.height / 2;
    const minHintY = plotRowBottom + hintHalfHeight + 20;
    // Same origin(0.5) reasoning as the vertical clamp above, but
    // horizontal: hintX is the text's center, so when the farmer is near
    // the left/right edge (e.g. the far-right plot column) the label can
    // extend past the screen edge unless clamped by its own half-width.
    const hintHalfWidth = this.startHintText.width / 2;
    const hintX = Math.min(Math.max(fx, hintHalfWidth + 8), W - hintHalfWidth - 8);
    const hintY = Math.max(fy - 120, minHintY);
    this.startHint.x = hintX;
    this.startHint.y = hintY;
    this.startHintText.x = hintX;
    this.startHintText.y = hintY;
    // Draw arrow pointing down to farmer. Two bugs fixed here, found while
    // hunting a real-device report of a stray triangle+circle hovering
    // over the upgrade pad (Instinct Wire issue #2): (1) fillTriangle's
    // coordinates are LOCAL to this Graphics object, but this object is
    // ALSO positioned via .x/.y above -- the original code passed hintX/
    // hintY as the local coordinates too, double-applying the offset and
    // rendering the triangle near world (2*hintX, hintY+hintY+30) instead
    // of just below the hint text. At boot (hintX=360, hintY=424) that
    // landed at world (~720, ~878) -- almost exactly the upgrade pad's
    // top-right corner, which is what was actually being seen, not a pad
    // feature at all. Fixed by using coordinates relative to the object's
    // own origin (0, not hintX). (2) there was no clear() before redrawing
    // -- harmless when this only ran once (the original bug, before this
    // fix), but this method now runs every frame while the hint is
    // visible, so every frame was stacking a new triangle on top of every
    // previous one, forever, with no clear() ever removing the old ones.
    this.startHint.clear();
    this.startHint.fillStyle(0x2e7d32, 0.9);
    this.startHint.fillTriangle(0, 30, -20, 10, 20, 10);
  }

  _hideStartHint() {
    if (this.startHintPulse) {
      this.startHintPulse.stop();
      this.startHintPulse = null;
    }
    if (this.startHint) this.startHint.setVisible(false);
    if (this.startHintText) this.startHintText.setVisible(false);
  }

  _openUpgradeSheet() {
    if (this.sheetVisible) return;
    if (this.state !== STATE.PLAYING) return;
    this.sheetVisible = true;

    // Build sheet in HUD container (screen-space, no camera zoom)
    const displayWidth = this.scale.displaySize.width;
    const displayHeight = this.scale.displaySize.height;
    const scaleY = displayHeight / H;
    const safeBottomLogical = safeInsets.bottom / scaleY;
    
    const sheetWidth = W - 32; // 16px margins
    const sheetMaxHeight = Math.min(displayHeight * 0.8, H - safeBottomLogical - 100);
    
    // Every object built below is registered individually via
    // _registerHudObject, not just added to the container tree -- Instinct
    // reviewer condition 3: camera.ignore() on a parent Container is not
    // guaranteed to recurse to (especially dynamically rebuilt) children,
    // so nothing in this rebuilt-on-every-open sheet relies on that.
    this.upgradeSheet = this.add.container(W / 2, H - safeBottomLogical);
    this.upgradeSheet.setDepth(1001);
    this.hudContainer.add(this.upgradeSheet);
    this._registerHudObject(this.upgradeSheet);

    // Backdrop (blocks world input)
    const backdrop = this.add.rectangle(0, -sheetMaxHeight / 2, W, sheetMaxHeight + safeBottomLogical, 0x000000, 0.5);
    backdrop.setInteractive();
    backdrop.on('pointerdown', () => this._closeUpgradeSheet());
    this.upgradeSheet.add(backdrop);
    this._registerHudObject(backdrop);

    // Sheet content container
    const content = this.add.container(0, -sheetMaxHeight);
    this.upgradeSheet.add(content);
    this._registerHudObject(content);

    // Sheet background
    const sheetBg = this.add.graphics();
    sheetBg.fillStyle(0x2d2d44, 0.98);
    sheetBg.fillRoundedRect(-sheetWidth / 2, 0, sheetWidth, sheetMaxHeight, 16);
    sheetBg.lineStyle(2, 0x4caf50, 1);
    sheetBg.strokeRoundedRect(-sheetWidth / 2, 0, sheetWidth, sheetMaxHeight, 16);
    content.add(sheetBg);
    this._registerHudObject(sheetBg);

    // Title
    const title = this.add.text(0, 32, 'UPGRADES', {
      fontFamily: 'monospace', fontSize: '28px', color: '#fff'
    }).setOrigin(0.5);
    content.add(title);
    this._registerHudObject(title);

    // Close button (top-right)
    const closeBtn = this.add.rectangle(sheetWidth / 2 - 40, 32, 56, 56, 0xff5252, 0.9);
    closeBtn.setStrokeStyle(2, 0xc62828, 1);
    closeBtn.setInteractive({ useHandCursor: true });
    closeBtn.on('pointerdown', () => this._closeUpgradeSheet());
    const closeText = this.add.text(sheetWidth / 2 - 40, 32, 'X', {
      fontFamily: 'monospace', fontSize: '24px', color: '#fff'
    }).setOrigin(0.5);
    content.add([closeBtn, closeText]);
    this._registerHudObject(closeBtn);
    this._registerHudObject(closeText);

    // Upgrade rows (rebuild in sheet)
    this.upgradeRows = [];
    const rowTypes = [
      { type: 'plot', name: 'More Plots', desc: '+1 Crop Plot', cost: PLOT_UPGRADE_BASE_COST },
      { type: 'boots', name: 'Speed Boots', desc: 'Faster Movement', cost: BOOTS_UPGRADE_COST_T1 },
      { type: 'helper', name: 'Helper', desc: 'Auto-Harvest', cost: HELPER_UPGRADE_COST_T1 },
      { type: 'chicken', name: 'Chicken Coop', desc: 'Produces Eggs', cost: CHICKEN_UPGRADE_COST_T1 }
    ];

    const startY = 80;
    // Responsive row spacing (Round 2c, 4-row sheet overflow fix -- see
    // Instinct Wire issue #2): at 140px/row (the original, tall-viewport
    // design), 4 rows can overflow the sheet's real, dynamic height
    // (sheetMaxHeight, computed above) on short viewports -- confirmed
    // empirically at 3 of 4 real test viewports before this fix. rowHeight
    // now shrinks to fit exactly rowTypes.length rows within the actual
    // available space, never growing past the original 140px design on
    // tall viewports (Math.min keeps tall-viewport behavior pixel-identical
    // to before this change). `scale` uniformly shrinks every row's
    // content (icon radius, button size, font sizes, internal Y-offsets)
    // by the same factor rowHeight itself shrank by, so the content block
    // -- which exactly fit its original 140px row by design -- is
    // guaranteed to keep fitting inside a smaller row, centered the same
    // way it always was, just scaled down.
    const bottomMargin = 24;
    const rowHeight = Math.min(140, (sheetMaxHeight - startY - bottomMargin) / rowTypes.length);
    const scale = rowHeight / 140;

    rowTypes.forEach((rowData, i) => {
      const y = startY + i * rowHeight;
      const row = this.add.container(0, y);
      content.add(row);
      this._registerHudObject(row);

      const icon = this.add.circle(-sheetWidth / 2 + 80, 0, 40 * scale,
        rowData.type === 'plot' ? 0x8bc34a : rowData.type === 'boots' ? 0xffb300 : rowData.type === 'helper' ? 0xff7043 : 0xfff3c4);
      icon.setStrokeStyle(3, 0x000, 0.5);
      row.add(icon);
      this._registerHudObject(icon);

      const nameText = this.add.text(-sheetWidth / 2 + 140, -25 * scale, rowData.name, {
        fontFamily: 'monospace', fontSize: Math.round(24 * scale) + 'px', color: '#fff'
      }).setOrigin(0, 0);
      row.add(nameText);
      this._registerHudObject(nameText);

      const descText = this.add.text(-sheetWidth / 2 + 140, 10 * scale, rowData.desc, {
        fontFamily: 'monospace', fontSize: Math.round(18 * scale) + 'px', color: '#c8e6c9'
      }).setOrigin(0, 0);
      row.add(descText);
      this._registerHudObject(descText);

      // Cost and owned from game state
      const owned = this._getOwnedCount(rowData.type);
      const costText = this.add.text(sheetWidth / 2 - 80, -25 * scale, 'Cost: ' + rowData.cost, {
        fontFamily: 'monospace', fontSize: Math.round(22 * scale) + 'px', color: '#fff'
      }).setOrigin(1, 0);
      row.add(costText);
      this._registerHudObject(costText);

      const ownedText = this.add.text(sheetWidth / 2 - 80, 10 * scale, 'Owned: ' + owned, {
        fontFamily: 'monospace', fontSize: Math.round(18 * scale) + 'px', color: '#c8e6c9'
      }).setOrigin(1, 0);
      row.add(ownedText);
      this._registerHudObject(ownedText);

      const btn = this.add.rectangle(0, 68 * scale, 280 * scale, 56 * scale, 0xffb300, 1).setStrokeStyle(3, 0xf57f17, 1);
      btn.setInteractive({ useHandCursor: true });
      btn.on('pointerdown', () => this._buyUpgrade(rowData.type));
      const btnText = this.add.text(0, 68 * scale, 'BUY', {
        fontFamily: 'monospace', fontSize: Math.round(24 * scale) + 'px', color: '#000'
      }).setOrigin(0.5);
      row.add([btn, btnText]);
      this._registerHudObject(btn);
      this._registerHudObject(btnText);

      this.upgradeRows.push({ type: rowData.type, costText, ownedText, btn, btnText, baseCost: rowData.cost });
    });

    this._refreshUpgradeUI();

    // Animate sheet sliding up
    this.tweens.add({
      targets: content,
      y: -sheetMaxHeight + 40,
      duration: 300,
      ease: 'Back.easeOut'
    });
  }

  _closeUpgradeSheet() {
    if (!this.sheetVisible || !this.upgradeSheet) return;
    this.sheetVisible = false;
    this.upgradeSheet.destroy();
    this.upgradeSheet = null;
  }

  _layoutUpgradeSheet() {
    // Rebuild sheet if open (handles resize/orientation)
    if (this.sheetVisible) {
      this._closeUpgradeSheet();
      this._openUpgradeSheet();
    }
  }

  _getOwnedCount(type) {
    if (type === 'plot') return this.plots.length - 5; // base 5 plots
    if (type === 'boots') return this.bootsTier; // already 0-indexed owned count
    if (type === 'helper') return this.helperTier; // already 0-indexed owned count
    if (type === 'chicken') return this.chickenTier; // already 0-indexed owned count
    return 0;
  }

  // Cheapest cost among any upgrade the player hasn't maxed out yet. Real-
  // device defect #4 fix: the top HUD progress bar used to show
  // plots.length / MAX_PLOTS in the same gold coin-colored styling sitting
  // directly beside the "Coins: N" counter, reading as coin/sale progress
  // when it was actually an unrelated plot-count ratio. It's repurposed
  // here to show real coins-toward-next-upgrade progress instead. The plot
  // upgrade cost grows but never truly maxes out (buffs kick in past the
  // grid cap), so this only returns null once boots AND helper are also
  // both fully tiered.
  _cheapestUpgradeCost() {
    const costs = [
      Math.floor(PLOT_UPGRADE_BASE_COST * Math.pow(PLOT_UPGRADE_COST_GROWTH / 100, this.plotUpgradeCount))
    ];
    if (this.bootsTier < 3) {
      costs.push([BOOTS_UPGRADE_COST_T1, BOOTS_UPGRADE_COST_T2, BOOTS_UPGRADE_COST_T3][this.bootsTier]);
    }
    if (this.helperTier < 2) {
      costs.push([HELPER_UPGRADE_COST_T1, HELPER_UPGRADE_COST_T2][this.helperTier]);
    }
    if (this.chickenTier < 2) {
      costs.push([CHICKEN_UPGRADE_COST_T1, CHICKEN_UPGRADE_COST_T2][this.chickenTier]);
    }
    return costs.length ? Math.min(...costs) : null;
  }

  _createPlot(index, x, y) {
    const plot = this.add.graphics();
    plot.fillStyle(0x5d4037, 1);
    plot.fillRoundedRect(x, y, PLOT_SIZE, PLOT_SIZE, 13);
    plot.setDepth(0);  // ground layer, below gameplay objects
    this._registerWorldObject(plot);

    const crop = this.add.circle(x + PLOT_SIZE / 2, y + PLOT_SIZE / 2, 29, 0x8bc34a);
    crop.setVisible(false);
    crop.setDepth(0);  // ground layer, below gameplay objects
    this._registerWorldObject(crop);

    // Progress bar for crop growth (on the plot itself)
    const progressBarBg = this.add.rectangle(x + PLOT_SIZE / 2, y - 16, PLOT_SIZE - 8, 8, 0x000000, 0.5);
    progressBarBg.setOrigin(0.5, 1);
    progressBarBg.setDepth(0);  // ground layer, below gameplay objects
    this._registerWorldObject(progressBarBg);
    const progressBarFill = this.add.rectangle(x + 4, y - 16, 0, 6, 0x8bc34a, 1);
    progressBarFill.setOrigin(0, 1);
    progressBarFill.setDepth(0);  // ground layer, below gameplay objects
    this._registerWorldObject(progressBarFill);
    progressBarFill.setVisible(false);

    const plotObj = {
      index,
      x,
      y,
      readyAt: this.time.now + CROP_GROW_MS * this.growSpeedMult,
      plotSprite: plot,
      cropSprite: crop,
      progressBarBg,
      progressBarFill,
      harvested: false,
      pulseTween: null,
      // Producer-abstraction fields (Round 2): generic code (readiness
      // loop, magnet, helper targeting, _collectProducer) reads these.
      // Plot-specific code (layout, upgrades, existing tests) keeps using
      // the original field names above, unchanged -- both sets of field
      // names live on the SAME object.
      id: index,
      producerTypeId: 'plot',
      collectibleTypeId: 'crop',
      worldSprite: plot,
      productSprite: crop,
      centerX: x + PLOT_SIZE / 2,
      centerY: y + PLOT_SIZE / 2,
    };
    Object.defineProperty(plotObj, 'cycleMs', {
      get: () => CROP_GROW_MS * this.growSpeedMult,
      configurable: true
    });
    this.plots.push(plotObj);
    this.producers.push(plotObj);
  }

  _plotPosition(index) {
    const col = index % PLOTS_PER_ROW;
    const row = Math.floor(index / PLOTS_PER_ROW);
    const rowStartX = (W - (PLOTS_PER_ROW * PLOT_SIZE + (PLOTS_PER_ROW - 1) * PLOT_GAP)) / 2;
    const x = rowStartX + col * (PLOT_SIZE + PLOT_GAP);
    const y = PLOT_AREA_TOP + 96 + row * (PLOT_SIZE + PLOT_GAP);  // 60 * 1.6 = 96
    return { x, y };
  }

  _collectProducer(producer, collector) {
    if (producer.harvested) return false;
    if (this.time.now < producer.readyAt) return false;

    const collectibleTypeId = producer.collectibleTypeId;
    const config = COLLECTIBLE_TYPES[collectibleTypeId];
    const isPlayer = collector === 'player';

    if (isPlayer) {
      const currentWeight = this.carryItems.reduce((sum, item) => sum + COLLECTIBLE_TYPES[item.typeId].weight, 0);
      if (currentWeight >= CARRY_STACK_MAX) return false;
    } else {
      const helperWeight = collector.inventory.reduce((sum, typeId) => sum + COLLECTIBLE_TYPES[typeId].weight, 0);
      if (helperWeight >= HELPER_MAX_CARRY) return false;
    }

    producer.harvested = true;
    producer.productSprite.setVisible(false);
    if (producer.pulseTween) {
      producer.pulseTween.stop();
      producer.pulseTween = null;
    }
    if (producer.progressBarFill) producer.progressBarFill.setVisible(false);
    if (producer.progressBarBg) producer.progressBarBg.setVisible(false);
    producer.readyAt = this.time.now + producer.cycleMs;

    if (isPlayer) {
      this._addCollectiblesToPlayer(collectibleTypeId, config.playerYield);
      this.tweens.add({
        targets: this.farmer, scale: { from: 1, to: 1.15 }, duration: 80,
        yoyo: true, ease: 'Sine.easeOut'
      });
      vibrate(15);
    } else {
      for (let i = 0; i < config.helperYield; i++) {
        collector.inventory.push(collectibleTypeId);
      }
    }
    return true;
  }

  _harvestPlot(index) {
    if (this.state !== STATE.PLAYING) return;
    const plot = this.plots[index];
    if (!plot) return;
    this._collectProducer(plot, 'player');
  }

  // Real-device defect #5 fix: a single harvest must visibly burst multiple
  // goods into the carry stack (genre expectation), not add exactly one
  // sprite. Bounded by the existing CARRY_STACK_MAX cap -- shared by both
  // the player's own harvest (_harvestPlot) and the helper's harvest path,
  // since both add to the same shared player carry stack via
  // _addToCarryStack().
  _addCarryItem(typeId) {
    const config = COLLECTIBLE_TYPES[typeId]
    const currentWeight = this.carryItems.reduce((sum, item) => sum + COLLECTIBLE_TYPES[item.typeId].weight, 0)
    if (currentWeight + config.weight > CARRY_STACK_MAX) return false

    const sprite = this.add.circle(0, 0, 16, config.carryColor)
    sprite.setStrokeStyle(2, config.carryStroke, 1)

    const stackIndex = this.carryItems.length
    const angle = (stackIndex * 0.3) - 0.3
    const radius = 18 + stackIndex * 3
    sprite.x = Math.sin(angle) * radius
    sprite.y = -Math.cos(angle) * radius - stackIndex * 4
    sprite.setScale(0.3)

    this.carryStack.add(sprite)
    // Registered individually (not just via the parent carryStack) --
    // Group/ignore() on a Container is not guaranteed to recurse to
    // children (Instinct reviewer condition 3).
    this._registerWorldObject(sprite)
    this.carryItems.push({ typeId, sprite })

    this.tweens.add({
      targets: sprite, scale: { from: 0.3, to: 1 }, duration: 200,
      ease: 'Back.easeOut', delay: stackIndex * 30,
    })

    if (this.carryItems.length === 1) this.carryStack.setVisible(true)
    if (this.carryCountText) {
      const totalWeight = this.carryItems.reduce((sum, item) => sum + COLLECTIBLE_TYPES[item.typeId].weight, 0)
      this.carryCountText.setText(totalWeight + '/' + CARRY_STACK_MAX)
    }

    this.carrying = 'crop'
    this.carryIndicator.visible = true
    this.carryIndicator.x = this.farmer.x
    this.carryIndicator.y = this.farmer.y - 56

    this._updateCarryStackPosition()
    return true
  }

  _addCollectiblesToPlayer(typeId, requestedCount) {
    let added = 0
    for (let i = 0; i < requestedCount; i++) {
      if (!this._addCarryItem(typeId)) break
      added++
    }
    return added
  }
  _helperSellAtStall(helper) {
    const sellAmount = helper.inventory.reduce((sum, typeId) => {
      const config = COLLECTIBLE_TYPES[typeId]
      return sum + config.sellValue + (config.receivesPlotSellBonus ? this.sellValueBonus : 0)
    }, 0)
    this.coins += sellAmount;
    this.coinsText.setText('Coins: ' + this.coins);
    this.game.registry.set('score', this.coins);

    // Fly coins from helper's position to counter
    this._flyCoinsToCounter(helper.inventory.length, helper.x, helper.y);

    // Sell feedback: particle burst + haptic at helper's position
    const stall = this._computeStallLayout();
    this._withNewChildrenRegistered(this._registerWorldObject, () =>
      Juice.ParticleBurst.create(this, stall.centerX, stall.y, {
        color: 0xffd700, count: 12, speed: 128, size: 8
      })
    );
    vibrate(20);

    // Reset helper inventory
    helper.inventory = [];
  }


  _clearCarryStack() {
    this.carryItems.forEach(item => item.sprite.destroy());
    this.carryItems = [];
    this.carryStack.setVisible(false);
    if (this.carryCountText) this.carryCountText.setText('');

    // Update backward compatibility
    this.carrying = null;
    this.carryIndicator.visible = false;
    this.carryIndicator.x = this.farmer.x;
    this.carryIndicator.y = this.farmer.y - 56;
  }

  _updateCarryStackPosition() {
    this.carryStack.x = this.farmer.x;
    this.carryStack.y = this.farmer.y - 56;
    
    // Update backward compatibility
    this.carryIndicator.x = this.farmer.x;
    this.carryIndicator.y = this.farmer.y - 56;
  }

  _flyCoinsToCounter(amount, sourceX, sourceY) {
    const coinCount = Math.min(amount, 8); // Max 8 coin particles
    const counterPos = this.coinsText.getTopLeft();
    const targetX = counterPos.x + this.coinsText.width / 2;
    const targetY = counterPos.y + this.coinsText.height / 2;

    // sourceX/sourceY are WORLD coordinates (caller passes helper.x/y or
    // farmer.x/y). The coin sprite itself is a HUD object rendered by
    // uiCamera, so its start position must be converted from world-camera
    // physical screen position to uiCamera logical space.
    //
    // A naive `sourceX - worldCam.scrollX` is NOT the world camera's true
    // physical screen position: Phaser cameras default to a CENTERED origin
    // (0.5, 0.5), and worldCam (unlike uiCamera) is never centerOn'd -- it
    // just follows the farmer -- so that origin offset is never cancelled
    // out. The true formula includes the origin term:
    //   physicalX = (worldX - scrollX) * zoom + originX * width * (1 - zoom)
    // (confirmed empirically against camera.getWorldPoint-sampled ground
    // truth; the naive formula was off by exactly originX*width*(1-zoom),
    // ~89px horizontally / ~193px vertically at 390x844 -- the same
    // magnitude Instinct's gate review originally flagged, meaning an
    // earlier version of this fix, which merely added uiCamera.scrollX
    // back in, patched the wrong term and still failed a real pixel test).
    // Once we have the source's true physical screen position, converting
    // it into uiCamera's logical space is exactly what getWorldPoint is
    // for (uiCamera IS correctly origin-compensated post-centerOn, so this
    // round-trips precisely).
    const worldCam = this.cameras.main;
    const physicalX = (sourceX - worldCam.scrollX) * worldCam.zoom +
      worldCam.originX * worldCam.width * (1 - worldCam.zoom);
    const physicalY = (sourceY - worldCam.scrollY) * worldCam.zoom +
      worldCam.originY * worldCam.height * (1 - worldCam.zoom);
    const uiPoint = this.uiCamera.getWorldPoint(physicalX, physicalY);
    const startX = uiPoint.x;
    const startY = uiPoint.y;

    for (let i = 0; i < coinCount; i++) {
      const coin = this.add.circle(startX, startY, 8, 0xffd700);
      coin.setStrokeStyle(2, 0xf57f17, 1);
      this._registerHudObject(coin);

      // Stage 1: scatter burst (relative to startX/startY, the HUD-space
      // coordinates the coin actually lives in -- not the original
      // world-space sourceX/sourceY).
      const angle = Math.random() * Math.PI * 2;
      const burstDist = 50 + Math.random() * 50;
      const burstX = startX + Math.cos(angle) * burstDist;
      const burstY = startY + Math.sin(angle) * burstDist;
      
      // Stage 2: ease-in to counter
      this.tweens.add({
        targets: coin,
        x: burstX,
        y: burstY,
        scale: { from: 0.5, to: 1.2 },
        duration: 150,
        ease: 'Cubic.easeOut',
        onComplete: () => {
          // Staggered arrival
          const delay = i * 40 + Math.random() * 40;
          this.time.delayedCall(delay, () => {
            this.tweens.add({
              targets: coin,
              x: targetX,
              y: targetY,
              scale: { from: 1.2, to: 0 },
              alpha: { from: 1, to: 0 },
              duration: 400,
              ease: 'Cubic.easeIn',
              onComplete: () => {
                coin.destroy();
                // Punch-scale the counter on first coin arrival
                if (i === 0) {
                  this.tweens.add({
                    targets: this.coinsText,
                    scale: { from: 1, to: 1.3 },
                    duration: 100,
                    yoyo: true,
                    ease: 'Sine.easeOut'
                  });
                }
              }
            });
          });
        }
      });
    }
  }

  _sellAtStall() {
    if (this.carryItems.length === 0) return;
    const sellAmount = this.carryItems.reduce((sum, item) => {
      const config = COLLECTIBLE_TYPES[item.typeId]
      return sum + config.sellValue + (config.receivesPlotSellBonus ? this.sellValueBonus : 0)
    }, 0)
    this.coins += sellAmount;
    this.coinsText.setText('Coins: ' + this.coins);
    this.game.registry.set('score', this.coins);
    
    // Fly coins from farmer to counter
    this._flyCoinsToCounter(this.carrySprites.length, this.farmer.x, this.farmer.y - 56);
    
    // Sell feedback: particle burst + haptic (same computed stall position
    // as everything else -- see _computeStallLayout())
    const stall = this._computeStallLayout();
    this._withNewChildrenRegistered(this._registerWorldObject, () =>
      Juice.ParticleBurst.create(this, stall.centerX, stall.y, {
        color: 0xffd700, count: 12, speed: 128, size: 8
      })
    );
    vibrate(20);

    // Clear carry stack
    this._clearCarryStack();

    // Coins just changed -- keep the upgrade sheet's BUY buttons (cost /
    // affordable-vs-not state) live if it's currently open, instead of only
    // refreshing on the next purchase.
    if (this.sheetVisible) this._refreshUpgradeUI();

    if (CTA_ENABLED && !this.ctaButton) {
      this._createCTAButton();
    }
  }

  _buyUpgrade(type) {
    if (this.state !== STATE.PLAYING) return;
    let cost, maxTier;
    if (type === 'plot') {
      cost = PLOT_UPGRADE_BASE_COST * Math.pow(PLOT_UPGRADE_COST_GROWTH / 100, this.plotUpgradeCount);
      cost = Math.floor(cost);
      if (this.coins < cost) return;
      this.coins -= cost;
      this.plotUpgradeCount++;
      if (this.plots.length < MAX_PLOTS) {
        const pos = this._plotPosition(this.plots.length);
        this._createPlot(this.plots.length, pos.x, pos.y);
      } else {
        this.plotGridCapped = true;
        this.sellValueBonus += PLOT_BUFF_SELL_VALUE_BONUS;
        this.growSpeedMult *= PLOT_BUFF_GROW_SPEED_MULT;
        if (this.growSpeedMult * CROP_GROW_MS < PLOT_BUFF_MIN_GROW_MS) {
          this.growSpeedMult = PLOT_BUFF_MIN_GROW_MS / CROP_GROW_MS;
        }
      }
    } else if (type === 'boots') {
      if (this.bootsTier >= 3) return;
      cost = [BOOTS_UPGRADE_COST_T1, BOOTS_UPGRADE_COST_T2, BOOTS_UPGRADE_COST_T3][this.bootsTier];
      if (this.coins < cost) return;
      this.coins -= cost;
      this.bootsTier++;
    } else if (type === 'helper') {
      if (this.helperTier >= 2) return;
      cost = [HELPER_UPGRADE_COST_T1, HELPER_UPGRADE_COST_T2][this.helperTier];
      if (this.coins < cost) return;
      this.coins -= cost;
      this.helperTier++;
      const interval = [HELPER_INTERVAL_T1, HELPER_INTERVAL_T2][this.helperTier - 1];
      this._spawnHelper(interval);
    } else if (type === 'chicken') {
      if (this.chickenTier >= 2) return;
      cost = [CHICKEN_UPGRADE_COST_T1, CHICKEN_UPGRADE_COST_T2][this.chickenTier];
      if (this.coins < cost) return;
      this.coins -= cost;
      this.chickenTier++;
      if (this.chickenTier === 1) {
        this._createCoop();
      } else {
        // Tier 2: a ready egg is never destroyed -- only restart the cycle
        // (at the new, faster speed, via coop.cycleMs's live getter) if the
        // coop is NOT currently ready. If it's already ready, leave it
        // exactly as-is; the player still gets to collect it.
        if (this.time.now < this.coop.readyAt) {
          this.coop.readyAt = this.time.now + this.coop.cycleMs;
        }
      }
    }
    this.coinsText.setText('Coins: ' + this.coins);
    this.game.registry.set('score', this.coins);
    this._refreshUpgradeUI();
    
    // Upgrade feedback: camera shake + celebration burst + haptic. Burst is
    // positioned at screen-center (W/2, H*0.5), not any specific world
    // entity -- HUD-space, rendered via the UI camera so it always appears
    // centered on whatever the player is currently looking at, not at a
    // fixed world coordinate that could scroll off-screen.
    this.cameras.main.shake(200, 0.015);
    this._withNewChildrenRegistered(this._registerHudObject, () =>
      Juice.ParticleBurst.create(this, W / 2, H * 0.5, {
        color: 0xffd700, count: 24, speed: 160, size: 10, spread: Math.PI * 1.5
      })
    );
    vibrate(30);
  }

  _refreshUpgradeUI() {
    // Refresh both in-world pad and bottom sheet (if open)
    if (this.upgradeRows) {
      this.upgradeRows.forEach(row => {
        let cost, owned;
        if (row.type === 'plot') {
          cost = PLOT_UPGRADE_BASE_COST * Math.pow(PLOT_UPGRADE_COST_GROWTH / 100, this.plotUpgradeCount);
          cost = Math.floor(cost);
          owned = this.plotUpgradeCount;
        } else if (row.type === 'boots') {
          if (this.bootsTier >= 3) { cost = 'MAX'; owned = 3; }
          else { cost = [BOOTS_UPGRADE_COST_T1, BOOTS_UPGRADE_COST_T2, BOOTS_UPGRADE_COST_T3][this.bootsTier]; owned = this.bootsTier; }
        } else if (row.type === 'helper') {
          if (this.helperTier >= 2) { cost = 'MAX'; owned = 2; }
          else { cost = [HELPER_UPGRADE_COST_T1, HELPER_UPGRADE_COST_T2][this.helperTier]; owned = this.helperTier; }
        } else if (row.type === 'chicken') {
          if (this.chickenTier >= 2) { cost = 'MAX'; owned = 2; }
          else { cost = [CHICKEN_UPGRADE_COST_T1, CHICKEN_UPGRADE_COST_T2][this.chickenTier]; owned = this.chickenTier; }
        }
        if (row.costText) row.costText.setText('Cost: ' + cost);
        if (row.ownedText) row.ownedText.setText('Owned: ' + owned);

        // BUY button affordable/disabled visual state: previously the BUY
        // button always looked identical regardless of whether the player
        // could afford it, so tapping it while too poor looked dead /
        // unresponsive (flagged alongside the 5 real-device defects).
        const maxed = cost === 'MAX';
        const affordable = !maxed && this.coins >= cost;
        this._setBuyButtonState(row, affordable, maxed);
      });
    }
  }

  _setBuyButtonState(row, affordable, maxed) {
    if (!row.btn) return;
    if (maxed) {
      row.btn.setFillStyle(0x757575, 0.6);
      row.btn.setStrokeStyle(3, 0x424242, 1);
      if (row.btnText) row.btnText.setColor('#bbbbbb');
    } else if (affordable) {
      row.btn.setFillStyle(0xffb300, 1);
      row.btn.setStrokeStyle(3, 0xf57f17, 1);
      if (row.btnText) row.btnText.setColor('#000000');
    } else {
      row.btn.setFillStyle(0x8d8d8d, 0.45);
      row.btn.setStrokeStyle(3, 0x5c5c5c, 1);
      if (row.btnText) row.btnText.setColor('#4a4a4a');
    }
  }

  _spawnHelper(interval) {
      const helper = this.add.circle(W / 2, PLOT_AREA_TOP + 320, 24, 0xff7043);
      helper.setDepth(10);
      helper.setStrokeStyle(3, 0xc62828, 1);
      this._registerWorldObject(helper);
      const helperObj = {
      sprite: helper,
      x: W / 2,
      y: PLOT_AREA_TOP + 320,
      target: null,
      state: 'idle',
      interval,
      timer: 0,
      carrying: false,
      targetPlotIndex: -1,
      inventory: []
    };
    Object.defineProperty(helperObj, 'carryCount', {
      get() { return helperObj.inventory.length; },
      configurable: true
    });
    this.helpers.push(helperObj);
  }

  _updateAutoAssist(dt) {
    this.helpers.forEach(helper => {
      helper.timer += dt;
      if (helper.timer >= helper.interval && helper.state === 'idle') {
        helper.timer = 0;
        helper.state = 'seeking_plot';
      }
      this._updateHelper(helper, dt);
    });

    // Joystick-driven movement: farmer moves in joystick direction. This is
    // the ONLY thing that moves the farmer directly (real-device defect #2
    // fix). A prior "auto-assist" branch used to walk the farmer toward the
    // nearest ready plot even with the joystick idle/untouched -- verified
    // on a real device moving 148-183px over 1.8s with zero input. Movement
    // automation is the separately-purchased Helper entity (_updateHelper /
    // _spawnHelper above), not something the base farmer does by default.
    if (this.joystickActive) {
      this._moveFarmerByJoystick(dt);
    }

    // Magnet: auto-collect crops/coins within MAGNET_RADIUS of farmer. This
    // is the deliberate Part 2a auto-collect feature (crops/coins the
    // farmer is already standing next to fly to them) and is intentionally
    // left untouched -- it does not move the farmer, it only acts on things
    // already within reach.
    this._updateMagnet();
  }

  _moveFarmerByJoystick(dt) {
      const currentSpeed = MOVE_SPEED * (this.bootsTier > 0 ? Math.pow(BOOTS_SPEED_MULT, this.bootsTier) : 1);

      // Apply joystick vector (already normalized to [-1, 1])
      const moveDist = currentSpeed * (dt / 1000);
      this.farmer.x += this.joystickVector.x * moveDist;
      this.farmer.y += this.joystickVector.y * moveDist;

      // Clamp farmer to playable area (above bottom sheet, within screen bounds)
      const farmerMinY = PLOT_AREA_TOP + FARMER_RADIUS;
      const farmerMaxY = WORLD_H - FARMER_RADIUS;
      const farmerMinX = FARMER_RADIUS;
      const farmerMaxX = WORLD_W - FARMER_RADIUS;
    
    this.farmer.x = Phaser.Math.Clamp(this.farmer.x, farmerMinX, farmerMaxX);
    this.farmer.y = Phaser.Math.Clamp(this.farmer.y, farmerMinY, farmerMaxY);
    
    this._updateCarryStackPosition();

  }

  _moveFarmerTowards(targetX, targetY, dt) {
    const currentSpeed = MOVE_SPEED * (this.bootsTier > 0 ? Math.pow(BOOTS_SPEED_MULT, this.bootsTier) : 1);
    const dx = targetX - this.farmer.x;
    const dy = targetY - this.farmer.y;
    const dist = Math.sqrt(dx * dx + dy * dy);
    if (dist < 3) {
      this.farmer.x = targetX;
      this.farmer.y = targetY;
      this._updateCarryStackPosition();
      return;
    }
    const moveDist = currentSpeed * (dt / 1000);
    this.farmer.x += (dx / dist) * moveDist;
    this.farmer.y += (dy / dist) * moveDist;
    this._updateCarryStackPosition();
  }

  _updateMagnet() {
    const fx = this.farmer.x;
    const fy = this.farmer.y;

    // Check producers: harvest ready crops within MAGNET_RADIUS
    this.producers.forEach(producer => {
      if (!producer.harvested && this.time.now >= producer.readyAt) {
        const dist = Phaser.Math.Distance.Between(fx, fy, producer.centerX, producer.centerY);
        if (dist < MAGNET_RADIUS) {
          this._collectProducer(producer, 'player');
        }
      }
    });
    // Check stall: sell carried crops if farmer is within MAGNET_RADIUS of
    // the stall's REAL rendered position (single source of truth --
    // _computeStallLayout() -- not the separate STALL_Y constant that used
    // to drift from what _layoutHUD() actually drew, real-device defect #3).
    if (this.carrySprites.length > 0) {
      const stall = this._computeStallLayout();
      const distToStall = Phaser.Math.Distance.Between(fx, fy, stall.centerX, stall.centerY);
      if (distToStall < MAGNET_RADIUS) {
        this._sellAtStall();
      }
    }

    // Check upgrade pad: auto-open upgrade panel (could be a future feature)
    // Not implementing auto-upgrade for now - keeping manual interaction for purchases
  }

  _updateHelper(helper, dt) {
    const speed = MOVE_SPEED * (this.bootsTier > 0 ? Math.pow(BOOTS_SPEED_MULT, this.bootsTier) : 1);

    if (helper.state === 'seeking_plot') {
      let targetProducer = null;
      let minDist = Infinity;
      this.producers.forEach(producer => {
        if (!producer.harvested && this.time.now >= producer.readyAt) {
          const dist = Phaser.Math.Distance.Between(helper.x, helper.y, producer.centerX, producer.centerY);
          if (dist < minDist) {
            minDist = dist;
            targetProducer = producer;
          }
        }
      });
      if (targetProducer) {
        helper.target = { x: targetProducer.centerX, y: targetProducer.centerY };
        helper.targetProducer = targetProducer;
        helper.state = 'moving_to_plot';
      } else {
        helper.state = 'idle';
      }
    }

    if (helper.state === 'moving_to_plot') {
      this._moveHelperTowards(helper, helper.target.x, helper.target.y, dt, speed);
      const dist = Phaser.Math.Distance.Between(helper.x, helper.y, helper.target.x, helper.target.y);
      if (dist < MAGNET_RADIUS) {
        const producer = helper.targetProducer;
        const collected = producer ? this._collectProducer(producer, helper) : false;
        if (collected) {
          if (helper.carryCount >= HELPER_MAX_CARRY) {
            helper.state = 'moving_to_stall';
            const stall = this._computeStallLayout();
            helper.target = { x: stall.centerX, y: stall.centerY };
          } else {
            helper.state = 'seeking_plot';
          }
        } else if (helper.carryCount >= HELPER_MAX_CARRY) {
          // Carry stack is full -- go deposit at the market instead of
          // idling right next to a producer it can't collect from.
          helper.state = 'moving_to_stall';
          const stall = this._computeStallLayout();
          helper.target = { x: stall.centerX, y: stall.centerY };
        } else {
          helper.state = 'idle';
        }
      }
    }

    if (helper.state === 'moving_to_stall') {
      this._moveHelperTowards(helper, helper.target.x, helper.target.y, dt, speed);
      const dist = Phaser.Math.Distance.Between(helper.x, helper.y, helper.target.x, helper.target.y);
      if (dist < MAGNET_RADIUS) {
        // Sell from the helper's own carry count -- not the player's carrySprites.
        if (helper.carryCount > 0) {
          this._helperSellAtStall(helper);
        }
        helper.inventory = [];
        helper.state = 'idle';
      } else {
        console.log(`Helper moving to stall: dist=${dist.toFixed(1)}, target=(${helper.target.x}, ${helper.target.y}), pos=(${helper.x.toFixed(1)}, ${helper.y.toFixed(1)})`);
      }
    }
  }

  _moveHelperTowards(helper, targetX, targetY, dt, speed) {
    const dx = targetX - helper.x;
    const dy = targetY - helper.y;
    const dist = Math.sqrt(dx * dx + dy * dy);
    if (dist < 3) {
      helper.x = targetX;
      helper.y = targetY;
      return;
    }
    const moveDist = speed * (dt / 1000);
    helper.x += (dx / dist) * moveDist;
    helper.y += (dy / dist) * moveDist;
    helper.sprite.x = helper.x;
    helper.sprite.y = helper.y;
  }

  _createCTAButton() {
    // HUD by intended behavior, not convenience: a persistent end-screen
    // overlay button meant to stay put regardless of any world scroll, not
    // a world entity.
    this.ctaButton = this.add.text(W / 2, H / 2 + 160, 'PLAY FULL VERSION', {
      fontFamily: 'monospace', fontSize: '29px', color: '#fff',
      backgroundColor: '#e65100', padding: { x: 32, y: 16 }
    }).setOrigin(0.5).setInteractive({ useHandCursor: true });
    this._registerHudObject(this.ctaButton);
    this.ctaButton.on('pointerdown', () => {
      if (typeof mraid !== 'undefined' && mraid.open) { mraid.open(CTA_LINK); }
      else { window.open(CTA_LINK, '_blank'); }
    });
    this.tweens.add({ targets: this.ctaButton, alpha: { from: 0, to: 1 }, duration: 300 });
  }

  _end(won) {
    if (CTA_ENABLED && !this.ctaButton) {
      this._createCTAButton();
    }
  }

  update(time, dt) {
    this.game.sessionTime = (this.game.sessionTime || 0) + dt;

    this.producers.forEach(producer => {
      if (!producer.harvested && this.time.now >= producer.readyAt) {
        producer.productSprite.setVisible(true);
        if (!producer.pulseTween) {
          producer.pulseTween = this.tweens.add({
            targets: producer.productSprite,
            scale: { from: 1, to: 1.15 },
            duration: 800,
            yoyo: true,
            repeat: -1,
            ease: 'Sine.easeInOut'
          });
        }
        if (producer.progressBarFill) {
          producer.progressBarFill.setVisible(true);
          producer.progressBarFill.width = producer.progressBarBg.width - 8;
          producer.progressBarBg.setVisible(true);
        }
      } else if (!producer.harvested) {
        const progress = (this.time.now - (producer.readyAt - producer.cycleMs)) / producer.cycleMs;
        const clampedProgress = Phaser.Math.Clamp(progress, 0, 1);
        if (producer.progressBarFill && producer.progressBarBg) {
          producer.progressBarFill.setVisible(true);
          producer.progressBarFill.width = (producer.progressBarBg.width - 8) * clampedProgress;
          producer.progressBarBg.setVisible(true);
        }
      }
      if (producer.harvested && this.time.now >= producer.readyAt) {
        producer.harvested = false;
      }
    });

    // Update top-center progress bar: coins toward the next affordable
    // upgrade (real-device defect #4 -- see _cheapestUpgradeCost()).
    if (this.progressBarFill && this.progressBarBg && this.progressText) {
      const nextCost = this._cheapestUpgradeCost();
      if (nextCost === null) {
        this.progressBarFill.width = 392;
        this.progressText.setText('All upgrades maxed!');
      } else {
        const progress = Math.min(this.coins / nextCost, 1);
        this.progressBarFill.width = 392 * progress;
        this.progressText.setText('Next upgrade: ' + this.coins + ' / ' + nextCost);
      }
    }

    if (this.state !== STATE.PLAYING) return;

    // Start hint: track the farmer's live position every frame while
    // visible (real-device playtest bug -- it used to be positioned once
    // and never moved again), and auto-dismiss once he's clearly moved
    // away from where it first appeared. _hideStartHint() existed before
    // this fix but was never actually called from anywhere.
    if (this.startHint && this.startHint.visible) {
      this._repositionStartHint();
      const movedDist = Phaser.Math.Distance.Between(
        this.farmer.x, this.farmer.y, this._startHintOriginX, this._startHintOriginY
      );
      if (movedDist > START_HINT_DISMISS_DIST) {
        this._hideStartHint();
      }
    }

    // Magnet already handles stall selling in _updateAutoAssist
    this._updateAutoAssist(dt);
  }
}

const config = {
  type: Phaser.AUTO,
  parent: 'game-root',
  scale: { 
    mode: Phaser.Scale.RESIZE, 
    autoCenter: Phaser.Scale.NO_CENTER,
    width: '100%',
    height: '100%'
  },
  backgroundColor: WORLD_BACKGROUND_COLOR,
  scene: [PlayScene],
  audio: { noAudio: true },
  resolution: 2,  // Cap effective DPR at 2x for performance
};

window.addEventListener('load', () => { new Phaser.Game(config); });
// Upgrade: Chicken Coop (fixed chain, 2 tiers) -- Round 2c
const CHICKEN_UPGRADE_COST_T1 = 150;
const CHICKEN_UPGRADE_COST_T2 = 350;
const CHICKEN_CYCLE_T1 = 5000;
const CHICKEN_CYCLE_T2 = 2500;

// Coop placement (Round 2c): fixed world position, single source of truth,
// same pattern as _computeStallLayout()/_computePadLayout(). x=720 sits
// just past the plot grid's permanent maximum x-extent (688, since
// PLOTS_PER_ROW=6 never changes and rows only grow downward as more plots
// are bought) -- clear of the 5 initial plots AND every possible future
// plot, by construction, not by coincidence. y=288 keeps it level with
// plot row 0.
const COOP_X = 720;
const COOP_FIXED_Y = 288;
const COOP_W = 96;
const COOP_H = 96;

// Round 2c (chicken/egg vertical slice): coop layout + creation, added via
// prototype assignment rather than in-class method syntax so this addition
// lands as a pure end-of-file append (see Instinct Wire issue #2, repo
// talyaak/gd-pipeline, for why). Behaves identically to an in-class method
// when called as this._computeCoopLayout() / this._createCoop() from
// elsewhere in PlayScene -- `this` binds the same way either way.
PlayScene.prototype._computeCoopLayout = function () {
  // Fixed world position, independent of viewport size or safe-area
  // insets -- the coop is a genuine world entity, not HUD-relative. Single
  // source of truth for every runtime consumer (rendering, magnet
  // collection, helper targeting), same pattern as _computeStallLayout()/
  // _computePadLayout().
  return {
    x: COOP_X,
    y: COOP_FIXED_Y,
    centerX: COOP_X + COOP_W / 2,
    centerY: COOP_FIXED_Y + COOP_H / 2
  };
};

PlayScene.prototype._createCoop = function () {
  const coop = this._computeCoopLayout();

  const body = this.add.graphics();
  body.fillStyle(0xffffff, 1);
  body.fillRoundedRect(coop.x, coop.y, COOP_W, COOP_H, 13);
  body.setDepth(0);
  this._registerWorldObject(body);

  const egg = this.add.circle(coop.centerX, coop.centerY, 29, COLLECTIBLE_TYPES.egg.worldColor);
  egg.setVisible(false);
  egg.setDepth(0);
  this._registerWorldObject(egg);

  const progressBarBg = this.add.rectangle(coop.centerX, coop.y - 16, COOP_W - 8, 8, 0x000000, 0.5);
  progressBarBg.setOrigin(0.5, 1);
  progressBarBg.setDepth(0);
  this._registerWorldObject(progressBarBg);
  progressBarBg.setVisible(false);

  const progressBarFill = this.add.rectangle(coop.x + 4, coop.y - 16, 0, 6, COLLECTIBLE_TYPES.egg.worldColor, 1);
  progressBarFill.setOrigin(0, 1);
  progressBarFill.setDepth(0);
  this._registerWorldObject(progressBarFill);
  progressBarFill.setVisible(false);

  const coopObj = {
    id: 'coop',
    x: coop.x,
    y: coop.y,
    readyAt: this.time.now + CHICKEN_CYCLE_T1,
    worldSprite: body,
    productSprite: egg,
    progressBarBg,
    progressBarFill,
    harvested: false,
    pulseTween: null,
    producerTypeId: 'coop',
    collectibleTypeId: 'egg',
    centerX: coop.centerX,
    centerY: coop.centerY,
  };
  Object.defineProperty(coopObj, 'cycleMs', {
    get: () => (this.chickenTier >= 2 ? CHICKEN_CYCLE_T2 : CHICKEN_CYCLE_T1),
    configurable: true
  });

  this.coop = coopObj;
  this.producers.push(coopObj);
};