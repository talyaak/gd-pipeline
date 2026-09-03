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

const TUBE_W = 54;
const TUBE_H = TUBE_CAPACITY * 34 + 20;
const TUBE_Y = 380;
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
    this.bgG.fillRect(0, 0, 800, 450);

    this._generatePuzzle();

    const totalTubes = this.tubes.length;
    const spacing = 700 / (totalTubes - 1);
    this.tubeX = this.tubes.map((_, i) => 60 + i * spacing + 10);

    this.tubeLayer = this.add.container(0, 0);
    this.tubes.forEach((_, i) => this._buildTubeSprite(i));
    this._renderAllTubes();

    this.movesText = this.add.text(16, 12, 'Moves: ' + this.moves, { fontFamily: 'monospace', fontSize: '18px', color: '#ffffff' });
    this.timerBarBg = this.add.rectangle(650, 20, 260, 10, 0x14142a).setStrokeStyle(1, 0x33e6ff, 0.5);
    this.timerBarFg = this.add.rectangle(520, 20, 260, 10, 0x33e6ff).setOrigin(0, 0.5);

    this.startText = this.add.text(400, 55, 'TAP TWO TUBES TO POUR  •  SORT EACH COLOR', {
      fontFamily: 'monospace', fontSize: '15px', color: '#ffffff', align: 'center',
    }).setOrigin(0.5);
    this.tweens.add({ targets: this.startText, alpha: 0.4, duration: 700, yoyo: true, repeat: -1 });

    const introBanner = Juice.IntroBanner.create(this, { label: 'POUR MATCHING COLORS TOGETHER', y: 44 });
    const introHint = Juice.TapHint.create(this, this.tubeX[0], TUBE_Y - 40, { color: COLORS[0], radius: 30 });
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
    const x = this.tubeX[i];
    const g = this.add.graphics();
    g.lineStyle(3, 0x33e6ff, 0.5);
    g.strokeRoundedRect(x - TUBE_W / 2, TUBE_Y - TUBE_H, TUBE_W, TUBE_H, 10);
    const ballLayer = this.add.container(0, 0);
    this.tubeSprites[i] = { g, ballLayer, highlight: null };
  }

  _renderAllTubes() {
    this.tubes.forEach((_, i) => this._renderTube(i));
  }

  _renderTube(i) {
    const spr = this.tubeSprites[i];
    spr.ballLayer.removeAll(true);
    const x = this.tubeX[i];
    this.tubes[i].forEach((color, slot) => {
      const y = TUBE_Y - 12 - slot * 34 - 17;
      const ball = this.add.circle(x, y, BALL_R, color).setStrokeStyle(2, 0xffffff, 0.7);
      spr.ballLayer.add(ball);
    });
  }

  // ---- input ----

  _tubeAt(x, y) {
    for (let i = 0; i < this.tubeX.length; i++) {
      if (Math.abs(x - this.tubeX[i]) < TUBE_W / 2 + 8 && y > TUBE_Y - TUBE_H - 10 && y < TUBE_Y + 10) return i;
    }
    return null;
  }

  _onPointerDown(p) {
    if (this.state === STATE.START) { this._begin(); return; }
    if (this.state === STATE.END) { this.scene.restart(); return; }
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
    Juice.ParticleBurst.create(this, this.tubeX[idx], TUBE_Y - 20, { color: this.tubes[idx][this.tubes[idx].length - 1], count: 6 });
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
      spr.highlight = Juice.GemSelectionHighlight.create(this, this.tubeX[idx] - TUBE_W / 2 - 3, TUBE_Y - TUBE_H - 3, TUBE_W + 6, { radius: 10 });
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
  }

  _end(won) {
    this.state = STATE.END;
    Juice.GameOverPanel.create(this, {
      won,
      score: MOVE_LIMIT - this.moves,
      target: 0,
      best: 0,
      onRetry: () => this.scene.restart(),
      onCTA: () => {}
    });
  }

  update(time) {
    if (this.state !== STATE.PLAYING) return;
    const elapsed = time - this.sessionStart;
    const remain = Phaser.Math.Clamp(1 - elapsed / SESSION_MS, 0, 1);
    this.timerBarFg.width = 260 * remain;
    this.timerBarFg.fillColor = remain < 0.2 ? 0xff3355 : 0x33e6ff;
    if (elapsed >= SESSION_MS) { this._end(false); }
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
