// Hand-built physics "pull the pin" harness. Same approach as the other
// harness/*.game.js files: hardcoded, tuned by actually playing it.
//
// No GDD existed for this genre yet (STRATEGY.md flagged it "not tested at
// all"), so this was designed directly rather than scoped down from one.
//
// Deliberately does NOT use Matter.js or any physics library: the vendored
// Phaser build (pipeline/vendor/phaser.min.js) doesn't include the Matter
// plugin, and pulling in an extra library would break the "single
// self-contained HTML file, no external assets" constraint every genre in
// this project has held to. Physics here is hand-rolled: gravity, AABB
// ball-vs-shelf collision, and soft circle-circle separation. That's the
// right amount of physics for what this genre actually needs -- balls
// falling and resting on shelves, not a general rigid-body simulation.

const W = 450, H = 800;
const CTA_LINK = "https://example.com/game";
const GRAVITY = 900;
const WALL_L = 70, WALL_R = 380;
const CHAMBER_TOP = 140, CHAMBER_BOTTOM = 680;
const BALL_R = 12;
const BALL_COUNT = 10;
const PIN_PULLS = 3;
const TARGET_COLLECTED = 6;
const SESSION_MS = 40000;
const TIMER_BAR_W = 180;
const BALL_COLORS = [0x33e6ff, 0xff33cc, 0xffe14d, 0x33ff88, 0xff9933];

// Each shelf is two rectangle segments with a gap between them -- balls can
// trickle through the gap on their own over time, or the player can spend a
// pin-pull to remove the whole shelf for an instant cascade. Positions here
// are proportional to the original 800x450 landscape layout, just spread
// across the taller portrait chamber.
const SHELVES = [
  { y: 299, gapCenter: 159, gapWidth: 60 },
  { y: 426, gapCenter: 291, gapWidth: 60 },
  { y: 553, gapCenter: 225, gapWidth: 60 },
];
const SHELF_H = 10;

const STATE = { START: 'start', PLAYING: 'playing', END: 'end' };

class PlayScene extends Phaser.Scene {
  constructor() {
    super('PlayScene');
  }

