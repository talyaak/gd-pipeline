// Hand-built ball/water-sort harness. Same approach as the other
// harness/*.game.js files: hardcoded, tuned by actually playing it.
// Priority #4 in STRATEGY.md's genre list, no GDD existed yet.
//
// Puzzle generation: a straight random shuffle-and-deal, not a scramble from
// solved via random legal pours. A scramble-from-solved was tried first and
// turned out to be a dead end for this shape (colors×4 exactly filling
// colors+2 tubes at capacity 4): with only 2 empty tubes and every source
// tube starting as a single solid color, the only legal moves are relocating
// an entire intact color-stack into an empty tube -- every "scrambled" board
// that produces was, on inspection, still fully solved, just with colors
// sitting in different tube slots. Direct random dealing risks an occasional
// unsolvable board, which a generous move limit makes an acceptable trade
// for a demo harness (not a real puzzle game promising fair levels).

const TUBE_CAPACITY = 4;
const COLORS = [0x33e6ff, 0xff33cc, 0xffe14d, 0x33ff88];
const EMPTY_TUBES = 2;
const MOVE_LIMIT = 30;
const SESSION_MS = 60000;

const W = 450, H = 800;
const CTA_LINK = "https://example.com/game";
const TUBE_W = 54;
const TUBE_H = TUBE_CAPACITY * 34 + 20;
// 6 tubes in one row needs ~700px (the old 800x450 layout) -- doesn't fit a
// 450-wide portrait screen. Two rows of 3 instead, each tube tracking its
// own (x, y) rather than a single shared TUBE_Y.
const TUBE_COLS = 3;
const COL_X = [100, 225, 350];
const ROW_Y = [280, 590];
const BALL_R = 15;

const STATE = { START: 'start', PLAYING: 'playing', END: 'end' };

class PlayScene extends Phaser.Scene {
  constructor() {
    super('PlayScene');
  }

  create() {
    this.state = STATE.START;
    this.moves = MOVE_LIMIT;
    this.selected = null;
    this.tubeSprites = [];

    this.cameras.main.setBackgroundColor('#0a0a18');
    this.bgG = this.add.graphics();
    this.bgG.fillGradientStyle(0x0a0a18, 0x0a0a18, 0x101528, 0x101528, 1);
    this.bgG.fillRect(0, 0, W, H);

    this._generatePuzzle();

    this.tubeX = this.tubes.map((_, i) => COL_X[i % TUBE_COLS]);
    this.tubeY = this.tubes.map((_, i) => ROW_Y[Math.floor(i / TUBE_COLS)]);

    this.tubeLayer = this.add.container(0, 0);
    this.tubes.forEach((_, i) => this._buildTubeSprite(i));
    this._renderAllTubes();

    this.movesText = this.add.text(16, 12, 'Moves: ' + this.moves, { fontFamily: 'monospace', fontSize: '18px', color: '#ffffff' });
    this.timerBarBg = this.add.rectangle(W / 2, 20, 220, 10, 0x14142a).setStrokeStyle(1, 0x33e6ff, 0.5);
    this.timerBarFg = this.add.rectangle(W / 2 - 110, 20, 220, 10, 0x33e6ff).setOrigin(0, 0.5);

    this.startText = this.add.text(W / 2, 55, 'TAP TWO TUBES TO POUR\nSORT EACH COLOR', {
      fontFamily: 'monospace', fontSize: '15px', color: '#ffffff', align: 'center',
    }).setOrigin(0.5);
    this.tweens.add({ targets: this.startText, alpha: 0.4, duration: 700, yoyo: true, repeat: -1 });

    const introBanner = Juice.IntroBanner.create(this, { label: 'POUR MATCHING COLORS TOGETHER', y: 100 });
    const introHint = Juice.TapHint.create(this, this.tubeX[0], this.tubeY[0] - 40, { color: COLORS[0], radius: 30 });
    this.time.delayedCall(2000, () => { introBanner.destroy(); introHint.destroy(); });

    this.input.on('pointerdown', (p) => this._onPointerDown(p));

    window.__GAME__ = this.game;
    this.game.registry.set('score', 0);
  }

  // ---- puzzle generation ----

  _generatePuzzle() {
    const balls = [];
    COLORS.forEach((color) => { for (let i = 0; i < TUBE_CAPACITY; i++) balls.push(color); });
    Phaser.Utils.Array.Shuffle(balls);
    this.tubes = [];
    for (let t = 0; t < COLORS.length; t++) {
      this.tubes.push(balls.slice(t * TUBE_CAPACITY, (t + 1) * TUBE_CAPACITY));
    }
    for (let i = 0; i < EMPTY_TUBES; i++) this.tubes.push([]);
  }

  _pourAmount(fromIdx, toIdx) {
    const src = this.tubes[fromIdx];
    const dst = this.tubes[toIdx];
    if (src.length === 0) return 0;
    const topColor = src[src.length - 1];
    let count = 0;
    for (let i = src.length - 1; i >= 0 && src[i] === topColor; i--) count++;
    const capacity = TUBE_CAPACITY - dst.length;
    if (capacity <= 0) return 0;
    if (dst.length > 0 && dst[dst.length - 1] !== topColor) return 0;
    return Math.min(count, capacity);
  }

