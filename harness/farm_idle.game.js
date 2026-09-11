// Hand-built farm idle harness. Arcade idle genre (My Perfect Hotel / Pizza Ready family).
// Theme: farm life. Core loop: drag farmer -> harvest plot -> sell at stall -> buy upgrades.

const W = 450, H = 800;
const CTA_LINK = "https://example.com/game";

const STATE = { START: 'start', PLAYING: 'playing' };  // ONLY these two

// Farmer
const MOVE_SPEED = 150;
const FARMER_RADIUS = 20;

// Plots
const PLOT_COUNT = 5;
const PLOT_SIZE = 60;
const PLOT_GAP = 10;
const CROP_GROW_MS = 4000;
const CROP_SELL_VALUE = 10;

// Upgrade: More Crop Plots (repeatable)
const PLOT_UPGRADE_BASE_COST = 50;
const PLOT_UPGRADE_COST_GROWTH = 150;  // hundredths: 150 = 1.50x growth

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

// Layout constants
const PLOT_AREA_TOP = 120;
const PLOTS_PER_ROW = Math.floor((W - PLOT_GAP) / (PLOT_SIZE + PLOT_GAP));
const MAX_PLOT_ROWS = 3;
const MAX_PLOTS = PLOTS_PER_ROW * MAX_PLOT_ROWS; // 18 with current W/PLOT_SIZE/PLOT_GAP
const PLOT_BUFF_SELL_VALUE_BONUS = 2;   // added to effective sell value per post-cap purchase
const PLOT_BUFF_GROW_SPEED_MULT = 0.92; // effective grow time multiplied by this, compounding, per post-cap purchase
const PLOT_BUFF_MIN_GROW_MS = 500;      // floor so regrow time can never degenerate toward zero
const STALL_X = 60;
const STALL_Y = 700;
const STALL_W = 100;
const STALL_H = 70;
const PAD_X = 390;
const PAD_Y = 700;
const PAD_W = 100;
const PAD_H = 70;
const COINS_Y = 40;
const UPGRADE_PANEL_TOP = 420;
const UPGRADE_PANEL_H = 280;

class PlayScene extends Phaser.Scene {
  constructor() {
    super('PlayScene');
  }