  create() {
    this.state = STATE.START;
    this.collected = 0;
    this.pullsLeft = PIN_PULLS;
    this.shelfAlive = SHELVES.map(() => true);

    this.cameras.main.setBackgroundColor('#0a0a18');
    this.bgG = this.add.graphics();
    this.bgG.fillGradientStyle(0x0a0a18, 0x0a0a18, 0x151530, 0x151530, 1);
    this.bgG.fillRect(0, 0, 800, 450);

    // Chamber walls
    const wallsG = this.add.graphics();
    wallsG.lineStyle(3, 0x33e6ff, 0.5);
    wallsG.lineBetween(WALL_L, CHAMBER_TOP, WALL_L, CHAMBER_BOTTOM);
    wallsG.lineBetween(WALL_R, CHAMBER_TOP, WALL_R, CHAMBER_BOTTOM);
    wallsG.lineStyle(2, 0x33ffbb, 0.7);
    wallsG.strokeRoundedRect(WALL_L - 6, CHAMBER_BOTTOM, WALL_R - WALL_L + 12, 20, 4);
    this.add.text((WALL_L + WALL_R) / 2, CHAMBER_BOTTOM + 10, 'GOAL', { fontFamily: 'monospace', fontSize: '12px', color: '#33ffbb' }).setOrigin(0.5);

    this.shelfLayer = this.add.container(0, 0);
    this.shelfGfx = SHELVES.map((s) => this._buildShelfSprite(s));

    this.particlesLayer = this.add.container(0, 0);

    this.energyText = null;
    this.scoreText = this.add.text(16, 12, 'Collected: 0 / ' + TARGET_COLLECTED, { fontFamily: 'monospace', fontSize: '18px', color: '#33ffbb' });
    this.pullsText = this.add.text(16, 36, 'Pin pulls: ' + this.pullsLeft, { fontFamily: 'monospace', fontSize: '14px', color: '#ffe14d' });
    this.timerBarBg = this.add.rectangle(W - 16 - TIMER_BAR_W / 2, 20, TIMER_BAR_W, 10, 0x14142a).setStrokeStyle(1, 0x33e6ff, 0.5);
    this.timerBarFg = this.add.rectangle(W - 16 - TIMER_BAR_W, 20, TIMER_BAR_W, 10, 0x33e6ff).setOrigin(0, 0.5);

    this.startText = this.add.text(W / 2, 60, 'TAP A SHELF TO PULL ITS PIN', {
      fontFamily: 'monospace', fontSize: '16px', color: '#ffffff', align: 'center',
    }).setOrigin(0.5);
    this.tweens.add({ targets: this.startText, alpha: 0.4, duration: 700, yoyo: true, repeat: -1 });

    this.balls = [];
    for (let i = 0; i < BALL_COUNT; i++) {
      const x = WALL_L + 25 + (i % 5) * 55 + (Math.random() - 0.5) * 10;
      const y = CHAMBER_TOP + 15 + Math.floor(i / 5) * 30;
      const color = BALL_COLORS[i % BALL_COLORS.length];
      const sprite = this.add.circle(x, y, BALL_R, color).setStrokeStyle(2, 0xffffff, 0.7);
      this.balls.push({ sprite, x, y, vx: (Math.random() - 0.5) * 20, vy: 0, alive: true });
    }

    // Quick visible intro: point at the first pin for ~2s before the
    // (already-instant) tap-to-start becomes the obvious next move.
    const introBanner = Juice.IntroBanner.create(this, { label: 'TAP A PIN TO DROP THE BALLS', y: 100 });
    const introHint = Juice.TapHint.create(this, SHELVES[0].gapCenter, SHELVES[0].y, { color: 0xffe14d, radius: 16 });
    this.time.delayedCall(2000, () => { introBanner.destroy(); introHint.destroy(); });

    this.input.on('pointerdown', (p) => this._onPointerDown(p));

    window.__GAME__ = this.game;
    this.game.registry.set('score', 0);
  }

  _buildShelfSprite(shelf) {
    const g = this.add.graphics();
    this._drawShelf(g, shelf, true);
    const zone = this.add.zone(WALL_L, shelf.y - SHELF_H, WALL_R - WALL_L, SHELF_H * 2).setOrigin(0, 0).setInteractive();
    zone.shelfRef = shelf;
    return { g, zone, alive: true };
  }

  _drawShelf(g, shelf, alive) {
    g.clear();
    if (!alive) return;
    const gapL = shelf.gapCenter - shelf.gapWidth / 2;
    const gapR = shelf.gapCenter + shelf.gapWidth / 2;
    g.fillStyle(0xff9933, 0.85);
    g.lineStyle(2, 0xffffff, 0.6);
    g.fillRect(WALL_L, shelf.y, gapL - WALL_L, SHELF_H);
    g.strokeRect(WALL_L, shelf.y, gapL - WALL_L, SHELF_H);
    g.fillRect(gapR, shelf.y, WALL_R - gapR, SHELF_H);
    g.strokeRect(gapR, shelf.y, WALL_R - gapR, SHELF_H);
    // pin marker
    g.fillStyle(0xffe14d, 1);
    g.fillCircle(shelf.gapCenter, shelf.y + SHELF_H / 2, 5);
  }

  _onPointerDown(p) {
    if (this.state === STATE.START) { this._begin(); return; }
    if (this.state === STATE.END) { return; } // GameOverPanel's own TAP TO RETRY button handles restart; a blanket restart-on-any-tap here raced with clicking the CTA button
    if (this.state !== STATE.PLAYING) return;
    if (this.pullsLeft <= 0) return;

    for (let i = 0; i < SHELVES.length; i++) {
      if (!this.shelfAlive[i]) continue;
      const s = SHELVES[i];
      if (p.y >= s.y - 16 && p.y <= s.y + 16 && p.x >= WALL_L && p.x <= WALL_R) {
        this._pullPin(i);
        return;
      }
    }
  }