  _applyPour(fromIdx, toIdx) {
    const amount = this._pourAmount(fromIdx, toIdx);
    const src = this.tubes[fromIdx];
    const dst = this.tubes[toIdx];
    const color = src[src.length - 1];
    for (let i = 0; i < amount; i++) { src.pop(); dst.push(color); }
    return amount;
  }

  // ---- rendering ----

  _buildTubeSprite(i) {
    const x = this.tubeX[i], ty = this.tubeY[i];
    const g = this.add.graphics();
    g.lineStyle(3, 0x33e6ff, 0.5);
    g.strokeRoundedRect(x - TUBE_W / 2, ty - TUBE_H, TUBE_W, TUBE_H, 10);
    const ballLayer = this.add.container(0, 0);
    this.tubeSprites[i] = { g, ballLayer, highlight: null };
  }

  _renderAllTubes() {
    this.tubes.forEach((_, i) => this._renderTube(i));
  }

  _renderTube(i) {
    const spr = this.tubeSprites[i];
    spr.ballLayer.removeAll(true);
    const x = this.tubeX[i], ty = this.tubeY[i];
    this.tubes[i].forEach((color, slot) => {
      const y = ty - 12 - slot * 34 - 17;
      const ball = this.add.circle(x, y, BALL_R, color).setStrokeStyle(2, 0xffffff, 0.7);
      spr.ballLayer.add(ball);
    });
  }

  // ---- input ----

  _tubeAt(x, y) {
    for (let i = 0; i < this.tubeX.length; i++) {
      if (Math.abs(x - this.tubeX[i]) < TUBE_W / 2 + 8 && y > this.tubeY[i] - TUBE_H - 10 && y < this.tubeY[i] + 10) return i;
    }
    return null;
  }

  _onPointerDown(p) {
    if (this.state === STATE.START) { this._begin(); return; }
    if (this.state === STATE.END) { return; } // GameOverPanel's own TAP TO RETRY button handles restart; a blanket restart-on-any-tap here raced with clicking the CTA button
    if (this.state !== STATE.PLAYING) return;
    const idx = this._tubeAt(p.x, p.y);
    if (idx === null) return;

    if (this.selected === null) {
      if (this.tubes[idx].length === 0) return;
      this.selected = idx;
      this._highlight(idx, true);
      return;
    }
    if (this.selected === idx) {
      this._highlight(idx, false);
      this.selected = null;
      return;
    }
    const amount = this._pourAmount(this.selected, idx);
    const from = this.selected;
    this._highlight(from, false);
    this.selected = null;
    if (amount === 0) {
      this.cameras.main.shake(80, 0.004);
      return;
    }
    this._applyPour(from, idx);
    this._renderTube(from);
    this._renderTube(idx);
    Juice.ParticleBurst.create(this, this.tubeX[idx], this.tubeY[idx] - 20, { color: this.tubes[idx][this.tubes[idx].length - 1], count: 6 });
    this.moves -= 1;
    this.movesText.setText('Moves: ' + this.moves);
    this.movesText.setColor(this.moves <= 5 ? '#ff3355' : '#ffffff');
    this.game.registry.set('score', MOVE_LIMIT - this.moves);

    if (this._isSolved()) { this._end(true); return; }
    if (this.moves <= 0) { this._end(false); return; }
  }

  _highlight(idx, on) {
    const spr = this.tubeSprites[idx];
    if (on) {
      spr.highlight = Juice.GemSelectionHighlight.create(this, this.tubeX[idx] - TUBE_W / 2 - 3, this.tubeY[idx] - TUBE_H - 3, TUBE_W + 6, { radius: 10 });
    } else if (spr.highlight) {
      spr.highlight.destroy();
      spr.highlight = null;
    }
  }

  _isSolved() {
    return this.tubes.every((t) => t.length === 0 || (t.length === TUBE_CAPACITY && t.every((c) => c === t[0])));
  }

  _begin() {
    this.state = STATE.PLAYING;
    this.startText.setVisible(false);
    this.sessionStart = this.time.now;
    // Initialize sessionTime on Game instance for validation
    this.game.sessionTime = 0;
  }

  _end(won) {
    this.state = STATE.END;
    Juice.GameOverPanel.create(this, {
      won,
      score: MOVE_LIMIT - this.moves,
      target: 0,
      best: 0,
      onRetry: () => this.scene.restart(),
      onCTA: () => {
        if (typeof mraid !== 'undefined' && mraid.open) { mraid.open(CTA_LINK); }
        else { window.open(CTA_LINK, '_blank'); }
      }
    });
  }

  update(time, dt) {
    if (this.state !== STATE.PLAYING) return;
    const elapsed = time - this.sessionStart;
    const remain = Phaser.Math.Clamp(1 - elapsed / SESSION_MS, 0, 1);
    this.timerBarFg.width = 220 * remain;
    this.timerBarFg.fillColor = remain < 0.2 ? 0xff3355 : 0x33e6ff;
    if (elapsed >= SESSION_MS) { this._end(false); }

    this.game.sessionTime = (this.game.sessionTime || 0) + dt;
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