  create() {
    this.state = STATE.START;
    this.game.state = STATE.START;
    this.coins = 0;
    this.carrying = null;  // null | 'crop'
    this.farmerTarget = null;  // { x, y } for auto-walk
    this.isDragging = false;

    // Plots: array of { x, y, readyAt, sprite, cropSprite }
    this.plots = [];

    // Upgrade state
    this.plotUpgradeCount = 0;
    this.bootsTier = 0;  // 0-3
    this.helperTier = 0; // 0-2
    this.helperTimer = 0;
    this.helpers = [];  // array of { x, y, target, state, sprite, interval, timer }
    this.sellValueBonus = 0;
    this.growSpeedMult = 1;
    this.plotGridCapped = false;

    this.cameras.main.setBackgroundColor('#8fbc8f');  // light green farm background

    // --- Build static world ---
    // Grass background
    this.grassG = this.add.graphics();
    this.grassG.fillStyle(0x7cb342, 1);
    this.grassG.fillRect(0, PLOT_AREA_TOP, W, H - PLOT_AREA_TOP);

    // Initialize plots
    for (let i = 0; i < PLOT_COUNT; i++) {
      const pos = this._plotPosition(i);
      this._createPlot(i, pos.x, pos.y);
    }

    // Market stall
    this.stallG = this.add.graphics();
    this.stallG.fillStyle(0x8d6e63, 1);
    this.stallG.fillRoundedRect(STALL_X, STALL_Y, STALL_W, STALL_H, 8);
    this.stallG.fillStyle(0x5d4037, 1);
    this.stallG.fillRect(STALL_X + 10, STALL_Y - 20, STALL_W - 20, 20);
    this.stallText = this.add.text(STALL_X + STALL_W / 2, STALL_Y + STALL_H / 2, 'MARKET', {
      fontFamily: 'monospace', fontSize: '14px', color: '#fff'
    }).setOrigin(0.5);

    // Upgrade pad
    this.padG = this.add.graphics();
    this.padG.fillStyle(0xffb300, 1);
    this.padG.fillRoundedRect(PAD_X, PAD_Y, PAD_W, PAD_H, 8);
    this.padText = this.add.text(PAD_X + PAD_W / 2, PAD_Y + PAD_H / 2, 'UPGRADES', {
      fontFamily: 'monospace', fontSize: '14px', color: '#000'
    }).setOrigin(0.5);

    // Farmer
    this.farmer = this.add.circle(W / 2, PLOT_AREA_TOP + 200, FARMER_RADIUS, 0xe65100);
    this.farmer.setStrokeStyle(3, 0xbf360c, 1);

    // Carried crop indicator (above farmer)
    this.carryIndicator = this.add.circle(W / 2, PLOT_AREA_TOP + 200 - 35, 12, 0x8bc34a, 0);
    this.carryIndicator.setStrokeStyle(3, 0x8bc34a, 1);
    this.carryIndicator.setVisible(false);

    // Coins display
    this.coinsText = this.add.text(W / 2, COINS_Y, 'Coins: 0', {
      fontFamily: 'monospace', fontSize: '24px', color: '#000'
    }).setOrigin(0.5);

    // Upgrade panel (shop)
    this.upgradePanel = this.add.container(0, 0);
    this.upgradeBg = this.add.rectangle(W / 2, UPGRADE_PANEL_TOP + UPGRADE_PANEL_H / 2, W - 40, UPGRADE_PANEL_H, 0x4caf50, 0.9);
    this.upgradeBg.setStrokeStyle(2, 0x2e7d32, 1);
    this.upgradePanel.add(this.upgradeBg);

    this.upgradeRows = [];
    this.upgradeRows.push(this._buildUpgradeRow('plot', 'More Plots', '+1 Crop Plot', PLOT_UPGRADE_BASE_COST, 0));
    this.upgradeRows.push(this._buildUpgradeRow('boots', 'Speed Boots', 'Faster Movement', BOOTS_UPGRADE_COST_T1, 1));
    this.upgradeRows.push(this._buildUpgradeRow('helper', 'Helper', 'Auto-Harvest', HELPER_UPGRADE_COST_T1, 2));

    // Start prompt
    this.startText = this.add.text(W / 2, H / 2, 'DRAG FARMER TO START', {
      fontFamily: 'monospace', fontSize: '20px', color: '#fff', align: 'center',
      backgroundColor: '#2e7d32', padding: { x: 20, y: 10 }
    }).setOrigin(0.5);
    this.tweens.add({ targets: this.startText, alpha: 0.4, duration: 800, yoyo: true, repeat: -1 });

    // Intro banner + tap hint (using Juice)
    const introBanner = Juice.IntroBanner.create(this, { label: 'HARVEST • SELL • UPGRADE', y: 60 });
    const introHint = Juice.TapHint.create(this, this.farmer.x, this.farmer.y, { color: 0xe65100, radius: 40 });
    this.time.delayedCall(2500, () => { introBanner.destroy(); introHint.destroy(); });

    // Input: drag farmer
    this.farmer.setInteractive({ draggable: true });
    this.input.setDraggable(this.farmer);
    this.input.on('dragstart', (pointer, gameObject) => {
      if (gameObject === this.farmer) {
        this.isDragging = true;
        this.farmerTarget = null;  // cancel auto-walk
        this._begin();
      }
    });
    this.input.on('drag', (pointer, gameObject, dragX, dragY) => {
      if (gameObject === this.farmer) {
        gameObject.x = dragX;
        gameObject.y = dragY;
        // Update carry indicator position
        this.carryIndicator.x = dragX;
        this.carryIndicator.y = dragY - 35;
      }
    });
    this.input.on('dragend', (pointer, gameObject) => {
      if (gameObject === this.farmer) {
        this.isDragging = false;
      }
    });

    // Global pointerdown for START->PLAYING transition (matches idle_clicker pattern)
    this.input.on('pointerdown', () => this._begin());
    this.input.keyboard.on('keydown-SPACE', () => this._begin());

    window.__GAME__ = this.game;
    this.game.registry.set('score', 0);
  }

