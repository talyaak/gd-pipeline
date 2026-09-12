// Hand-built farm idle harness. Arcade idle genre (My Perfect Hotel / Pizza Ready family).
// Theme: farm life. Core loop: joystick move farmer -> harvest plot -> sell at stall -> buy upgrades.

const W = 720, H = 1280;  // Portrait design base (1.6x scale from 450x800)
const SCALE = 1.6;         // 720/450 = 1280/800 = 1.6
const CTA_LINK = "https://example.com/game";

const STATE = { START: 'start', PLAYING: 'playing' };

// Farmer
const MOVE_SPEED = 300;       // logical pixels/sec (was 150, ~2x for brisk feel)
const FARMER_RADIUS = 32;     // 20 * 1.6

// Joystick (floating, display-on-touch)
const JOYSTICK_RADIUS = 80;   // visual/logical radius of the joystick base

// Auto-collect magnet
const MAGNET_RADIUS = 60;     // coins/crops within this radius fly to farmer automatically

// Plots
const PLOT_COUNT = 5;
const PLOT_SIZE = 96;         // 60 * 1.6
const PLOT_GAP = 16;          // 10 * 1.6
const CROP_GROW_MS = 4000;
const CROP_SELL_VALUE = 10;

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

// CTA
const CTA_ENABLED = 0;

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
const STALL_Y = 1120;                 // 700 * 1.6
const STALL_W = 160;                  // 100 * 1.6
const STALL_H = 112;                  // 70 * 1.6
const PAD_X = 464;                    // (W - PAD_W) = 720 - 256 = 464, was 390 = 450 - 60
const PAD_Y = 1120;                   // 700 * 1.6
const PAD_W = 256;                    // 160 * 1.6
const PAD_H = 112;                    // 70 * 1.6
const COINS_Y = 64;                   // 40 * 1.6
const UPGRADE_PANEL_TOP = 672;        // 420 * 1.6
const UPGRADE_PANEL_H = 448;          // 280 * 1.6

