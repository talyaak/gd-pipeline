// Hand-built idle/clicker harness. Same approach as harness/endless_runner.game.js
// and harness/match_3.game.js: hardcoded, tuned by actually playing it.
// Scoped down from genre_library/idle_clicker/gdd_v1.json's full-game MVP
// (prestige, offline progress, 20 achievements) to fit a single ~45s playable-ad
// session -- those systems only pay off across return visits a playable ad
// never gets. Keep this scoped to one session; don't add prestige/offline back
// in without a reason a playable ad session actually has.

const W = 450, H = 800;
const SESSION_MS = 45000;
const TARGET_ENERGY = 5000;
const TAP_VALUE = 2;

const GENERATORS = [
  { key: 'probe', name: 'Probe', baseCost: 10, rate: 1, color: 0x33e6ff },
  { key: 'satellite', name: 'Satellite', baseCost: 100, rate: 8, color: 0xff33cc },
  { key: 'station', name: 'Station', baseCost: 1100, rate: 60, color: 0xffe14d },
];
const COST_GROWTH = 1.15;

const STATE = { START: 'start', PLAYING: 'playing', END: 'end' };

// Bottom-drawer shop, per genre_library/idle_clicker/gdd_v1.json's own
// mobile note ("generator list on left (desktop) / bottom drawer (mobile)")
// -- landscape had the shop as a side column next to the tap orb, which
// doesn't fit a 450-wide portrait screen. Full-width rows stacked below
// the orb instead.
const TAP_ORB_Y = 230;
const SHOP_X0 = 30;
const SHOP_WIDTH = W - SHOP_X0 * 2;
const SHOP_PANEL_TOP = 460;
const SHOP_Y0 = 510;
const SHOP_ROW_H = 100;

function costFor(gen, owned) {
  return Math.ceil(gen.baseCost * Math.pow(COST_GROWTH, owned));
}

class PlayScene extends Phaser.Scene {
  constructor() {
    super('PlayScene');
  }

  create() {
    this.state = STATE.START;
    this.energy = 0;
    this.displayEnergy = 0;
    this.totalEarned = 0;
    this.taps = 0;
    this.owned = { probe: 0, satellite: 0, station: 0 };
    this.milestonesFired = new Set();
    this.dust = [];

    this.cameras.main.setBackgroundColor('#0a0a18');
    this.bgG = this.add.graphics();
    this.dustLayer = this.add.container(0, 0);
    for (let i = 0; i < 30; i++) {
      const d = this.add.circle(Math.random() * W, Math.random() * H, 1 + Math.random() * 1.5, 0x8899ff, 0.35);
      d.vx = (Math.random() - 0.5) * 6;
      d.vy = (Math.random() - 0.5) * 6;
      this.dustLayer.add(d);
      this.dust.push(d);
    }

    this.energyText = this.add.text(16, 12, 'Energy: 0', { fontFamily: 'monospace', fontSize: '22px', color: '#33e6ff' });
    this.targetText = this.add.text(16, 38, 'Target: ' + TARGET_ENERGY, { fontFamily: 'monospace', fontSize: '14px', color: '#ffe14d' });
    this.timerBarBg = this.add.rectangle(W / 2, 16, 300, 10, 0x14142a).setStrokeStyle(1, 0x33e6ff, 0.5);
    this.timerBarFg = this.add.rectangle(W / 2 - 150, 16, 300, 10, 0x33e6ff).setOrigin(0, 0.5);
    this.timerBarBg.setOrigin(0.5, 0.5);

    // Tap orb
    this.tapGlow = this.add.circle(W / 2, TAP_ORB_Y, 90, 0x33e6ff, 0.18);
    this.tapOrb = this.add.circle(W / 2, TAP_ORB_Y, 70, 0x33e6ff, 0.9);
    this.tapOrb.setStrokeStyle(3, 0xffffff, 0.85);
    this.tapLabel = this.add.text(W / 2, TAP_ORB_Y, 'TAP', { fontFamily: 'monospace', fontSize: '22px', color: '#0a0a18' }).setOrigin(0.5);
    this.rippleLayer = this.add.container(0, 0);
    this.tapOrb.setInteractive({ useHandCursor: true });
    this.tapOrb.on('pointerdown', () => this._onTap());

    this.toastLayer = this.add.container(0, 0);

    // Shop panel -- bottom drawer, full width
    const shopCenterY = (SHOP_PANEL_TOP + (SHOP_Y0 + (GENERATORS.length - 1) * SHOP_ROW_H + 50)) / 2;
    const shopHeight = (SHOP_Y0 + (GENERATORS.length - 1) * SHOP_ROW_H + 50) - SHOP_PANEL_TOP;
    this.shopBg = this.add.rectangle(W / 2, shopCenterY, W - 20, shopHeight, 0x14142a, 0.9).setStrokeStyle(2, 0x33e6ff, 0.35);
    this.shopRows = GENERATORS.map((gen, i) => this._buildShopRow(gen, i));

    this.startText = this.add.text(W / 2, TAP_ORB_Y + 130, 'TAP THE ORB TO BEGIN', {
      fontFamily: 'monospace', fontSize: '18px', color: '#ffffff', align: 'center',
    }).setOrigin(0.5);
    this.tweens.add({ targets: this.startText, alpha: 0.4, duration: 700, yoyo: true, repeat: -1 });

    // Quick visible intro: point at the tap orb for ~2s before the
    // (already-instant) tap-to-start becomes the obvious next move.
    const introBanner = Juice.IntroBanner.create(this, { label: 'TAP TO EARN • BUY GENERATORS', y: 70 });
    const introHint = Juice.TapHint.create(this, this.tapOrb.x, this.tapOrb.y, { color: 0x33e6ff, radius: 70 });
    this.time.delayedCall(2000, () => { introBanner.destroy(); introHint.destroy(); });

    window.__GAME__ = this.game;
    this.game.registry.set('score', 0);
  }

