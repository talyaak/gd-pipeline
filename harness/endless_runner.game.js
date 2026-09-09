// Hand-built endless runner harness. Every value here is hardcoded and tuned by
// actually playing the game -- see LESSONS_LEARNED / the rethink discussion for why:
// generated versions of this genre were structurally fine but visually/content
// empty (one obstacle at a time, no variety, no juice). This file exists to prove
// what "fun" looks like for this genre BEFORE anything gets parameterized for
// generation. Do not add a config layer here; pull constants out only after this
// is confirmed fun by actually playing it.

const W = 450, H = 800;
const CTA_LINK = "https://example.com/game";
const LANES_X = [95, 225, 355];
const PLAYER_Y = 620;
const LANE_SWITCH_MS = 140;
const SWIPE_THRESHOLD = 30;

const STATE = { BOOT: 'boot', START: 'start', PLAYING: 'playing', DEAD: 'dead' };

class PlayScene extends Phaser.Scene {
  constructor() {
    super('PlayScene');
  }

  create() {
    this.state = STATE.START;
    this.lane = 1;
    this.targetLane = 1;
    this.score = 0;
    this.best = Number(localStorage.getItem('runner_best') || 0);
    this.multiplier = 1;
    this.speed = 220; // px/sec obstacles+world scroll toward camera
    this.spawnTimer = 0;
    this.spawnInterval = 1300; // ms between spawns, decreases over time
    this.elapsed = 0;
    this.jumping = false;
    this.jumpUntil = 0;
    this.obstacles = [];
    this.pickups = [];
    this.popups = [];

    this.cameras.main.setBackgroundColor('#0a0a18');

    // Parallax tunnel: concentric rings that scroll outward from a vanishing
    // point behind the player, giving a sense of forward speed even when the
    // player itself is stationary in x. This was completely absent from the
    // generated versions -- they had static/empty backgrounds.
    this.tunnelG = this.add.graphics();
    this.ringPhase = 0;

    // Lane guides
    this.laneG = this.add.graphics();

    // Player: glowing square with a fading trail (object pool of ghost squares)
    this.player = this.add.rectangle(LANES_X[1], PLAYER_Y, 34, 34, 0x33e6ff);
    this.player.setStrokeStyle(2, 0xffffff, 0.9);
    this.playerGlow = this.add.rectangle(LANES_X[1], PLAYER_Y, 34, 34, 0x33e6ff, 0.25).setScale(1.8);
    this.trail = [];
    for (let i = 0; i < 6; i++) {
      const g = this.add.rectangle(LANES_X[1], PLAYER_Y, 34, 34, 0x33e6ff, 0.12 - i * 0.018);
      this.trail.push(g);
    }
    this.trailHistory = [];

    // UI
    this.scoreText = this.add.text(16, 12, 'Score: 0', { fontFamily: 'monospace', fontSize: '22px', color: '#33e6ff' });
    this.bestText = this.add.text(16, 38, 'Best: ' + this.best, { fontFamily: 'monospace', fontSize: '16px', color: '#ff33cc' });
    this.multText = this.add.text(W - 16, 12, 'x1', { fontFamily: 'monospace', fontSize: '22px', color: '#ffe14d' }).setOrigin(1, 0);

    this.startText = this.add.text(W / 2, 300, 'TAP or SWIPE\nSWIPE LEFT/RIGHT to switch lanes\nTAP / SWIPE UP to jump', {
      fontFamily: 'monospace', fontSize: '18px', color: '#ffffff', align: 'center'
    }).setOrigin(0.5);
    this.tweens.add({ targets: this.startText, alpha: 0.4, duration: 700, yoyo: true, repeat: -1 });

    // Quick visible intro: point at the player and the lanes for ~2s before
    // the (already-instant) tap-to-start becomes the obvious next move.
    const introBanner = Juice.IntroBanner.create(this, { label: 'DODGE OBSTACLES • JUMP TO SURVIVE' });
    const introHint = Juice.TapHint.create(this, LANES_X[1], PLAYER_Y, { color: 0x33e6ff });
    this.time.delayedCall(2000, () => { introBanner.destroy(); introHint.destroy(); });

    this.input.keyboard.on('keydown-SPACE', () => this._onAction());
    this.input.keyboard.on('keydown-UP', () => this._onAction());
    this.input.keyboard.on('keydown-W', () => this._onAction());
    this.input.keyboard.on('keydown-LEFT', () => this._switchLane(-1));
    this.input.keyboard.on('keydown-A', () => this._switchLane(-1));
    this.input.keyboard.on('keydown-RIGHT', () => this._switchLane(1));
    this.input.keyboard.on('keydown-D', () => this._switchLane(1));

    // Touch: swipe left/right switches lanes, swipe up or a plain tap jumps
    // (or starts/restarts). A tap is just a swipe that never crossed the
    // threshold -- decided on release, not on press, so a lane-switch swipe
    // doesn't also fire a jump.
    this._touchStartX = 0;
    this._touchStartY = 0;
    this._touchDecided = false;
    this.input.on('pointerdown', (p) => {
      this._touchStartX = p.x;
      this._touchStartY = p.y;
      this._touchDecided = false;
    });
    this.input.on('pointermove', (p) => {
      if (!p.isDown || this._touchDecided) return;
      const dx = p.x - this._touchStartX;
      const dy = p.y - this._touchStartY;
      if (Math.abs(dx) > SWIPE_THRESHOLD && Math.abs(dx) > Math.abs(dy)) {
        this._touchDecided = true;
        this._switchLane(dx > 0 ? 1 : -1);
      } else if (dy < -SWIPE_THRESHOLD && Math.abs(dy) > Math.abs(dx)) {
        this._touchDecided = true;
        this._onAction();
      }
    });
    this.input.on('pointerup', () => {
      if (!this._touchDecided) this._onAction();
    });

    window.__GAME__ = this.game;
    this.game.registry.set('score', 0);
  }