  _buildUpgradeRow(type, name, desc, baseCost, rowIndex) {
    const y = UPGRADE_PANEL_TOP + 40 + rowIndex * 85;
    const row = this.add.container(0, 0);

    const icon = this.add.circle(60, y, 20, type === 'plot' ? 0x8bc34a : type === 'boots' ? 0xffb300 : 0xff7043);
    icon.setStrokeStyle(2, 0x000, 0.5);

    const nameText = this.add.text(90, y - 18, name, { fontFamily: 'monospace', fontSize: '14px', color: '#fff' });
    const descText = this.add.text(90, y + 4, desc, { fontFamily: 'monospace', fontSize: '11px', color: '#c8e6c9' });

    const costText = this.add.text(W - 60, y - 18, 'Cost: ' + baseCost, { fontFamily: 'monospace', fontSize: '13px', color: '#fff' }).setOrigin(1, 0);
    const ownedText = this.add.text(W - 60, y + 4, 'Owned: 0', { fontFamily: 'monospace', fontSize: '11px', color: '#c8e6c9' }).setOrigin(1, 0);

    const btn = this.add.rectangle(W / 2, y + 30, 180, 30, 0xffb300, 1).setStrokeStyle(2, 0xf57f17, 1);
    const btnText = this.add.text(W / 2, y + 30, 'BUY', { fontFamily: 'monospace', fontSize: '14px', color: '#000' }).setOrigin(0.5);
    btn.setInteractive({ useHandCursor: true });
    btn.on('pointerdown', () => this._buyUpgrade(type));

    row.add([icon, nameText, descText, costText, ownedText, btn, btnText]);
    this.upgradePanel.add(row);

    return { type, icon, nameText, descText, costText, ownedText, btn, btnText, baseCost, rowIndex };
  }

  _begin() {
    if (this.state === STATE.START) {
      this.state = STATE.PLAYING;
      this.game.state = STATE.PLAYING;
      this.startText.setVisible(false);
    }
  }

  _createPlot(index, x, y) {
    const plot = this.add.graphics();
    plot.fillStyle(0x5d4037, 1);
    plot.fillRoundedRect(x, y, PLOT_SIZE, PLOT_SIZE, 8);

    // Crop sprite (initially invisible)
    const crop = this.add.circle(x + PLOT_SIZE / 2, y + PLOT_SIZE / 2, 18, 0x8bc34a);
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
    const y = PLOT_AREA_TOP + 60 + row * (PLOT_SIZE + PLOT_GAP);
    return { x, y };
  }

  _harvestPlot(index) {
    if (this.state !== STATE.PLAYING) return;
    if (this.carrying === 'crop') return;  // already carrying
    const plot = this.plots[index];
    if (!plot) return;
    if (plot.harvested) return;
    if (this.time.now < plot.readyAt) return;  // not ready yet

    // Harvest!
    plot.harvested = true;
    plot.cropSprite.setVisible(false);
    if (plot.pulseTween) {
      plot.pulseTween.stop();
      plot.pulseTween = null;
    }
    this.carrying = 'crop';
    this.carryIndicator.setVisible(true);
    this.carryIndicator.x = this.farmer.x;
    this.carryIndicator.y = this.farmer.y - 35;

    // Start regrow timer
    plot.readyAt = this.time.now + CROP_GROW_MS * this.growSpeedMult;

    // Visual feedback
    this.tweens.add({ targets: this.farmer, scale: 1.15, duration: 80, yoyo: true, ease: 'Sine.easeOut' });
    this.cameras.main.flash(50, 140, 195, 120, false);
  }

  _sellAtStall() {
    if (this.state !== STATE.PLAYING) return;
    if (this.carrying !== 'crop') return;

    this.coins += CROP_SELL_VALUE + this.sellValueBonus;
    this.coinsText.setText('Coins: ' + this.coins);
    this.game.registry.set('score', this.coins);
    this.carrying = null;
    this.carryIndicator.setVisible(false);

    // Juice burst at stall
    Juice.ParticleBurst.create(this, STALL_X + STALL_W / 2, STALL_Y, {
      color: 0xffd700, count: 12, speed: 120, size: 6
    });

    // CTA button appears on first sale if enabled
    if (CTA_ENABLED && !this.ctaButton) {
      this._createCTAButton();
    }
  }