  _buildShopRow(gen, i) {
    const y = SHOP_Y0 + i * SHOP_ROW_H;
    const icon = this.add.circle(SHOP_X0 + 20, y - 14, 16, gen.color, 0.85).setStrokeStyle(2, 0xffffff, 0.7);
    const nameText = this.add.text(SHOP_X0 + 46, y - 28, gen.name, { fontFamily: 'monospace', fontSize: '14px', color: '#ffffff' });
    const rateText = this.add.text(SHOP_X0 + 46, y - 8, gen.rate + '/sec', { fontFamily: 'monospace', fontSize: '11px', color: '#8899ff' });
    const ownedText = this.add.text(SHOP_X0 + SHOP_WIDTH - 8, y - 28, 'x0', { fontFamily: 'monospace', fontSize: '13px', color: '#ffe14d' }).setOrigin(1, 0);
    const btn = this.add.rectangle(SHOP_X0, y + 16, SHOP_WIDTH, 26, 0x33e6ff, 0.85).setOrigin(0, 0.5).setStrokeStyle(1, 0xffffff, 0.6);
    const costText = this.add.text(SHOP_X0 + SHOP_WIDTH / 2, y + 16, 'Buy: ' + costFor(gen, 0), { fontFamily: 'monospace', fontSize: '12px', color: '#0a0a18' }).setOrigin(0.5);
    btn.setInteractive({ useHandCursor: true });
    btn.on('pointerdown', () => this._buy(gen.key));
    return { icon, nameText, rateText, ownedText, btn, costText };
  }

  _onTap() {
    if (this.state === STATE.START) { this._begin(); }
    if (this.state !== STATE.PLAYING) return;
    this.taps += 1;
    this._addEnergy(TAP_VALUE);
    this._ripple(this.tapOrb.x, this.tapOrb.y, 0x33e6ff);
    this.tweens.add({ targets: [this.tapOrb, this.tapGlow, this.tapLabel], scale: 0.9, duration: 60, yoyo: true, ease: 'Sine.easeOut' });
    this._checkMilestone('taps1', this.taps === 1, 'First Tap!');
    this._checkMilestone('taps25', this.taps === 25, '25 Taps!');
  }