  _onAction() {
    if (this.state === STATE.START) {
      this._start();
    } else if (this.state === STATE.PLAYING) {
      this._jump();
    } else if (this.state === STATE.DEAD) {
      this.scene.restart();
    }
  }

  _start() {
    this.state = STATE.PLAYING;
    this.startText.setVisible(false);
    this.sessionStart = this.time.now;
    this.spawnTimer = -1200; // grace period: first obstacle arrives ~2.5s in, not instantly
  }

  _switchLane(dir) {
    if (this.state !== STATE.PLAYING) return;
    const next = Phaser.Math.Clamp(this.targetLane + dir, 0, 2);
    if (next === this.targetLane) return;
    this.targetLane = next;
    this.tweens.add({
      targets: this.player, x: LANES_X[next], duration: LANE_SWITCH_MS, ease: 'Cubic.easeOut',
    });
    this.tweens.add({
      targets: this.playerGlow, x: LANES_X[next], duration: LANE_SWITCH_MS, ease: 'Cubic.easeOut',
    });
    this.lane = next;
  }

  _jump() {
    if (this.jumping) return;
    this.jumping = true;
    this.jumpUntil = this.time.now + 420;
    this.tweens.add({
      targets: [this.player, this.playerGlow], scaleX: 1.35, scaleY: 1.35, duration: 180, yoyo: true, ease: 'Sine.easeOut',
    });
    this.tweens.add({
      targets: [this.player, this.playerGlow], y: PLAYER_Y - 40, duration: 210, yoyo: true, ease: 'Sine.easeOut',
      onComplete: () => { this.jumping = false; },
    });
  }