// Safe-area insets (CSS pixels, updated on resize)
let safeInsets = { top: 0, right: 0, bottom: 0, left: 0 };
let isLandscape = false;
let rotateOverlay = null;

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

    // Market stall
    this.stallG = this.add.graphics();
    this.stallG.fillStyle(0x8d6e63, 1);
    this.stallG.fillRoundedRect(STALL_X, STALL_Y, STALL_W, STALL_H, 8);
    this.stallG.fillStyle(0x5d4037, 1);
    this.stallG.fillRect(STALL_X + 16, STALL_Y - 32, STALL_W - 32, 32);
    this.stallText = this.add.text(STALL_X + STALL_W / 2, STALL_Y + STALL_H / 2, 'MARKET', {
      fontFamily: 'monospace', fontSize: '22px', color: '#fff'
    }).setOrigin(0.5);

    // Upgrade pad
    this.padG = this.add.graphics();
    this.padG.fillStyle(0xffb300, 1);
    this.padG.fillRoundedRect(PAD_X, PAD_Y, PAD_W, PAD_H, 8);
    this.padText = this.add.text(PAD_X + PAD_W / 2, PAD_Y + PAD_H / 2, 'UPGRADES', {
      fontFamily: 'monospace', fontSize: '22px', color: '#000'
    }).setOrigin(0.5);

    // Farmer
    this.farmer = this.add.circle(W / 2, PLOT_AREA_TOP + 320, FARMER_RADIUS, 0xe65100);
    this.farmer.setStrokeStyle(5, 0xbf360c, 1);

    // Carried crop indicator
    this.carryIndicator = this.add.circle(W / 2, PLOT_AREA_TOP + 320 - 56, 19, 0x8bc34a, 0);
    this.carryIndicator.setStrokeStyle(5, 0x8bc34a, 1);
    this.carryIndicator.setVisible(false);

    // Coins display (HUD - will be repositioned on resize)
    this.coinsText = this.add.text(W / 2, COINS_Y, 'Coins: 0', {
      fontFamily: 'monospace', fontSize: '38px', color: '#000'
    }).setOrigin(0.5);

    // Upgrade panel (shop) - anchored at bottom
    this.upgradePanel = this.add.container(0, H - UPGRADE_PANEL_H);
    this.upgradeBg = this.add.rectangle(W / 2, UPGRADE_PANEL_H / 2, W - 64, UPGRADE_PANEL_H, 0x4caf50, 0.9);
    this.upgradeBg.setStrokeStyle(3, 0x2e7d32, 1);
    this.upgradePanel.add(this.upgradeBg);

    this.upgradeRows = [];
    this.upgradeRows.push(this._buildUpgradeRow('plot', 'More Plots', '+1 Crop Plot', PLOT_UPGRADE_BASE_COST, 0));
    this.upgradeRows.push(this._buildUpgradeRow('boots', 'Speed Boots', 'Faster Movement', BOOTS_UPGRADE_COST_T1, 1));
    this.upgradeRows.push(this._buildUpgradeRow('helper', 'Helper', 'Auto-Harvest', HELPER_UPGRADE_COST_T1, 2));

    // Start prompt
    this.startText = this.add.text(W / 2, H / 2, 'DRAG ANYWHERE TO MOVE FARMER', {
      fontFamily: 'monospace', fontSize: '32px', color: '#fff', align: 'center',
      backgroundColor: '#2e7d32', padding: { x: 32, y: 16 }
    }).setOrigin(0.5);
    this.tweens.add({ targets: this.startText, alpha: 0.4, duration: 800, yoyo: true, repeat: -1 });

    // Intro banner + tap hint (using Juice)
    const introBanner = Juice.IntroBanner.create(this, { label: 'HARVEST \u2022 SELL \u2022 UPGRADE', y: 96 });
    const introHint = Juice.TapHint.create(this, this.farmer.x, this.farmer.y, { color: 0xe65100, radius: 64 });
    this.time.delayedCall(2500, () => { introBanner.destroy(); introHint.destroy(); });

    // Input: Floating joystick (touch/click anywhere in play area)
    // Pointerdown starts the joystick at the pointer position
    this.input.on('pointerdown', (pointer) => {
      if (isLandscape) return;
      this._begin();
      this._activateJoystick(pointer.x, pointer.y);
    });

    // Pointermove updates the joystick vector
    this.input.on('pointermove', (pointer) => {
      if (!this.joystickActive || isLandscape) return;
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
    // Clamp joystick center to playable area (above upgrade panel)
    const maxY = H - UPGRADE_PANEL_H - safeInsets.bottom / (this.scale.displaySize.height / H) - JOYSTICK_RADIUS;
    const clampedY = Phaser.Math.Clamp(y, JOYSTICK_RADIUS, maxY);
    const clampedX = Phaser.Math.Clamp(x, JOYSTICK_RADIUS, W - JOYSTICK_RADIUS);

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

    // Calculate vector from center to current pointer position
    let dx = x - this.joystickCenter.x;
    let dy = y - this.joystickCenter.y;
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
      if (this.upgradePanel) this.upgradePanel.setVisible(false);
    } else if (!isLandscape && wasLandscape) {
      this._hideRotateOverlay();
      updateSafeInsets();
      this._layoutHUD();
      if (this.upgradePanel) this.upgradePanel.setVisible(true);
    }
  }

  _onResize(gameSize, baseSize, displaySize, resolution) {
    updateSafeInsets();
    this._layoutHUD();
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

    // Coin counter: top center, below safe-area top
    if (this.coinsText) {
      this.coinsText.setPosition(W / 2, Math.max(COINS_Y, safeTopLogical + 32));
    }

    // Upgrade panel: bottom, above safe-area bottom
    let panelTop = H - UPGRADE_PANEL_H; // default full-size position
    if (this.upgradePanel) {
      const panelBottom = H - safeBottomLogical;
      
      // Compute available height for panel (from minPanelTop to panelBottom)
      // Min panel top: leave room for plot area (up to row 3) + farmer + gap
      const minPanelTop = 600; // logical coords: below plot area (max ~528) + comfortable gap
      const availablePanelHeight = panelBottom - minPanelTop;
      
      // Use full panel height if it fits, otherwise compress
      const panelHeight = Math.min(UPGRADE_PANEL_H, Math.max(availablePanelHeight, 320)); // min 320 logical
      const compressionFactor = panelHeight / UPGRADE_PANEL_H; // 1.0 = full size, <1 = compressed
      
      panelTop = panelBottom - panelHeight;
      this.upgradePanel.setPosition(0, panelTop);
      // Update upgradeBg width to fill width minus safe insets
      this.upgradeBg.setPosition(W / 2, panelHeight / 2);
      this.upgradeBg.height = panelHeight;
      this.upgradeBg.width = W - safeLeftLogical - safeRightLogical;
    }

    // Reposition upgrade rows within panel (with compression)
    if (this.upgradeRows) {
      const panelBottom = H - safeBottomLogical;
      const minPanelTop = 600;
      const availablePanelHeight = panelBottom - minPanelTop;
      const panelHeight = Math.min(UPGRADE_PANEL_H, Math.max(availablePanelHeight, 320));
      const compressionFactor = panelHeight / UPGRADE_PANEL_H;
      
      // Base row spacing (85 * 1.6 = 136), compressed
      const baseRowSpacing = 136;
      const rowSpacing = baseRowSpacing * compressionFactor;
      // Base row start Y (40), compressed
      const rowStartY = 40 * compressionFactor;
      
      this.upgradeRows.forEach((row, i) => {
        const y = rowStartY + i * rowSpacing;
        row.icon.setPosition(96, y);
        row.nameText.setPosition(144, y - 29 * compressionFactor);
        row.descText.setPosition(144, y + 6 * compressionFactor);
        row.costText.setPosition(W - 96 - safeRightLogical, y - 29 * compressionFactor);
        row.ownedText.setPosition(W - 96 - safeRightLogical, y + 6 * compressionFactor);
        row.btn.setPosition(W / 2, y + 48 * compressionFactor);
        row.btnText.setPosition(W / 2, y + 48 * compressionFactor);
      });
    }

    // Stall: position above upgrade panel (with safe-area bottom buffer)
    if (this.stallG && this.stallText) {
      // Stall should be above the panel with a small gap
      const stallGap = 24;
      const stallY = Math.min(STALL_Y, panelTop - STALL_H - stallGap);
      this.stallG.setPosition(STALL_X, stallY);
      // Clear and redraw stall at new position
      this.stallG.clear();
      this.stallG.fillRoundedRect(0, 0, STALL_W, STALL_H, 8);
      this.stallG.fillRect(16, -32, STALL_W - 32, 32);
      // stallText is a top-level scene object, not a child of stallG, so it
      // needs absolute scene coordinates -- not coordinates relative to
      // stallG's own local origin (which is what STALL_W/2, STALL_H/2 would
      // be interpreted as, detaching the label from the stall visually).
      this.stallText.setPosition(STALL_X + STALL_W / 2, stallY + STALL_H / 2);
    }

    // Upgrade pad: same safe-area-bottom treatment as the stall above --
    // previously never repositioned at all, so it stayed at its original Y
    // and could overlap the safe area on short screens with a bottom inset.
    if (this.padG && this.padText) {
      const padGap = 24;
      const padY = Math.min(PAD_Y, panelTop - PAD_H - padGap);
      this.padG.setPosition(PAD_X, padY);
      this.padG.clear();
      this.padG.fillStyle(0xffb300, 1);
      this.padG.fillRoundedRect(0, 0, PAD_W, PAD_H, 8);
      this.padText.setPosition(PAD_X + PAD_W / 2, padY + PAD_H / 2);
    }
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

  _buildUpgradeRow(type, name, desc, baseCost, rowIndex) {
    const y = 40 + rowIndex * 136;  // 85 * 1.6
    const row = this.add.container(0, 0);

    const icon = this.add.circle(96, y, 32, type === 'plot' ? 0x8bc34a : type === 'boots' ? 0xffb300 : 0xff7043);
    icon.setStrokeStyle(3, 0x000, 0.5);

    const nameText = this.add.text(144, y - 29, name, { fontFamily: 'monospace', fontSize: '22px', color: '#fff' });
    const descText = this.add.text(144, y + 6, desc, { fontFamily: 'monospace', fontSize: '18px', color: '#c8e6c9' });

    const costText = this.add.text(W - 96, y - 29, 'Cost: ' + baseCost, { fontFamily: 'monospace', fontSize: '21px', color: '#fff' }).setOrigin(1, 0);
    const ownedText = this.add.text(W - 96, y + 6, 'Owned: 0', { fontFamily: 'monospace', fontSize: '18px', color: '#c8e6c9' }).setOrigin(1, 0);

    const btn = this.add.rectangle(W / 2, y + 48, 288, 48, 0xffb300, 1).setStrokeStyle(3, 0xf57f17, 1);
    const btnText = this.add.text(W / 2, y + 48, 'BUY', { fontFamily: 'monospace', fontSize: '22px', color: '#000' }).setOrigin(0.5);
    btn.setInteractive({ useHandCursor: true });
    btn.on('pointerdown', () => this._buyUpgrade(type));

    row.add([icon, nameText, descText, costText, ownedText, btn, btnText]);
    this.upgradePanel.add(row);

    return { type, icon, nameText, descText, costText, ownedText, btn, btnText, baseCost, rowIndex };
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
      this.startText.setVisible(false);
    }
  }

  _createPlot(index, x, y) {
    const plot = this.add.graphics();
    plot.fillStyle(0x5d4037, 1);
    plot.fillRoundedRect(x, y, PLOT_SIZE, PLOT_SIZE, 13);

    const crop = this.add.circle(x + PLOT_SIZE / 2, y + PLOT_SIZE / 2, 29, 0x8bc34a);
    crop.setVisible(false);

    this.plots.push({
      index,
      x,
      y,
      readyAt: this.time.now + CROP_GROW_MS * this.growSpeedMult,
      plotSprite: plot,
      cropSprite: crop,
      harvested: false,
      pulseTween: null
    });
  }

  _plotPosition(index) {
    const col = index % PLOTS_PER_ROW;
    const row = Math.floor(index / PLOTS_PER_ROW);
    const rowStartX = (W - (PLOTS_PER_ROW * PLOT_SIZE + (PLOTS_PER_ROW - 1) * PLOT_GAP)) / 2;
    const x = rowStartX + col * (PLOT_SIZE + PLOT_GAP);
    const y = PLOT_AREA_TOP + 96 + row * (PLOT_SIZE + PLOT_GAP);  // 60 * 1.6 = 96
    return { x, y };
  }

  _harvestPlot(index) {
    if (this.state !== STATE.PLAYING) return;
    if (this.carrying === 'crop') return;
    const plot = this.plots[index];
    if (!plot) return;
    if (plot.harvested) return;
    if (this.time.now < plot.readyAt) return;

    plot.harvested = true;
    plot.cropSprite.setVisible(false);
    if (plot.pulseTween) {
      plot.pulseTween.stop();
      plot.pulseTween = null;
    }
    // Schedule next growth cycle so update loop doesn't immediately reset harvested
    plot.readyAt = this.time.now + CROP_GROW_MS * this.growSpeedMult;
    this.carrying = 'crop';
    this.carryIndicator.setVisible(true);
    this.carryIndicator.x = this.farmer.x;
    this.carryIndicator.y = this.farmer.y - 56;
  }

  _sellAtStall() {
    if (this.carrying !== 'crop') return;
    this.coins += CROP_SELL_VALUE + this.sellValueBonus;
    this.coinsText.setText('Coins: ' + this.coins);
    this.game.registry.set('score', this.coins);
    this.carrying = null;
    this.carryIndicator.setVisible(false);
    Juice.ParticleBurst.create(this, STALL_X + STALL_W / 2, STALL_Y, {
      color: 0xffd700, count: 12, speed: 128, size: 8
    });
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
  }

  _refreshUpgradeUI() {
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
      row.costText.setText('Cost: ' + cost);
      row.ownedText.setText('Owned: ' + owned);
    });
  }

  _spawnHelper(interval) {
    const helper = this.add.circle(W / 2, PLOT_AREA_TOP + 320, 24, 0xff7043);
    helper.setStrokeStyle(3, 0xc62828, 1);
    this.helpers.push({
      sprite: helper,
      x: W / 2,
      y: PLOT_AREA_TOP + 320,
      target: null,
      state: 'idle',
      interval,
      timer: 0,
      carrying: false,
      targetPlotIndex: -1
    });
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

    // Joystick-driven movement: farmer moves in joystick direction
    if (this.joystickActive) {
      this._moveFarmerByJoystick(dt);
    }
    // Auto-assist (when not actively using joystick): walk to nearest ready plot
    else if (!this.joystickActive && this.farmerTarget) {
      this._moveFarmerTowards(this.farmerTarget.x, this.farmerTarget.y, dt);
      const distToPlot = Phaser.Math.Distance.Between(this.farmer.x, this.farmer.y, this.farmerTarget.x, this.farmerTarget.y);
      if (distToPlot < MAGNET_RADIUS) {
        const nearestPlot = this.plots.find(p => !p.harvested && this.time.now >= p.readyAt &&
          Phaser.Math.Distance.Between(this.farmer.x, this.farmer.y, p.x + PLOT_SIZE / 2, p.y + PLOT_SIZE / 2) < MAGNET_RADIUS);
        if (nearestPlot) {
          this._harvestPlot(nearestPlot.index);
          this.farmerTarget = null;
        }
      }
    } else if (!this.joystickActive) {
      let nearestPlot = null;
      let nearestDist = Infinity;
      this.plots.forEach(plot => {
        if (!plot.harvested && this.time.now >= plot.readyAt) {
          const dist = Phaser.Math.Distance.Between(this.farmer.x, this.farmer.y, plot.x + PLOT_SIZE / 2, plot.y + PLOT_SIZE / 2);
          if (dist < nearestDist) {
            nearestDist = dist;
            nearestPlot = plot;
          }
        }
      });
      if (nearestPlot) {
        this.farmerTarget = { x: nearestPlot.x + PLOT_SIZE / 2, y: nearestPlot.y + PLOT_SIZE / 2 };
        this._moveFarmerTowards(this.farmerTarget.x, this.farmerTarget.y, dt);
        const distToPlot = Phaser.Math.Distance.Between(this.farmer.x, this.farmer.y, this.farmerTarget.x, this.farmerTarget.y);
        if (distToPlot < MAGNET_RADIUS) {
          this._harvestPlot(nearestPlot.index);
          this.farmerTarget = null;
        }
      } else {
        this.farmerTarget = null;
      }
    }

    // Magnet: auto-collect crops/coins within MAGNET_RADIUS of farmer
    this._updateMagnet();
  }

  _moveFarmerByJoystick(dt) {
    const currentSpeed = MOVE_SPEED * (this.bootsTier > 0 ? Math.pow(BOOTS_SPEED_MULT, this.bootsTier) : 1);
    
    // Apply joystick vector (already normalized to [-1, 1])
    const moveDist = currentSpeed * (dt / 1000);
    this.farmer.x += this.joystickVector.x * moveDist;
    this.farmer.y += this.joystickVector.y * moveDist;
    
    // Clamp farmer to playable area (above upgrade panel, within screen bounds)
    const farmerMinY = PLOT_AREA_TOP + FARMER_RADIUS;
    const farmerMaxY = H - UPGRADE_PANEL_H - safeInsets.bottom / (this.scale.displaySize.height / H) - FARMER_RADIUS;
    const farmerMinX = FARMER_RADIUS;
    const farmerMaxX = W - FARMER_RADIUS;
    
    this.farmer.x = Phaser.Math.Clamp(this.farmer.x, farmerMinX, farmerMaxX);
    this.farmer.y = Phaser.Math.Clamp(this.farmer.y, farmerMinY, farmerMaxY);
    
    this.carryIndicator.x = this.farmer.x;
    this.carryIndicator.y = this.farmer.y - 56;
  }

  _moveFarmerTowards(targetX, targetY, dt) {
    const currentSpeed = MOVE_SPEED * (this.bootsTier > 0 ? Math.pow(BOOTS_SPEED_MULT, this.bootsTier) : 1);
    const dx = targetX - this.farmer.x;
    const dy = targetY - this.farmer.y;
    const dist = Math.sqrt(dx * dx + dy * dy);
    if (dist < 3) {
      this.farmer.x = targetX;
      this.farmer.y = targetY;
      this.carryIndicator.x = this.farmer.x;
      this.carryIndicator.y = this.farmer.y - 56;
      return;
    }
    const moveDist = currentSpeed * (dt / 1000);
    this.farmer.x += (dx / dist) * moveDist;
    this.farmer.y += (dy / dist) * moveDist;
    this.carryIndicator.x = this.farmer.x;
    this.carryIndicator.y = this.farmer.y - 56;
  }

  _updateMagnet() {
    const fx = this.farmer.x;
    const fy = this.farmer.y;

    // Check plots: harvest ready crops within MAGNET_RADIUS
    this.plots.forEach(plot => {
      if (!plot.harvested && this.time.now >= plot.readyAt) {
        const cropCenterX = plot.x + PLOT_SIZE / 2;
        const cropCenterY = plot.y + PLOT_SIZE / 2;
        const dist = Phaser.Math.Distance.Between(fx, fy, cropCenterX, cropCenterY);
        if (dist < MAGNET_RADIUS && this.carrying !== 'crop') {
          this._harvestPlot(plot.index);
        }
      }
    });

    // Check stall: sell carried crop if farmer is within MAGNET_RADIUS of stall
    if (this.carrying === 'crop') {
      const stallCenterX = STALL_X + STALL_W / 2;
      const stallCenterY = STALL_Y + STALL_H / 2;
      const distToStall = Phaser.Math.Distance.Between(fx, fy, stallCenterX, stallCenterY);
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
      let targetPlot = null;
      let minDist = Infinity;
      this.plots.forEach(plot => {
        if (!plot.harvested && this.time.now >= plot.readyAt) {
          const dist = Phaser.Math.Distance.Between(helper.x, helper.y, plot.x + PLOT_SIZE / 2, plot.y + PLOT_SIZE / 2);
          if (dist < minDist) {
            minDist = dist;
            targetPlot = plot;
          }
        }
      });
      if (targetPlot) {
        helper.target = { x: targetPlot.x + PLOT_SIZE / 2, y: targetPlot.y + PLOT_SIZE / 2 };
        helper.targetPlotIndex = targetPlot.index;
        helper.state = 'moving_to_plot';
      } else {
        helper.state = 'idle';
      }
    }

    if (helper.state === 'moving_to_plot') {
      this._moveHelperTowards(helper, helper.target.x, helper.target.y, dt, speed);
      const dist = Phaser.Math.Distance.Between(helper.x, helper.y, helper.target.x, helper.target.y);
      if (dist < MAGNET_RADIUS) {
        const plot = this.plots[helper.targetPlotIndex];
        if (plot && !plot.harvested && this.time.now >= plot.readyAt) {
          plot.harvested = true;
          plot.cropSprite.setVisible(false);
          if (plot.pulseTween) {
            plot.pulseTween.stop();
            plot.pulseTween = null;
          }
          plot.readyAt = this.time.now + CROP_GROW_MS * this.growSpeedMult;
          helper.carrying = true;
          helper.state = 'moving_to_stall';
          helper.target = { x: STALL_X + STALL_W / 2, y: STALL_Y + STALL_H / 2 };
        } else {
          helper.state = 'idle';
        }
      }
    }

    if (helper.state === 'moving_to_stall') {
      this._moveHelperTowards(helper, helper.target.x, helper.target.y, dt, speed);
      const dist = Phaser.Math.Distance.Between(helper.x, helper.y, helper.target.x, helper.target.y);
      if (dist < MAGNET_RADIUS) {
        this.coins += CROP_SELL_VALUE + this.sellValueBonus;
        this.coinsText.setText('Coins: ' + this.coins);
        this.game.registry.set('score', this.coins);
        helper.carrying = false;
        Juice.ParticleBurst.create(this, STALL_X + STALL_W / 2, STALL_Y, {
          color: 0xffd700, count: 8, speed: 80, size: 5
        });
        if (CTA_ENABLED && !this.ctaButton) {
          this._createCTAButton();
        }
        helper.state = 'idle';
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

    this.plots.forEach(plot => {
      if (!plot.harvested && this.time.now >= plot.readyAt) {
        plot.cropSprite.setVisible(true);
        if (!plot.pulseTween) {
          plot.pulseTween = this.tweens.add({
            targets: plot.cropSprite,
            scale: { from: 1, to: 1.15 },
            duration: 800,
            yoyo: true,
            repeat: -1,
            ease: 'Sine.easeInOut'
          });
        }
      }
      if (plot.harvested && this.time.now >= plot.readyAt) {
        plot.harvested = false;
      }
    });

    if (this.state !== STATE.PLAYING) return;

    // Magnet already handles stall selling in _updateAutoAssist
    this._updateAutoAssist(dt);
  }
}

const config = {
  type: Phaser.AUTO,
  parent: 'game-root',
  scale: { 
    mode: Phaser.Scale.FIT, 
    autoCenter: Phaser.Scale.CENTER_BOTH, 
    width: W, 
    height: H 
  },
  backgroundColor: '#8fbc8f',
  scene: [PlayScene],
  audio: { noAudio: true },
  resolution: 2,  // Cap effective DPR at 2x for performance
};

window.addEventListener('load', () => { new Phaser.Game(config); });