  _pullPin(i) {
    this.shelfAlive[i] = false;
    this.pullsLeft -= 1;
    this.pullsText.setText('Pin pulls: ' + this.pullsLeft);
    this._drawShelf(this.shelfGfx[i].g, SHELVES[i], false);
    this.shelfGfx[i].zone.disableInteractive();
    this.cameras.main.shake(140, 0.006);
    for (let k = 0; k < 14; k++) {
      const p = this.add.circle(SHELVES[i].gapCenter, SHELVES[i].y, 3, 0xffe14d);
      const angle = Math.random() * Math.PI * 2;
      const dist = 30 + Math.random() * 50;
      this.tweens.add({
        targets: p, x: SHELVES[i].gapCenter + Math.cos(angle) * dist, y: SHELVES[i].y + Math.sin(angle) * dist,
        alpha: 0, duration: 400 + Math.random() * 200, ease: 'Cubic.easeOut', onComplete: () => p.destroy(),
      });
    }
  }

  _begin() {
    this.state = STATE.PLAYING;
    this.startText.setVisible(false);
    this.sessionStart = this.time.now;
    // Initialize sessionTime on Game instance for validation
    this.game.sessionTime = 0;
  }

  _collect(ball) {
    ball.alive = false;
    this.collected += 1;
    this.scoreText.setText('Collected: ' + this.collected + ' / ' + TARGET_COLLECTED);
    this.game.registry.set('score', this.collected);
    const x = ball.sprite.x;
    this.tweens.add({ targets: ball.sprite, scale: 1.6, alpha: 0, duration: 220, ease: 'Cubic.easeOut', onComplete: () => ball.sprite.destroy() });
    for (let k = 0; k < 8; k++) {
      const p = this.add.circle(x, CHAMBER_BOTTOM + 8, 3, 0x33ffbb);
      const angle = Math.random() * Math.PI * 2;
      const dist = 16 + Math.random() * 20;
      this.tweens.add({
        targets: p, x: x + Math.cos(angle) * dist, y: CHAMBER_BOTTOM + 8 + Math.sin(angle) * dist, alpha: 0,
        duration: 350, ease: 'Cubic.easeOut', onComplete: () => p.destroy(),
      });
    }
  }

  _end(won) {
    this.state = STATE.END;
    if (won) this.cameras.main.flash(150, 51, 255, 187, false);
    const cx = W / 2, cy = H / 2;
    const panel = this.add.rectangle(cx, cy, 360, 220, 0x0a0a18, 0.95).setStrokeStyle(2, won ? 0x33ffbb : 0xff3377);
    const title = this.add.text(cx, cy - 70, won ? 'RESCUED!' : "TIME'S UP", { fontFamily: 'monospace', fontSize: '26px', color: won ? '#33ffbb' : '#ff3377' }).setOrigin(0.5);
    const scoreT = this.add.text(cx, cy - 25, 'Collected: ' + this.collected + ' / ' + TARGET_COLLECTED, { fontFamily: 'monospace', fontSize: '18px', color: '#33e6ff' }).setOrigin(0.5);
    const pullsT = this.add.text(cx, cy + 1, (PIN_PULLS - this.pullsLeft) + ' pins pulled', { fontFamily: 'monospace', fontSize: '13px', color: '#8899ff' }).setOrigin(0.5);
    const restart = this.add.text(cx, cy + 43, 'TAP TO RETRY', { fontFamily: 'monospace', fontSize: '16px', color: '#0a0a18', backgroundColor: '#33e6ff', padding: { x: 14, y: 8 } }).setOrigin(0.5);
    const cta = this.add.text(cx, cy + 87, 'PLAY FULL VERSION', { fontFamily: 'monospace', fontSize: '16px', color: '#ffffff', backgroundColor: '#ff3377', padding: { x: 14, y: 8 } }).setOrigin(0.5).setInteractive({ useHandCursor: true });
    this.ctaButton = cta;
    cta.on('pointerdown', () => {
      if (typeof mraid !== 'undefined' && mraid.open) { mraid.open(CTA_LINK); }
      else { window.open(CTA_LINK, '_blank'); }
    });
    this.tweens.add({ targets: [panel, title, scoreT, pullsT, restart, cta], alpha: { from: 0, to: 1 }, duration: 250 });
  }