  _buyUpgrade(type) {
    if (this.state !== STATE.PLAYING) return;
    let cost = 0;
    let canBuy = false;

    if (type === 'plot') {
      cost = Math.ceil(PLOT_UPGRADE_BASE_COST * Math.pow(PLOT_UPGRADE_COST_GROWTH / 100, this.plotUpgradeCount));
      canBuy = true;  // uncapped
    } else if (type === 'boots') {
      if (this.bootsTier >= 3) return;  // max tier reached
      cost = this.bootsTier === 0 ? BOOTS_UPGRADE_COST_T1 :
             this.bootsTier === 1 ? BOOTS_UPGRADE_COST_T2 :
             BOOTS_UPGRADE_COST_T3;
      canBuy = true;
    } else if (type === 'helper') {
      if (this.helperTier >= 2) return;  // max tier reached
      cost = this.helperTier === 0 ? HELPER_UPGRADE_COST_T1 : HELPER_UPGRADE_COST_T2;
      canBuy = true;
    } else {
      return;
    }

    if (!canBuy || this.coins < cost) {
      // Shake feedback
      const row = this.upgradeRows.find(r => r.type === type);
      if (row) {
        this.cameras.main.shake(80, 0.003);
        this.tweens.add({ targets: row.btn, x: row.btn.x - 4, duration: 40, yoyo: true, repeat: 2 });
      }
      return;
    }

    this.coins -= cost;
    this.coinsText.setText('Coins: ' + this.coins);
    this.game.registry.set('score', this.coins);

    if (type === 'plot') {
      this.plotUpgradeCount += 1;
      if (this.plots.length < MAX_PLOTS) {
        this._addNewPlot();
      } else {
        this.sellValueBonus += PLOT_BUFF_SELL_VALUE_BONUS;
        const targetGrowMs = CROP_GROW_MS * this.growSpeedMult * PLOT_BUFF_GROW_SPEED_MULT;
        this.growSpeedMult = Math.max(PLOT_BUFF_MIN_GROW_MS / CROP_GROW_MS, targetGrowMs / CROP_GROW_MS);
        // Update description once when cap is first reached
        if (!this.plotGridCapped) {
          this.plotGridCapped = true;
          const capRow = this.upgradeRows.find(r => r.type === 'plot');
          if (capRow) capRow.descText.setText('Faster & Richer Crops');
        }
      }
      const row = this.upgradeRows.find(r => r.type === 'plot');
      if (row) {
        const newCost = Math.ceil(PLOT_UPGRADE_BASE_COST * Math.pow(PLOT_UPGRADE_COST_GROWTH / 100, this.plotUpgradeCount));
        row.costText.setText('Cost: ' + newCost);
        row.ownedText.setText('Owned: ' + this.plotUpgradeCount);
        this.tweens.add({ targets: row.icon, scale: 1.4, duration: 100, yoyo: true, ease: 'Sine.easeOut' });
      }
    } else if (type === 'boots') {
      this.bootsTier += 1;
      const row = this.upgradeRows.find(r => r.type === 'boots');
      if (row) {
        row.ownedText.setText('Tier: ' + this.bootsTier + '/3');
        if (this.bootsTier === 3) {
          row.btn.setFillStyle(0x757575, 1);
          row.btnText.setText('MAX');
          row.btnText.setColor('#9e9e9e');
          row.btn.disableInteractive();
        } else {
          const nextCost = this.bootsTier === 1 ? BOOTS_UPGRADE_COST_T2 : BOOTS_UPGRADE_COST_T3;
          row.costText.setText('Cost: ' + nextCost);
        }
        this.tweens.add({ targets: row.icon, scale: 1.4, duration: 100, yoyo: true, ease: 'Sine.easeOut' });
      }
    } else if (type === 'helper') {
      this.helperTier += 1;
      this._spawnOrUpgradeHelper();
      const row = this.upgradeRows.find(r => r.type === 'helper');
      if (row) {
        row.ownedText.setText('Tier: ' + this.helperTier + '/2');
        if (this.helperTier === 2) {
          row.btn.setFillStyle(0x757575, 1);
          row.btnText.setText('MAX');
          row.btnText.setColor('#9e9e9e');
          row.btn.disableInteractive();
        } else {
          row.costText.setText('Cost: ' + HELPER_UPGRADE_COST_T2);
        }
        this.tweens.add({ targets: row.icon, scale: 1.4, duration: 100, yoyo: true, ease: 'Sine.easeOut' });
      }
    }

    Juice.ParticleBurst.create(this, this.farmer.x, this.farmer.y, {
      color: type === 'plot' ? 0x8bc34a : type === 'boots' ? 0xffb300 : 0xff7043,
      count: 10, speed: 100, size: 5
    });
  }

