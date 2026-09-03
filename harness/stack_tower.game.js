// Hand-built stack-tower harness. Same approach as the other
// harness/*.game.js files: hardcoded, tuned by actually playing it.
// Priority #5 in STRATEGY.md's genre list, no GDD existed yet.

const TARGET_LAYERS = 15;
const BLOCK_H = 28;
const ACTIVE_Y = 150;
const FIRST_ROW_Y = ACTIVE_Y + BLOCK_H;
const ROW_REMOVE_Y = 430;
const BASE_WIDTH = 260;
const PERFECT_TOLERANCE = 6;
const BASE_SPEED = 140; // px/sec of horizontal oscillation
const SPEED_STEP = 8;
const MAX_SPEED = 320;
const MARGIN = 40;
const PALETTE = [0x33e6ff, 0xff33cc, 0xffe14d, 0x33ff88, 0xff9933, 0xaa66ff];

const STATE = { START: 'start', PLAYING: 'playing', END: 'end' };

class PlayScene extends Phaser.Scene {
  constructor() {
    super('PlayScene');
  }

  create() {
    this.state = STATE.START;
    this.score = 0;
    this.combo = 0;
    this.layer = 0;
    this.rows = []; // { sprite, left, right, y }

    this.cameras.main.setBackgroundColor('#0a0a18');
    this.bgG = this.add.graphics();
    this.bgG.fillGradientStyle(0x0a0a18, 0x0a0a18, 0x121226, 0x121226, 1);
    this.bgG.fillRect(0, 0, 800, 450);

    this.rowLayer = this.add.container(0, 0);
    this.particlesLayer = this.add.container(0, 0);

    // base row (foundation, not player-placed)
    const baseLeft = 400 - BASE_WIDTH / 2;
    const baseRight = 400 + BASE_WIDTH / 2;
    const baseSprite = this.add.rectangle(400, FIRST_ROW_Y, BASE_WIDTH, BLOCK_H, PALETTE[0]).setStrokeStyle(2, 0xffffff, 0.6);
    this.rowLayer.add(baseSprite);
    this.rows.push({ sprite: baseSprite, left: baseLeft, right: baseRight, y: FIRST_ROW_Y });

    this.scoreText = this.add.text(16, 12, 'Score: 0', { fontFamily: 'monospace', fontSize: '20px', color: '#33e6ff' });
    this.layerText = this.add.text(16, 36, 'Layer: 0 / ' + TARGET_LAYERS, { fontFamily: 'monospace', fontSize: '14px', color: '#ffe14d' });

    this.startText = this.add.text(400, 60, 'TAP TO DROP  •  STACK ' + TARGET_LAYERS + ' LAYERS', {
      fontFamily: 'monospace', fontSize: '16px', color: '#ffffff', align: 'center',
    }).setOrigin(0.5);
    this.tweens.add({ targets: this.startText, alpha: 0.4, duration: 700, yoyo: true, repeat: -1 });

    const introBanner = Juice.IntroBanner.create(this, { label: 'TAP WHEN ALIGNED TO STACK PERFECTLY', y: 44 });
    const introHint = Juice.TapHint.create(this, 400, ACTIVE_Y, { color: 0x33e6ff, radius: 24 });
    this.time.delayedCall(2000, () => { introBanner.destroy(); introHint.destroy(); });

    this._spawnMovingBlock(baseLeft, baseRight);

    this.input.on('pointerdown', () => this._onTap());
    this.input.keyboard.on('keydown-SPACE', () => this._onTap());

    window.__GAME__ = this.game;
    this.game.registry.set('score', 0);
  }

  _spawnMovingBlock(prevLeft, prevRight) {
    const width = prevRight - prevLeft;
    const fromLeftSide = this.layer % 2 === 0;
    const speed = Math.min(MAX_SPEED, BASE_SPEED + this.layer * SPEED_STEP);
    const minCenter = MARGIN + width / 2;
    const maxCenter = 800 - MARGIN - width / 2;
    const sprite = this.add.rectangle(fromLeftSide ? minCenter : maxCenter, ACTIVE_Y, width, BLOCK_H, PALETTE[this.layer % PALETTE.length]).setStrokeStyle(2, 0xffffff, 0.7);
    this.moving = {
      sprite, width, speed, dir: fromLeftSide ? 1 : -1, minCenter, maxCenter,
    };
  }

