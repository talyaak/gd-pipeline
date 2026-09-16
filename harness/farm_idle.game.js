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
// STALL_Y is ONLY a pre-first-layout placeholder for the initial
// this.add.text() call in create() (before _layoutHUD() has run once).
// Real-device defect #3: this constant used to also be read directly by
// _updateMagnet()/_sellAtStall()/helper-targeting as if it were the stall's
// actual rendered Y -- but _layoutHUD() computes the REAL stall Y
// dynamically per-viewport (H - totalHeight + stallGap) and never wrote it
// back here, so the two drifted apart on short viewports (the visible
// market ended up nowhere near where selling was actually detected). The
// single source of truth for the stall's live position is now
// PlayScene._computeStallLayout() -- every runtime consumer must call that,
// not this constant.
const STALL_Y = 1252;                 // 1412 - 112 - 48 = 1252 (preserves 48px bottom margin)
const STALL_W = 160;                  // 100 * 1.6
const STALL_H = 112;                  // 70 * 1.6
const PAD_X = 464;                    // (W - PAD_W) = 720 - 256 = 464, was 390 = 450 - 60
const PAD_Y = 1252;                   // 1412 - 112 - 48 = 1252 (same bottom margin as stall)
const PAD_W = 256;                    // 160 * 1.6
const PAD_H = 112;                    // 70 * 1.6
const COINS_Y = 64;                   // 40 * 1.6
const UPGRADE_PANEL_TOP = 672;        // 420 * 1.6
const UPGRADE_PANEL_H = 448;          // 280 * 1.6

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

    this.cameras.main.setBackgroundColor('#8fbc8f');

    // --- Build static world ---
    this.grassG = this.add.graphics();
    this.grassG.fillStyle(0x7cb342, 1);
    this.grassG.fillRect(0, PLOT_AREA_TOP, W, H - PLOT_AREA_TOP);

    for (let i = 0; i < PLOT_COUNT; i++) {
      const pos = this._plotPosition(i);
      this._createPlot(i, pos.x, pos.y);
    }

    // Farmer
        this.farmer = this.add.circle(W / 2, PLOT_AREA_TOP + 320, FARMER_RADIUS, 0xe65100);
        this.farmer.setStrokeStyle(5, 0xbf360c, 1);
        this.farmer.setDepth(10);  // gameplay foreground, above plots

    this.cameras.main.startFollow(this.farmer, true, 0.12, 0.12);
    this.cameras.main.roundPixels = true;

    // Carried crop indicator - now a stack container
        this.carryStack = this.add.container(this.farmer.x, this.farmer.y - 56);
        this.carryStack.setDepth(10);  // gameplay foreground, above plots
        this.carryStack.setVisible(false);
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

    // HUD scene/layer for screen-space elements (setScrollFactor(0))
    // This is the separate camera that stays fixed on screen while world camera moves
    this.hudContainer = this.add.container(0, 0);
    this.hudContainer.setDepth(1000);

    // Upgrade pad (in-world affordance) - tapping opens bottom sheet
    this.padG = this.add.graphics();
    this.padG.fillStyle(0xffb300, 1);
    this.padG.fillRoundedRect(0, 0, PAD_W, PAD_H, 8);
    this.padG.setInteractive(new Phaser.Geom.Rectangle(0, 0, PAD_W, PAD_H), Phaser.Geom.Rectangle.Contains);
    this.padG.on('pointerdown', () => this._openUpgradeSheet());
    this.padText = this.add.text(PAD_X + PAD_W / 2, PAD_Y + PAD_H / 2, 'UPGRADES', {
      fontFamily: 'monospace', fontSize: '20px', color: '#000', align: 'center'
    }).setOrigin(0.5);

    // Stall
    this.stallG = this.add.graphics();
    this.stallG.fillStyle(0x8b4513, 1);
    this.stallG.fillRoundedRect(0, 0, STALL_W, STALL_H, 8);
    this.stallG.fillRect(16, -32, STALL_W - 32, 32);
    this.stallText = this.add.text(STALL_X + STALL_W / 2, STALL_Y + STALL_H / 2, 'MARKET', {
      fontFamily: 'monospace', fontSize: '20px', color: '#fff', align: 'center'
    }).setOrigin(0.5);

    // Start hint (replaces persistent banner) - tap/arrow hint near farmer
    this.startHint = this.add.graphics();
    this.startHint.setVisible(false);
    this.startHintText = this.add.text(0, 0, 'TAP TO MOVE', {
      fontFamily: 'monospace', fontSize: '24px', color: '#fff',
      backgroundColor: '#2e7d32', padding: { x: 16, y: 8 }
    }).setOrigin(0.5).setVisible(false);
    this.startHintPulse = null;

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
    const introHint = Juice.TapHint.create(this, this.farmer.x, this.farmer.y, { color: 0xe65100, radius: 64 });
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

    // Also handle pointerout (mouse leaves canvas) - deactivate joystick
    this.input.on('pointerout', () => {
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

    // Create joystick thumb (visual)
    this.joystickThumb = this.add.circle(clampedX, clampedY, JOYSTICK_RADIUS * 0.5, 0x8bc34a, 0.8);
    this.joystickThumb.setStrokeStyle(2, 0x2e7d32, 1);
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
    // RESIZE mode: recalculate world zoom and visible world height
    viewportWidth = displaySize.width;
    viewportHeight = displaySize.height;
    worldZoom = viewportWidth / LOGICAL_W;
    visibleWorldHeight = viewportHeight / worldZoom;
    W = LOGICAL_W;
    H = visibleWorldHeight;

    // Apply uniform zoom to main camera so world scales correctly
    // (no stretched circles/hit targets — uniform scale preserved)
    const cam = this.cameras.main;
    cam.setViewport(0, 0, viewportWidth, viewportHeight);
    cam.setZoom(worldZoom);
    // World bounds are FIXED (WORLD_W x WORLD_H) and independent of viewport --
    // they must never be derived from viewportWidth/viewportHeight/W/H. Resize
    // changes the camera's viewport/zoom (above) and deadzone (below), never
    // the world bounds themselves.
    cam.setBounds(0, 0, WORLD_W, WORLD_H);

    // Deadzone: ~35% of logical viewport width, ~25% of current logical
    // height, recomputed every resize since it's viewport-relative (unlike
    // the fixed world bounds above).
    cam.setDeadzone(W * 0.35, H * 0.25);

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
    const stallGap = 24;
    const padHeight = PAD_H;
    const stallHeight = STALL_H;
    const totalHeight = padHeight + stallHeight + stallGap * 2 + this._safeBottomLogical();
    const stallY = H - totalHeight + stallGap;
    return {
      x: STALL_X,
      y: stallY,
      centerX: STALL_X + STALL_W / 2,
      centerY: stallY + STALL_H / 2
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

      // Upgrade pad: position with safe-area bottom buffer (at bottom, above safe area)
      if (this.padG && this.padText) {
        const padGap = 24;
        const padY = H - PAD_H - padGap - safeBottomLogical;
        this.padG.setPosition(PAD_X, padY);
        this.padG.clear();
        this.padG.fillStyle(0xffb300, 1);
        this.padG.fillRoundedRect(0, 0, PAD_W, PAD_H, 8);
        this.padText.setPosition(PAD_X + PAD_W / 2, padY + PAD_H / 2);
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
    // Draw arrow pointing down to farmer
    this.startHint.fillStyle(0x2e7d32, 0.9);
    this.startHint.fillTriangle(hintX, hintY + 30, hintX - 20, hintY + 10, hintX + 20, hintY + 10);
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
    
    this.upgradeSheet = this.add.container(W / 2, H - safeBottomLogical);
    this.upgradeSheet.setDepth(1001);
    this.hudContainer.add(this.upgradeSheet);

    // Backdrop (blocks world input)
    const backdrop = this.add.rectangle(0, -sheetMaxHeight / 2, W, sheetMaxHeight + safeBottomLogical, 0x000000, 0.5);
    backdrop.setInteractive();
    backdrop.on('pointerdown', () => this._closeUpgradeSheet());
    this.upgradeSheet.add(backdrop);

    // Sheet content container
    const content = this.add.container(0, -sheetMaxHeight);
    this.upgradeSheet.add(content);

    // Sheet background
    const sheetBg = this.add.graphics();
    sheetBg.fillStyle(0x2d2d44, 0.98);
    sheetBg.fillRoundedRect(-sheetWidth / 2, 0, sheetWidth, sheetMaxHeight, 16);
    sheetBg.lineStyle(2, 0x4caf50, 1);
    sheetBg.strokeRoundedRect(-sheetWidth / 2, 0, sheetWidth, sheetMaxHeight, 16);
    content.add(sheetBg);

    // Title
    const title = this.add.text(0, 32, 'UPGRADES', {
      fontFamily: 'monospace', fontSize: '28px', color: '#fff'
    }).setOrigin(0.5);
    content.add(title);

    // Close button (top-right)
    const closeBtn = this.add.rectangle(sheetWidth / 2 - 40, 32, 56, 56, 0xff5252, 0.9);
    closeBtn.setStrokeStyle(2, 0xc62828, 1);
    closeBtn.setInteractive({ useHandCursor: true });
    closeBtn.on('pointerdown', () => this._closeUpgradeSheet());
    const closeText = this.add.text(sheetWidth / 2 - 40, 32, 'X', {
      fontFamily: 'monospace', fontSize: '24px', color: '#fff'
    }).setOrigin(0.5);
    content.add([closeBtn, closeText]);

    // Upgrade rows (rebuild in sheet)
    this.upgradeRows = [];
    const rowTypes = [
      { type: 'plot', name: 'More Plots', desc: '+1 Crop Plot', cost: PLOT_UPGRADE_BASE_COST },
      { type: 'boots', name: 'Speed Boots', desc: 'Faster Movement', cost: BOOTS_UPGRADE_COST_T1 },
      { type: 'helper', name: 'Helper', desc: 'Auto-Harvest', cost: HELPER_UPGRADE_COST_T1 }
    ];
    
    const rowHeight = 140;
    const startY = 80;
    
    rowTypes.forEach((rowData, i) => {
      const y = startY + i * rowHeight;
      const row = this.add.container(0, y);
      content.add(row);

      const icon = this.add.circle(-sheetWidth / 2 + 80, 0, 40, 
        rowData.type === 'plot' ? 0x8bc34a : rowData.type === 'boots' ? 0xffb300 : 0xff7043);
      icon.setStrokeStyle(3, 0x000, 0.5);
      row.add(icon);

      const nameText = this.add.text(-sheetWidth / 2 + 140, -25, rowData.name, {
        fontFamily: 'monospace', fontSize: '24px', color: '#fff'
      }).setOrigin(0, 0);
      row.add(nameText);

      const descText = this.add.text(-sheetWidth / 2 + 140, 10, rowData.desc, {
        fontFamily: 'monospace', fontSize: '18px', color: '#c8e6c9'
      }).setOrigin(0, 0);
      row.add(descText);

      // Cost and owned from game state
      const owned = this._getOwnedCount(rowData.type);
      const costText = this.add.text(sheetWidth / 2 - 80, -25, 'Cost: ' + rowData.cost, {
        fontFamily: 'monospace', fontSize: '22px', color: '#fff'
      }).setOrigin(1, 0);
      row.add(costText);

      const ownedText = this.add.text(sheetWidth / 2 - 80, 10, 'Owned: ' + owned, {
        fontFamily: 'monospace', fontSize: '18px', color: '#c8e6c9'
      }).setOrigin(1, 0);
      row.add(ownedText);

      const btn = this.add.rectangle(0, 68, 280, 56, 0xffb300, 1).setStrokeStyle(3, 0xf57f17, 1);
      btn.setInteractive({ useHandCursor: true });
      btn.on('pointerdown', () => this._buyUpgrade(rowData.type));
      const btnText = this.add.text(0, 68, 'BUY', {
        fontFamily: 'monospace', fontSize: '24px', color: '#000'
      }).setOrigin(0.5);
      row.add([btn, btnText]);

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
    return costs.length ? Math.min(...costs) : null;
  }
  _createPlot(index, x, y) {
        const plot = this.add.graphics();
        plot.fillStyle(0x5d4037, 1);
        plot.fillRoundedRect(x, y, PLOT_SIZE, PLOT_SIZE, 13);
        plot.setDepth(0);  // ground layer, below gameplay objects

        const crop = this.add.circle(x + PLOT_SIZE / 2, y + PLOT_SIZE / 2, 29, 0x8bc34a);
        crop.setVisible(false);
        crop.setDepth(0);  // ground layer, below gameplay objects

        // Progress bar for crop growth (on the plot itself)
        const progressBarBg = this.add.rectangle(x + PLOT_SIZE / 2, y - 16, PLOT_SIZE - 8, 8, 0x000000, 0.5);
        progressBarBg.setOrigin(0.5, 1);
        progressBarBg.setDepth(0);  // ground layer, below gameplay objects
        const progressBarFill = this.add.rectangle(x + 4, y - 16, 0, 6, 0x8bc34a, 1);
        progressBarFill.setOrigin(0, 1);
        progressBarFill.setDepth(0);  // ground layer, below gameplay objects
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
    Juice.ParticleBurst.create(this, stall.centerX, stall.y, {
      color: 0xffd700, count: 12, speed: 128, size: 8
    });
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
    
    for (let i = 0; i < coinCount; i++) {
      const coin = this.add.circle(sourceX, sourceY, 8, 0xffd700);
      coin.setStrokeStyle(2, 0xf57f17, 1);
      
      // Stage 1: scatter burst
      const angle = Math.random() * Math.PI * 2;
      const burstDist = 50 + Math.random() * 50;
      const burstX = sourceX + Math.cos(angle) * burstDist;
      const burstY = sourceY + Math.sin(angle) * burstDist;
      
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
    Juice.ParticleBurst.create(this, stall.centerX, stall.y, {
      color: 0xffd700, count: 12, speed: 128, size: 8
    });
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
    }
    this.coinsText.setText('Coins: ' + this.coins);
    this.game.registry.set('score', this.coins);
    this._refreshUpgradeUI();
    
    // Upgrade feedback: camera shake + celebration burst + haptic
    this.cameras.main.shake(200, 0.015);
    Juice.ParticleBurst.create(this, W / 2, H * 0.5, {
      color: 0xffd700, count: 24, speed: 160, size: 10, spread: Math.PI * 1.5
    });
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
    const layout = this.computeLayout();
    const farmerMinY = PLOT_AREA_TOP + FARMER_RADIUS;
    const farmerMaxY = layout.visibleWorldHeight - FARMER_RADIUS;
    const farmerMinX = FARMER_RADIUS;
    const farmerMaxX = LOGICAL_W - FARMER_RADIUS;
    
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
    this.ctaButton = this.add.text(W / 2, H / 2 + 160, 'PLAY FULL VERSION', {
      fontFamily: 'monospace', fontSize: '29px', color: '#fff',
      backgroundColor: '#e65100', padding: { x: 32, y: 16 }
    }).setOrigin(0.5).setInteractive({ useHandCursor: true });
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
  backgroundColor: '#8fbc8f',
  scene: [PlayScene],
  audio: { noAudio: true },
  resolution: 2,  // Cap effective DPR at 2x for performance
};

window.addEventListener('load', () => { new Phaser.Game(config); });