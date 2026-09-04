// Hand-built tower-defense harness. Same approach as the other
// harness/*.game.js files: hardcoded, tuned by actually playing it.
// STRATEGY.md priority #7 -- the OLD LLM-generation pipeline produced a
// "structurally confirmed playable" version of this genre but it was never
// hand-verified for fun, and there was no hand-built harness. Scoped down
// hard for a single playable-ad session: one lane, one tower type, 3 short
// waves -- not the free-placement multi-tower economy a full game would have.

const W = 450, H = 800;
// Path runs top-to-bottom instead of the old left-to-right -- a horizontal
// lane across only 450px of width felt cramped and gave enemies barely any
// runway; a vertical lane uses the portrait screen's actual long axis and
// reads more naturally on a phone (enemies march down toward you).
const PATH_X = W / 2;
const PATH_TOP = 90;
const PATH_BOTTOM = 750;
const BASE_Y = 770;
const BASE_HP = 10;
const CURRENCY_START = 100;
const TOWER_COST = 40;
const TOWER_RANGE = 100;
const TOWER_DMG = 2;
const TOWER_RATE_MS = 500;
const BUILD_SPOTS = [
  { x: PATH_X - 90, y: 260 },
  { x: PATH_X + 90, y: 420 },
  { x: PATH_X - 90, y: 580 },
];

const WAVES = [
  { count: 5, hp: 5, speed: 55, spawnGap: 900 },
  { count: 5, hp: 7, speed: 70, spawnGap: 800 },
  { count: 5, hp: 9, speed: 85, spawnGap: 700 },
];
const WAVE_GAP_MS = 2500;

const STATE = { START: 'start', PLAYING: 'playing', END: 'end' };

class PlayScene extends Phaser.Scene {
  constructor() {
    super('PlayScene');
  }

  create() {
    this.state = STATE.START;
    this.currency = CURRENCY_START;
    this.baseHp = BASE_HP;
    this.waveIndex = 0;
    this.enemies = [];
    this.towers = [];
    this.killCount = 0;
    this.totalEnemies = WAVES.reduce((s, w) => s + w.count, 0);

    this.cameras.main.setBackgroundColor('#0a0a18');
    this.bgG = this.add.graphics();
    this.bgG.fillGradientStyle(0x0a0a18, 0x0a0a18, 0x101a1a, 0x101a1a, 1);
    this.bgG.fillRect(0, 0, W, H);

    const pathG = this.add.graphics();
    pathG.lineStyle(26, 0x14142a, 1);
    pathG.lineBetween(PATH_X, PATH_TOP, PATH_X, PATH_BOTTOM);
    pathG.lineStyle(2, 0x33e6ff, 0.35);
    pathG.lineBetween(PATH_X, PATH_TOP, PATH_X, PATH_BOTTOM);

    this.baseSprite = this.add.rectangle(PATH_X, BASE_Y, 60, 20, 0x33ffbb).setStrokeStyle(2, 0xffffff, 0.8);
    this.baseHpText = this.add.text(PATH_X + 46, BASE_Y, String(this.baseHp), { fontFamily: 'monospace', fontSize: '14px', color: '#33ffbb' }).setOrigin(0.5);

    this.enemyLayer = this.add.container(0, 0);
    this.towerLayer = this.add.container(0, 0);
    this.fxLayer = this.add.container(0, 0);

    this.buildPads = BUILD_SPOTS.map((spot) => this._buildPad(spot.x, spot.y));

    this.currencyText = this.add.text(16, 12, 'Coins: ' + this.currency, { fontFamily: 'monospace', fontSize: '18px', color: '#ffe14d' });
    this.waveText = this.add.text(W - 16, 12, 'Wave 1 / ' + WAVES.length, { fontFamily: 'monospace', fontSize: '16px', color: '#33e6ff' }).setOrigin(1, 0);

    this.startText = this.add.text(W / 2, 55, 'TAP A PAD TO BUILD\nDEFEND THE BASE', {
      fontFamily: 'monospace', fontSize: '15px', color: '#ffffff', align: 'center',
    }).setOrigin(0.5);
    this.tweens.add({ targets: this.startText, alpha: 0.4, duration: 700, yoyo: true, repeat: -1 });

    const introBanner = Juice.IntroBanner.create(this, { label: 'TAP PADS TO BUILD TOWERS (' + TOWER_COST + ' COINS)', y: 100 });
    const introHint = Juice.TapHint.create(this, BUILD_SPOTS[1].x, BUILD_SPOTS[1].y, { color: 0x33e6ff, radius: 20 });
    this.time.delayedCall(2000, () => { introBanner.destroy(); introHint.destroy(); });

    this.input.on('pointerdown', (p) => this._onPointerDown(p));

    window.__GAME__ = this.game;
    this.game.registry.set('score', 0);
  }

  _buildPad(x, y) {
    const g = this.add.graphics();
    g.lineStyle(2, 0x33e6ff, 0.6);
    g.strokeRoundedRect(x - 20, y - 20, 40, 40, 6);
    return { x, y, g, tower: null };
  }