  _addNewPlot() {
    const pos = this._plotPosition(this.plots.length);
    this._createPlot(this.plots.length, pos.x, pos.y);
  }

  _spawnOrUpgradeHelper() {
    if (this.helperTier === 1) {
      // Spawn first helper (chicken)
      const helper = this.add.circle(this.farmer.x, this.farmer.y, 14, 0xffcc80);
      helper.setStrokeStyle(2, 0xff8f00, 1);
      this.helpers.push({
        x: this.farmer.x,
        y: this.farmer.y,
        target: null,
        state: 'idle',  // idle, moving, harvesting, selling
        sprite: helper,
        interval: HELPER_INTERVAL_T1,
        timer: 0,
        carrying: false
      });
    } else if (this.helperTier === 2) {
      // Spawn second helper (dog) - different color, faster
      const helper = this.add.circle(this.farmer.x + 30, this.farmer.y, 14, 0x8d6e63);
      helper.setStrokeStyle(2, 0x4e342e, 1);
      this.helpers.push({
        x: this.farmer.x + 30,
        y: this.farmer.y,
        target: null,
        state: 'idle',
        sprite: helper,
        interval: HELPER_INTERVAL_T2,
        timer: 0,
        carrying: false
      });
      // Also speed up existing helper
      this.helpers.forEach(h => { h.interval = HELPER_INTERVAL_T2; });
    }
  }

  _getCheapestAffordableUpgrade() {
    const upgrades = [];
    // Plot upgrade
    const plotCost = Math.ceil(PLOT_UPGRADE_BASE_COST * Math.pow(PLOT_UPGRADE_COST_GROWTH / 100, this.plotUpgradeCount));
    if (this.coins >= plotCost) upgrades.push({ type: 'plot', cost: plotCost });
    // Boots
    if (this.bootsTier < 3) {
      const bootsCost = this.bootsTier === 0 ? BOOTS_UPGRADE_COST_T1 :
                        this.bootsTier === 1 ? BOOTS_UPGRADE_COST_T2 :
                        BOOTS_UPGRADE_COST_T3;
      if (this.coins >= bootsCost) upgrades.push({ type: 'boots', cost: bootsCost });
    }
    // Helper
    if (this.helperTier < 2) {
      const helperCost = this.helperTier === 0 ? HELPER_UPGRADE_COST_T1 : HELPER_UPGRADE_COST_T2;
      if (this.coins >= helperCost) upgrades.push({ type: 'helper', cost: helperCost });
    }
    if (upgrades.length === 0) return null;
    upgrades.sort((a, b) => a.cost - b.cost);
    return upgrades[0].type;
  }