  _begin() {
    this.state = STATE.PLAYING;
    this.startText.setVisible(false);
    this.sessionStart = this.time.now;
  }

  _addEnergy(amount) {
    this.energy += amount;
    this.totalEarned += amount;
  }

  _buy(key) {
    if (this.state !== STATE.PLAYING) return;
    const gen = GENERATORS.find((g) => g.key === key);
    const cost = costFor(gen, this.owned[key]);
    if (this.energy < cost) {
      const row = this.shopRows[GENERATORS.indexOf(gen)];
      this.cameras.main.shake(80, 0.003);
      this.tweens.add({ targets: row.btn, x: row.btn.x - 4, duration: 40, yoyo: true, repeat: 2 });
      return;
    }
    this.energy -= cost;
    this.owned[key] += 1;
    const row = this.shopRows[GENERATORS.indexOf(gen)];
    row.ownedText.setText('x' + this.owned[key]);
    row.costText.setText('Buy: ' + costFor(gen, this.owned[key]));
    this.tweens.add({ targets: row.icon, scale: 1.4, duration: 100, yoyo: true, ease: 'Sine.easeOut' });
    this._burstAt(row.icon.x, row.icon.y, gen.color);
    this._checkMilestone('first_' + key, this.owned[key] === 1, 'First ' + gen.name + '!');
  }

  _ripple(x, y, color) {
    const ring = this.add.circle(x, y, 10, color, 0).setStrokeStyle(3, color, 0.8);
    this.rippleLayer.add(ring);
    this.tweens.add({ targets: ring, radius: 60, alpha: 0, duration: 400, ease: 'Cubic.easeOut', onComplete: () => ring.destroy() });
  }

  _burstAt(x, y, color) {
    for (let i = 0; i < 10; i++) {
      const p = this.add.circle(x, y, 3, color);
      const angle = Math.random() * Math.PI * 2;
      const dist = 20 + Math.random() * 30;
      this.tweens.add({
        targets: p, x: x + Math.cos(angle) * dist, y: y + Math.sin(angle) * dist, alpha: 0,
        duration: 400 + Math.random() * 200, ease: 'Cubic.easeOut', onComplete: () => p.destroy(),
      });
    }
  }

  _checkMilestone(id, condition, label) {
    if (!condition || this.milestonesFired.has(id)) return;
    this.milestonesFired.add(id);
    const toast = this.add.container(W / 2, -30);
    const bg = this.add.rectangle(0, 0, 220, 34, 0x14142a, 0.95).setStrokeStyle(2, 0xffe14d, 0.8);
    const text = this.add.text(0, 0, label, { fontFamily: 'monospace', fontSize: '14px', color: '#ffe14d' }).setOrigin(0.5);
    toast.add([bg, text]);
    this.toastLayer.add(toast);
    this.tweens.add({
      targets: toast, y: 60, duration: 300, ease: 'Back.easeOut',
      onComplete: () => {
        this.time.delayedCall(1600, () => {
          this.tweens.add({ targets: toast, y: -30, alpha: 0, duration: 250, onComplete: () => toast.destroy() });
        });
      },
    });
  }