  _onTap() {
    if (this.state === STATE.START) { this._begin(); return; }
    if (this.state === STATE.END) { this.scene.restart(); return; }
    if (this.state !== STATE.PLAYING || !this.moving) return;

    const m = this.moving;
    const movLeft = m.sprite.x - m.width / 2;
    const movRight = m.sprite.x + m.width / 2;
    const prev = this.rows[this.rows.length - 1];

    const overlapLeft = Math.max(movLeft, prev.left);
    const overlapRight = Math.min(movRight, prev.right);
    const overlapWidth = overlapRight - overlapLeft;

    if (overlapWidth <= 4) {
      this._miss(m);
      return;
    }

    let newLeft = overlapLeft, newRight = overlapRight;
    let perfect = false;
    const prevWidth = prev.right - prev.left;
    if (Math.abs(overlapWidth - prevWidth) <= PERFECT_TOLERANCE) {
      perfect = true;
      newLeft = prev.left;
      newRight = prev.right;
    }

    this.combo = perfect ? this.combo + 1 : 0;
    const points = 10 + (perfect ? 20 * Math.max(1, this.combo) : 0);
    this.score += points;
    this.scoreText.setText('Score: ' + this.score);
    this.game.registry.set('score', this.score);

    // destroy the overhang piece(s) with a little "falls off" animation
    if (movLeft < newLeft - 0.5) this._dropOffcut(movLeft, newLeft, m.sprite.y, m.sprite.fillColor);
    if (movRight > newRight + 0.5) this._dropOffcut(newRight, movRight, m.sprite.y, m.sprite.fillColor);

    const newWidth = newRight - newLeft;
    const newX = newLeft + newWidth / 2;
    const placed = this.add.rectangle(newX, ACTIVE_Y, newWidth, BLOCK_H, m.sprite.fillColor).setStrokeStyle(2, 0xffffff, 0.8);
    this.rowLayer.add(placed);
    m.sprite.destroy();
    this.moving = null;

    if (perfect) {
      this.cameras.main.flash(90, 255, 225, 77, false);
      Juice.ParticleBurst.create(this, newX, ACTIVE_Y, { color: 0xffe14d, count: 10 });
      const popup = this.add.text(newX, ACTIVE_Y - 24, 'PERFECT' + (this.combo > 1 ? ' x' + this.combo : ''), { fontFamily: 'monospace', fontSize: '13px', color: '#ffe14d' }).setOrigin(0.5);
      this.tweens.add({ targets: popup, y: popup.y - 20, alpha: 0, duration: 500, onComplete: () => popup.destroy() });
    }

    this.layer += 1;
    this.layerText.setText('Layer: ' + this.layer + ' / ' + TARGET_LAYERS);

    // shift existing rows down, drop the new one into place
    this.rows.push({ sprite: placed, left: newLeft, right: newRight, y: ACTIVE_Y });
    this.rows.forEach((row) => {
      row.y += BLOCK_H;
      this.tweens.add({ targets: row.sprite, y: row.y, duration: 160, ease: 'Cubic.easeOut' });
    });
    this.rows = this.rows.filter((row) => {
      if (row.y > ROW_REMOVE_Y) { this.tweens.add({ targets: row.sprite, alpha: 0, duration: 150, onComplete: () => row.sprite.destroy() }); return false; }
      return true;
    });

    if (this.layer >= TARGET_LAYERS) {
      this.time.delayedCall(200, () => this._end(true));
      return;
    }
    this._spawnMovingBlock(newLeft, newRight);
  }

  _dropOffcut(left, right, y, color) {
    const w = right - left;
    if (w <= 0) return;
    const cut = this.add.rectangle(left + w / 2, y, w, BLOCK_H, color, 0.85);
    this.tweens.add({ targets: cut, y: y + 220, rotation: (Math.random() - 0.5) * 2, alpha: 0, duration: 500, ease: 'Cubic.easeIn', onComplete: () => cut.destroy() });
  }

  _miss(m) {
    this.cameras.main.shake(180, 0.01);
    this.tweens.add({ targets: m.sprite, y: m.sprite.y + 260, rotation: (Math.random() - 0.5) * 3, alpha: 0, duration: 550, ease: 'Cubic.easeIn' });
    this.moving = null;
    this.time.delayedCall(400, () => this._end(false));
  }

  _begin() {
    this.state = STATE.PLAYING;
    this.startText.setVisible(false);
  }

  _end(won) {
    this.state = STATE.END;
    Juice.GameOverPanel.create(this, {
      won,
      score: this.score,
      target: 0,
      best: 0,
      onRetry: () => this.scene.restart(),
      onCTA: () => {}
    });
  }

  update(time, dt) {
    if (this.state !== STATE.PLAYING || !this.moving) return;
    const m = this.moving;
    m.sprite.x += m.dir * m.speed * (dt / 1000);
    if (m.sprite.x <= m.minCenter) { m.sprite.x = m.minCenter; m.dir = 1; }
    if (m.sprite.x >= m.maxCenter) { m.sprite.x = m.maxCenter; m.dir = -1; }
  }
}

const config = {
  type: Phaser.AUTO,
  width: 800,
  height: 450,
  parent: undefined,
  backgroundColor: '#0a0a18',
  scene: [PlayScene],
  audio: { noAudio: true },
};

window.addEventListener('load', () => { new Phaser.Game(config); });