  _updateAutoAssist(dt) {
    if (this.state !== STATE.PLAYING) return;
    if (this.isDragging) return;  // player has control

    // Update helpers
    this.helpers.forEach(helper => {
      helper.timer += dt;
      if (helper.timer >= helper.interval) {
        helper.timer = 0;
        helper.state = 'seeking_plot';
      }

      if (helper.state !== 'idle') {
        this._updateHelper(helper, dt);
      }
    });

    // Farmer auto-assist priority:
    // 1. If carrying crop -> walk to stall
    if (this.carrying === 'crop') {
      this.farmerTarget = { x: STALL_X + STALL_W / 2, y: STALL_Y + STALL_H / 2 };
      this._moveFarmerTowards(this.farmerTarget.x, this.farmerTarget.y, dt);
      // Check arrival at stall
      const distToStall = Phaser.Math.Distance.Between(this.farmer.x, this.farmer.y, this.farmerTarget.x, this.farmerTarget.y);
      if (distToStall < 30) {
        this._sellAtStall();
        this.farmerTarget = null;
      }
      return;
    }

    // 2. If can afford upgrade and not at pad -> walk to pad
    const cheapestUpgrade = this._getCheapestAffordableUpgrade();
    if (cheapestUpgrade) {
      this.farmerTarget = { x: PAD_X + PAD_W / 2, y: PAD_Y + PAD_H / 2 };
      this._moveFarmerTowards(this.farmerTarget.x, this.farmerTarget.y, dt);
      const distToPad = Phaser.Math.Distance.Between(this.farmer.x, this.farmer.y, this.farmerTarget.x, this.farmerTarget.y);
      if (distToPad < 30) {
        this._buyUpgrade(cheapestUpgrade);
        this.farmerTarget = null;
      }
      return;
    }

    // 3. Walk to nearest ready plot
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
      if (distToPlot < 25) {
        this._harvestPlot(nearestPlot.index);
        this.farmerTarget = null;
      }
    } else {
      this.farmerTarget = null;
    }
  }

  _updateHelper(helper, dt) {
    const speed = MOVE_SPEED * (this.bootsTier > 0 ? Math.pow(BOOTS_SPEED_MULT, this.bootsTier) : 1);

    if (helper.state === 'seeking_plot') {
      // Find nearest ready plot
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
      if (dist < 25) {
        // Harvest
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
      if (dist < 30) {
        // Sell
        this.coins += CROP_SELL_VALUE + this.sellValueBonus;
        this.coinsText.setText('Coins: ' + this.coins);
        this.game.registry.set('score', this.coins);
        helper.carrying = false;
        Juice.ParticleBurst.create(this, STALL_X + STALL_W / 2, STALL_Y, {
          color: 0xffd700, count: 8, speed: 80, size: 5
        });
        // CTA on first sale
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
    if (dist < 2) {
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

  _moveFarmerTowards(targetX, targetY, dt) {
    const currentSpeed = MOVE_SPEED * (this.bootsTier > 0 ? Math.pow(BOOTS_SPEED_MULT, this.bootsTier) : 1);
    const dx = targetX - this.farmer.x;
    const dy = targetY - this.farmer.y;
    const dist = Math.sqrt(dx * dx + dy * dy);
    if (dist < 2) {
      this.farmer.x = targetX;
      this.farmer.y = targetY;
      this.carryIndicator.x = this.farmer.x;
      this.carryIndicator.y = this.farmer.y - 35;
      return;
    }
    const moveDist = currentSpeed * (dt / 1000);
    this.farmer.x += (dx / dist) * moveDist;
    this.farmer.y += (dy / dist) * moveDist;
    this.carryIndicator.x = this.farmer.x;
    this.carryIndicator.y = this.farmer.y - 35;
  }

  _createCTAButton() {
    this.ctaButton = this.add.text(W / 2, H / 2 + 100, 'PLAY FULL VERSION', {
      fontFamily: 'monospace', fontSize: '18px', color: '#fff',
      backgroundColor: '#e65100', padding: { x: 20, y: 10 }
    }).setOrigin(0.5).setInteractive({ useHandCursor: true });
    this.ctaButton.on('pointerdown', () => {
      if (typeof mraid !== 'undefined' && mraid.open) { mraid.open(CTA_LINK); }
      else { window.open(CTA_LINK, '_blank'); }
    });
    this.tweens.add({ targets: this.ctaButton, alpha: { from: 0, to: 1 }, duration: 300 });
  }

  // For CTA validation in execute.py - forces CTA to appear on "end" (but farm_idle has no end)
  _end(won) {
    if (CTA_ENABLED && !this.ctaButton) {
      this._createCTAButton();
    }
  }

  update(time, dt) {
    // Track session time on Game instance for validation
    this.game.sessionTime = (this.game.sessionTime || 0) + dt;

    // Update plot crop visibility (growing animation)
    this.plots.forEach(plot => {
      if (!plot.harvested && this.time.now >= plot.readyAt) {
        plot.cropSprite.setVisible(true);
        // Gentle pulse - only start once per ready transition
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
      // Regrow bug fix: clear stale harvested flag once regrow deadline passes
      if (plot.harvested && this.time.now >= plot.readyAt) {
        plot.harvested = false;
      }
    });

    if (this.state !== STATE.PLAYING) return;

    // Auto-assist logic
    this._updateAutoAssist(dt);
  }
}

const config = {
  type: Phaser.AUTO,
  parent: 'game-root',
  scale: { mode: Phaser.Scale.FIT, autoCenter: Phaser.Scale.CENTER_BOTH, width: W, height: H },
  backgroundColor: '#8fbc8f',
  scene: [PlayScene],
  audio: { noAudio: true },
};

window.addEventListener('load', () => { new Phaser.Game(config); });