  _end(won) {
    this.state = STATE.END;
    if (won) this.cameras.main.flash(150, 51, 230, 255, false);
    const panel = this.add.rectangle(W / 2, H / 2, 360, 220, 0x0a0a18, 0.95).setStrokeStyle(2, won ? 0x33e6ff : 0xff3377);
    const title = this.add.text(W / 2, H / 2 - 70, won ? 'TARGET REACHED!' : "TIME'S UP", { fontFamily: 'monospace', fontSize: '26px', color: won ? '#33ffbb' : '#ff3377' }).setOrigin(0.5);
    const scoreT = this.add.text(W / 2, H / 2 - 25, 'Energy: ' + Math.floor(this.energy) + ' / ' + TARGET_ENERGY, { fontFamily: 'monospace', fontSize: '18px', color: '#33e6ff' }).setOrigin(0.5);
    const tapsT = this.add.text(W / 2, H / 2 + 1, this.taps + ' taps  •  ' + Object.values(this.owned).reduce((a, b) => a + b, 0) + ' generators', { fontFamily: 'monospace', fontSize: '13px', color: '#8899ff' }).setOrigin(0.5);
    const restart = this.add.text(W / 2, H / 2 + 43, 'TAP TO RETRY', { fontFamily: 'monospace', fontSize: '16px', color: '#0a0a18', backgroundColor: '#33e6ff', padding: { x: 14, y: 8 } }).setOrigin(0.5).setInteractive();
    restart.on('pointerdown', () => this.scene.restart());
    const cta = this.add.text(W / 2, H / 2 + 87, 'PLAY FULL VERSION', { fontFamily: 'monospace', fontSize: '16px', color: '#ffffff', backgroundColor: '#ff3377', padding: { x: 14, y: 8 } }).setOrigin(0.5);
    this.tweens.add({ targets: [panel, title, scoreT, tapsT, restart, cta], alpha: { from: 0, to: 1 }, duration: 250 });

    if (won) {
      for (let i = 0; i < 26; i++) {
        const p = this.add.rectangle(W / 2, H / 2 - 105, 6, 10, GENERATORS[i % GENERATORS.length].color);
        const angle = -Math.PI / 2 + (Math.random() - 0.5) * 2.2;
        const dist = 120 + Math.random() * 160;
        this.tweens.add({
          targets: p, x: W / 2 + Math.cos(angle) * dist, y: H / 2 - 105 + Math.sin(angle) * dist + 120,
          rotation: Math.random() * 6, alpha: 0, duration: 900 + Math.random() * 400, ease: 'Cubic.easeOut', onComplete: () => p.destroy(),
        });
      }
    }
  }

  update(time, dt) {
    // ambient dust drift
    this.dust.forEach((d) => {
      d.x += d.vx * (dt / 1000);
      d.y += d.vy * (dt / 1000);
      if (d.x < 0 || d.x > W) d.vx *= -1;
      if (d.y < 0 || d.y > H) d.vy *= -1;
    });

    // background hue evolves with total energy earned
    const tier = Math.min(4, Math.floor(this.totalEarned / (TARGET_ENERGY / 4)));
    const hue = 0.55 + tier * 0.05;
    const c1 = Phaser.Display.Color.HSVToRGB(hue, 0.5, 0.1 + tier * 0.015);
    this.bgG.clear();
    this.bgG.fillStyle(Phaser.Display.Color.GetColor(c1.r, c1.g, c1.b), 1);
    this.bgG.fillRect(0, 0, W, H);

    if (this.state !== STATE.PLAYING) return;

    // passive generator production
    let production = 0;
    GENERATORS.forEach((gen) => { production += gen.rate * this.owned[gen.key]; });
    if (production > 0) this._addEnergy(production * (dt / 1000));

    // smooth counter lerp toward real energy value
    this.displayEnergy += (this.energy - this.displayEnergy) * Math.min(1, dt / 120);
    if (Math.abs(this.energy - this.displayEnergy) < 0.5) this.displayEnergy = this.energy;
    this.energyText.setText('Energy: ' + Math.floor(this.displayEnergy));
    this.game.registry.set('score', Math.floor(this.energy));

    // timer bar
    const elapsed = time - this.sessionStart;
    const remain = Phaser.Math.Clamp(1 - elapsed / SESSION_MS, 0, 1);
    this.timerBarFg.width = 300 * remain;
    this.timerBarFg.x = W / 2 - 150;
    this.timerBarFg.fillColor = remain < 0.2 ? 0xff3355 : 0x33e6ff;

    if (this.energy >= TARGET_ENERGY) { this._end(true); return; }
    if (elapsed >= SESSION_MS) { this._end(false); return; }
  }
}

const config = {
  type: Phaser.AUTO,
  parent: 'game-root',
  scale: { mode: Phaser.Scale.FIT, autoCenter: Phaser.Scale.CENTER_BOTH, width: W, height: H },
  backgroundColor: '#0a0a18',
  scene: [PlayScene],
  audio: { noAudio: true },
};

window.addEventListener('load', () => { new Phaser.Game(config); });