  _spawnObstacle() {
    // Three distinct patterns, weighted so early game leans easy. No walls at
    // all in the first ~8s -- the hardest pattern (needs an exact lane, no
    // jump escape) shouldn't be the first thing a new player sees.
    const roll = Math.random();
    const difficulty = Phaser.Math.Clamp(this.elapsed / 45000, 0, 1);
    const wallUnlocked = this.elapsed > 8000;
    let type;
    if (roll < 0.55 - difficulty * 0.15) type = 'hurdle';
    else if (roll < 0.85 || !wallUnlocked) type = 'barrier';
    else type = 'wall';

    if (type === 'wall') {
      // blocks two of three lanes, one safe gap
      const safe = Phaser.Math.Between(0, 2);
      [0, 1, 2].forEach((lane) => {
        if (lane === safe) return;
        this._addObstacle(lane, 'wall', 0xff3355, 70);
      });
    } else if (type === 'barrier') {
      const lane = Phaser.Math.Between(0, 2);
      this._addObstacle(lane, 'barrier', 0xff9933, 40);
    } else {
      const lane = Phaser.Math.Between(0, 2);
      this._addObstacle(lane, 'hurdle', 0xffe14d, 18);
    }

    // Occasionally also spawn a pickup in a currently-open lane
    if (Math.random() < 0.55) {
      const lane = Phaser.Math.Between(0, 2);
      const orb = this.add.circle(LANES_X[lane], -20, 9, 0x33ffbb);
      orb.setStrokeStyle(2, 0xffffff, 0.8);
      this.pickups.push({ obj: orb, lane });
    }
  }

  _addObstacle(lane, type, color, height) {
    const rect = this.add.rectangle(LANES_X[lane], -30, 70, height, color);
    rect.setStrokeStyle(2, 0xffffff, 0.5);
    this.obstacles.push({ obj: rect, lane, type });
  }

  _die() {
    if (this.state === STATE.DEAD) return;
    this.state = STATE.DEAD;
    this.cameras.main.shake(220, 0.02);
    this.cameras.main.flash(120, 255, 40, 80);

    // explosion particles
    for (let i = 0; i < 18; i++) {
      const p = this.add.rectangle(this.player.x, this.player.y, 6, 6, 0x33e6ff);
      const angle = Math.random() * Math.PI * 2;
      const dist = 60 + Math.random() * 80;
      this.tweens.add({
        targets: p, x: this.player.x + Math.cos(angle) * dist, y: this.player.y + Math.sin(angle) * dist,
        alpha: 0, duration: 500 + Math.random() * 300, ease: 'Cubic.easeOut', onComplete: () => p.destroy(),
      });
    }
    this.player.setVisible(false);
    this.playerGlow.setVisible(false);

    this.best = Math.max(this.best, Math.floor(this.score));
    localStorage.setItem('runner_best', String(this.best));

    const cx = W / 2, cy = H / 2;
    const panel = this.add.rectangle(cx, cy, 340, 220, 0x0a0a18, 0.92).setStrokeStyle(2, 0x33e6ff);
    const title = this.add.text(cx, cy - 75, 'GAME OVER', { fontFamily: 'monospace', fontSize: '32px', color: '#ff3377' }).setOrigin(0.5);
    const scoreT = this.add.text(cx, cy - 25, 'Score: ' + Math.floor(this.score), { fontFamily: 'monospace', fontSize: '20px', color: '#33e6ff' }).setOrigin(0.5);
    const bestT = this.add.text(cx, cy + 3, 'Best: ' + this.best, { fontFamily: 'monospace', fontSize: '16px', color: '#ffe14d' }).setOrigin(0.5);
    const restart = this.add.text(cx, cy + 45, 'TAP TO RESTART', { fontFamily: 'monospace', fontSize: '16px', color: '#0a0a18', backgroundColor: '#33e6ff', padding: { x: 14, y: 8 } }).setOrigin(0.5).setInteractive();
    const cta = this.add.text(cx, cy + 90, 'PLAY FULL VERSION', { fontFamily: 'monospace', fontSize: '16px', color: '#ffffff', backgroundColor: '#ff3377', padding: { x: 14, y: 8 } }).setOrigin(0.5).setInteractive({ useHandCursor: true });
    this.ctaButton = cta;
    cta.on('pointerdown', () => {
      if (typeof mraid !== 'undefined' && mraid.open) { mraid.open(CTA_LINK); }
      else { window.open(CTA_LINK, '_blank'); }
    });
    this.tweens.add({ targets: [panel, title, scoreT, bestT, restart, cta], alpha: { from: 0, to: 1 }, duration: 250 });
  }