  _onPointerDown(p) {
    if (this.state === STATE.START) { this._begin(); return; }
    if (this.state === STATE.END) { this.scene.restart(); return; }
    if (this.state !== STATE.PLAYING) return;

    const pad = this.buildPads.find((b) => Math.abs(p.x - b.x) < 24 && Math.abs(p.y - b.y) < 24);
    if (!pad || pad.tower) return;
    if (this.currency < TOWER_COST) {
      this.cameras.main.shake(80, 0.004);
      return;
    }
    this.currency -= TOWER_COST;
    this.currencyText.setText('Coins: ' + this.currency);
    const sprite = this.add.triangle(pad.x, pad.y, 0, 18, 18, -14, -18, -14, 0x33e6ff).setStrokeStyle(2, 0xffffff, 0.8);
    this.towerLayer.add(sprite);
    const tower = { x: pad.x, y: pad.y, sprite, lastFired: -Infinity };
    this.towers.push(tower);
    pad.tower = tower;
    pad.g.clear();
    Juice.ParticleBurst.create(this, pad.x, pad.y, { color: 0x33e6ff, count: 10 });
  }

  _begin() {
    this.state = STATE.PLAYING;
    this.startText.setVisible(false);
    this._startWave();
    // Initialize sessionTime on Game instance for validation
    this.game.sessionTime = 0;
  }

  _startWave() {
    if (this.waveIndex >= WAVES.length) return;
    const wave = WAVES[this.waveIndex];
    this.waveText.setText('Wave ' + (this.waveIndex + 1) + ' / ' + WAVES.length);
    this.waveSpawnDone = false;
    let spawned = 0;
    this.spawnTimer = this.time.addEvent({
      delay: wave.spawnGap,
      callback: () => {
        this._spawnEnemy(wave);
        spawned += 1;
        if (spawned >= wave.count) {
          this.waveSpawnDone = true;
          this.spawnTimer.remove(false);
        }
      },
      repeat: wave.count - 1,
    });
  }

  _spawnEnemy(wave) {
    const sprite = this.add.circle(PATH_X, PATH_TOP - 20, 12, 0xff3377).setStrokeStyle(2, 0xffffff, 0.7);
    const hpBar = this.add.rectangle(PATH_X, PATH_TOP - 40, 22, 4, 0x33ff88).setOrigin(0.5);
    this.enemyLayer.add(sprite);
    this.enemyLayer.add(hpBar);
    this.enemies.push({ sprite, hpBar, hp: wave.hp, maxHp: wave.hp, speed: wave.speed, alive: true });
  }

  _end(won) {
    this.state = STATE.END;
    if (this.spawnTimer) this.spawnTimer.remove(false);
    Juice.GameOverPanel.create(this, {
      won,
      score: this.killCount,
      target: this.totalEnemies,
      best: 0,
      onRetry: () => this.scene.restart(),
      onCTA: () => {}
    });
  }

  update(time, dt) {
    if (this.state !== STATE.PLAYING) return;
    const dtS = dt / 1000;

    this.game.sessionTime = (this.game.sessionTime || 0) + dt;

    // enemies advance
    for (let i = this.enemies.length - 1; i >= 0; i--) {
      const e = this.enemies[i];
      if (!e.alive) continue;
      e.sprite.y += e.speed * dtS;
      e.hpBar.y = e.sprite.y - 20;
      if (e.sprite.y >= BASE_Y - 20) {
        this.baseHp -= 1;
        this.baseHpText.setText(String(this.baseHp));
        this.cameras.main.shake(120, 0.006);
        e.alive = false;
        e.sprite.destroy(); e.hpBar.destroy();
        this.enemies.splice(i, 1);
        if (this.baseHp <= 0) { this._end(false); return; }
      }
    }

    // towers fire
    this.towers.forEach((t) => {
      if (time - t.lastFired < TOWER_RATE_MS) return;
      const target = this.enemies.find((e) => e.alive && Math.abs(e.sprite.y - t.y) < TOWER_RANGE);
      if (!target) return;
      t.lastFired = time;
      const beam = this.add.line(0, 0, t.x, t.y, target.sprite.x, target.sprite.y, 0x33e6ff, 0.8).setOrigin(0, 0).setLineWidth(2);
      this.fxLayer.add(beam);
      this.tweens.add({ targets: beam, alpha: 0, duration: 120, onComplete: () => beam.destroy() });
      target.hp -= TOWER_DMG;
      target.hpBar.width = Math.max(0, 22 * (target.hp / target.maxHp));
      if (target.hp <= 0 && target.alive) {
        target.alive = false;
        Juice.ParticleBurst.create(this, target.sprite.x, target.sprite.y, { color: 0xff3377, count: 8 });
        target.sprite.destroy(); target.hpBar.destroy();
        const idx = this.enemies.indexOf(target);
        if (idx >= 0) this.enemies.splice(idx, 1);
        this.killCount += 1;
        this.currency += 10;
        this.currencyText.setText('Coins: ' + this.currency);
        this.game.registry.set('score', this.killCount);
      }
    });

    // wave progression -- guarded by waveAdvancing so this fires exactly
    // once per wave clear, not every frame the condition stays true. Uses an
    // explicit waveSpawnDone flag rather than the timer's own progress:
    // Phaser's TimerEvent.getOverallProgress() doesn't reliably read back as
    // complete once the timer has been manually .remove()'d early.
    if (!this.waveAdvancing && this.waveSpawnDone && this.enemies.length === 0) {
      this.waveAdvancing = true;
      this.waveIndex += 1;
      if (this.waveIndex >= WAVES.length) {
        this.time.delayedCall(300, () => this._end(true));
      } else {
        this.time.delayedCall(WAVE_GAP_MS, () => { this.waveAdvancing = false; this._startWave(); });
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