  update(time, dt) {
    if (this.state === STATE.PLAYING) {
      const elapsed = time - this.sessionStart;
      const remain = Phaser.Math.Clamp(1 - elapsed / SESSION_MS, 0, 1);
      this.timerBarFg.width = TIMER_BAR_W * remain;
      this.timerBarFg.fillColor = remain < 0.2 ? 0xff3355 : 0x33e6ff;
      if (elapsed >= SESSION_MS && this.collected < TARGET_COLLECTED) { this._end(false); return; }
      if (this.collected >= TARGET_COLLECTED) { this._end(true); return; }
    }

    this.game.sessionTime = (this.game.sessionTime || 0) + dt;

    const dtS = Math.min(dt, 32) / 1000;
    if (this.state !== STATE.PLAYING) {
      // still let physics settle before/after play (e.g. initial spawn drop)
    }

    const live = this.balls.filter((b) => b.alive);

    // gravity + integrate
    live.forEach((b) => {
      b.vy += GRAVITY * dtS;
      b.x += b.vx * dtS;
      b.y += b.vy * dtS;
      b.vx *= 0.995;
    });

    // shelf collision
    live.forEach((b) => {
      for (let i = 0; i < SHELVES.length; i++) {
        if (!this.shelfAlive[i]) continue;
        const s = SHELVES[i];
        const gapL = s.gapCenter - s.gapWidth / 2;
        const gapR = s.gapCenter + s.gapWidth / 2;
        const onLeftSeg = b.x + BALL_R > WALL_L && b.x - BALL_R < gapL;
        const onRightSeg = b.x + BALL_R > gapR && b.x - BALL_R < WALL_R;
        if (!onLeftSeg && !onRightSeg) continue;
        if (b.vy >= 0 && b.y + BALL_R > s.y && b.y + BALL_R < s.y + SHELF_H + 14) {
          b.y = s.y - BALL_R;
          b.vy = -b.vy * 0.12;
          b.vx *= 0.7;
        }
      }
    });

    // wall collision
    live.forEach((b) => {
      if (b.x - BALL_R < WALL_L) { b.x = WALL_L + BALL_R; b.vx = Math.abs(b.vx) * 0.4; }
      if (b.x + BALL_R > WALL_R) { b.x = WALL_R - BALL_R; b.vx = -Math.abs(b.vx) * 0.4; }
    });

    // soft ball-ball separation
    for (let i = 0; i < live.length; i++) {
      for (let j = i + 1; j < live.length; j++) {
        const a = live[i], b = live[j];
        const dx = b.x - a.x, dy = b.y - a.y;
        const dist = Math.sqrt(dx * dx + dy * dy) || 0.001;
        const minDist = BALL_R * 2;
        if (dist < minDist) {
          const overlap = (minDist - dist) / 2;
          const nx = dx / dist, ny = dy / dist;
          a.x -= nx * overlap; a.y -= ny * overlap;
          b.x += nx * overlap; b.y += ny * overlap;
        }
      }
    }

    // goal detection + sync sprites
    live.forEach((b) => {
      if (b.y - BALL_R > CHAMBER_BOTTOM) {
        this._collect(b);
        return;
      }
      b.sprite.x = b.x;
      b.sprite.y = b.y;
    });
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