  update(time, dt) {
    if (this.state !== STATE.PLAYING) return;
    this.elapsed = time - this.sessionStart;

    // difficulty ramp: speed up and spawn faster over ~45s, then hold
    const difficulty = Phaser.Math.Clamp(this.elapsed / 45000, 0, 1);
    this.speed = 220 + difficulty * 240;
    this.spawnInterval = 1300 - difficulty * 750;

    // score ticks with survival + multiplier grows every 5s
    this.score += (dt / 1000) * 8 * this.multiplier;
    this.multiplier = 1 + Math.floor(this.elapsed / 5000);
    this.scoreText.setText('Score: ' + Math.floor(this.score));
    this.multText.setText('x' + this.multiplier);
    this.game.registry.set('score', Math.floor(this.score));

    // tunnel rings
    this.ringPhase += dt * 0.12;
    this.tunnelG.clear();
    for (let i = 0; i < 7; i++) {
      const t = ((this.ringPhase + i * 40) % 280) / 280;
      const scale = t;
      const alpha = 0.5 * (1 - t);
      const hue = Phaser.Display.Color.HSVToRGB(0.5 + difficulty * 0.35, 0.6, 0.9);
      this.tunnelG.lineStyle(2, Phaser.Display.Color.GetColor(hue.r, hue.g, hue.b), alpha);
      const w = 60 + scale * 400, h = 40 + scale * 750;
      this.tunnelG.strokeRect(W / 2 - w / 2, 260 - h / 2, w, h);
    }

    // lane guides
    this.laneG.clear();
    this.laneG.lineStyle(1, 0x2a2a55, 0.5);
    LANES_X.forEach((x) => { this.laneG.lineBetween(x, 0, x, H); });

    // trail: shift history, ghost squares follow with delay
    this.trailHistory.unshift({ x: this.player.x, y: this.player.y });
    if (this.trailHistory.length > 40) this.trailHistory.pop();
    this.trail.forEach((g, i) => {
      const h = this.trailHistory[i * 6];
      if (h) { g.x = h.x; g.y = h.y; }
    });

    // spawn
    this.spawnTimer += dt;
    if (this.spawnTimer >= this.spawnInterval) {
      this.spawnTimer = 0;
      this._spawnObstacle();
    }

    // move + collide obstacles
    const move = (this.speed * dt) / 1000;
    for (let i = this.obstacles.length - 1; i >= 0; i--) {
      const o = this.obstacles[i];
      o.obj.y += move;
      if (o.obj.y > H + 20) { o.obj.destroy(); this.obstacles.splice(i, 1); continue; }
      if (Math.abs(o.obj.y - this.player.y) < 24 && o.lane === this.lane) {
        const safe = o.type === 'hurdle' && this.jumping;
        if (!safe) { this._die(); return; }
      }
    }

    // move + collect pickups
    for (let i = this.pickups.length - 1; i >= 0; i--) {
      const p = this.pickups[i];
      p.obj.y += move;
      if (p.obj.y > H + 20) { p.obj.destroy(); this.pickups.splice(i, 1); continue; }
      if (Math.abs(p.obj.y - this.player.y) < 26 && p.lane === this.lane) {
        this.score += 10 * this.multiplier;
        const popup = this.add.text(p.obj.x, p.obj.y, '+' + (10 * this.multiplier), { fontFamily: 'monospace', fontSize: '16px', color: '#33ffbb' }).setOrigin(0.5);
        this.tweens.add({ targets: popup, y: popup.y - 40, alpha: 0, duration: 600, onComplete: () => popup.destroy() });
        for (let k = 0; k < 8; k++) {
          const spark = this.add.circle(p.obj.x, p.obj.y, 3, 0x33ffbb);
          const angle = Math.random() * Math.PI * 2;
          this.tweens.add({ targets: spark, x: p.obj.x + Math.cos(angle) * 40, y: p.obj.y + Math.sin(angle) * 40, alpha: 0, duration: 350, onComplete: () => spark.destroy() });
        }
        p.obj.destroy();
        this.pickups.splice(i, 1);
      }
    }
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
