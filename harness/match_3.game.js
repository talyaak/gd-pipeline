// Hand-built match-3 harness. Every value here is hardcoded and tuned by
// actually playing the game -- same approach as harness/endless_runner.game.js.
// This genre has a confirmed real bug in the old LLM-generated pipeline:
// click-to-swap input never registered at all. This harness resolves board
// position from raw pointer coordinates (not per-gem hit areas) specifically
// to avoid repeating that failure mode. Do not add a config layer here; pull
// constants out only after this is confirmed fun by actually playing it.
//
// Uses Juice toolkit (pipeline/vendor/juice.js) for shared juice utilities.

const COLS = 7;
const ROWS = 7;
const CELL = 46;
const BOARD_X = 400 - (COLS * CELL) / 2;
const BOARD_Y = 108;
const COLORS = [0x33e6ff, 0xff33cc, 0xffe14d, 0x33ff88, 0xff9933, 0xaa66ff];
const TARGET_SCORE = 1200;
const START_MOVES = 20;

const STATE = { BOOT: 'boot', START: 'start', IDLE: 'idle', BUSY: 'busy', END: 'end' };

function cellX(c) { return BOARD_X + c * CELL + CELL / 2; }
function cellY(r) { return BOARD_Y + r * CELL + CELL / 2; }

class PlayScene extends Phaser.Scene {
  constructor() {
    super('PlayScene');
  }

  create() {
    this.state = STATE.START;
    this.score = 0;
    this.best = Number(localStorage.getItem('match3_best') || 0);
    this.moves = START_MOVES;
    this.selected = null; // {c, r}
    this.dragStart = null;
    this.board = []; // board[r][c] = { color, sprite } or null
    this.comboDepth = 0;
    this.selectionHighlight = null;

    this.cameras.main.setBackgroundColor('#0a0a18');

    this.bgG = this.add.graphics();
    this.hue = 0.55;

    // Board background via Juice
    Juice.BoardBackground.create(this, {
      x: BOARD_X - 8,
      y: BOARD_Y - 8,
      width: COLS * CELL + 16,
      height: ROWS * CELL + 16,
      bgColor: 0x14142a,
      bgAlpha: 0.9,
      borderColor: 0x33e6ff,
      borderAlpha: 0.4,
      borderWidth: 2,
      radius: 10
    });

    this.particlesLayer = this.add.container(0, 0);
    this.popupsLayer = this.add.container(0, 0);

    this.scoreText = this.add.text(16, 12, 'Score: 0', { fontFamily: 'monospace', fontSize: '20px', color: '#33e6ff' });
    this.bestText = this.add.text(16, 36, 'Best: ' + this.best, { fontFamily: 'monospace', fontSize: '14px', color: '#ff33cc' });
    this.targetText = this.add.text(784, 12, 'Target: ' + TARGET_SCORE, { fontFamily: 'monospace', fontSize: '16px', color: '#ffe14d' }).setOrigin(1, 0);

    // Moves counter via Juice
    this.movesCounter = Juice.MovesCounter.create(this, {
      moves: this.moves,
      x: 784,
      y: 36,
      warnThreshold: 5,
      normalColor: '#ffffff',
      warnColor: '#ff3355',
      fontFamily: 'monospace',
      fontSize: '18px'
    });

    this.startText = this.add.text(400, 60, 'TAP TO START  •  swap adjacent gems to match 3+', {
      fontFamily: 'monospace', fontSize: '16px', color: '#ffffff', align: 'center',
    }).setOrigin(0.5).setVisible(false);
    this.tweens.add({ targets: this.startText, alpha: 0.4, duration: 700, yoyo: true, repeat: -1 });

    this._buildBoard();
    this._renderBoardStatic();
    this._playIntroDemo();

    this.input.on('pointerdown', (p) => this._onPointerDown(p));
    this.input.on('pointerup', (p) => this._onPointerUp(p));

    window.__GAME__ = this.game;
    this.game.registry.set('score', 0);
  }

  // ---- intro demo: ~1s auto-play of the core swap so a first-time player
  // sees the mechanic before being asked to act. Tapping at any point skips
  // straight to "begin" -- see _begin()'s demoActive handling. ----

  _playIntroDemo() {
    this.demoActive = true;
    this.introTimers = [];
    this.introBanner = Juice.IntroBanner.create(this, { label: 'SWAP GEMS TO MATCH 3+' });
    const a = { c: 2, r: 3 }, b = { c: 3, r: 3 };
    this.introHighlight = Juice.GemSelectionHighlight.create(this, BOARD_X + a.c * CELL, BOARD_Y + a.r * CELL, CELL);
    this.introTimers.push(this.time.delayedCall(300, () => {
      if (!this.demoActive) return;
      this.introHighlight.destroy();
      this.introHighlight = null;
      Juice.SwapAnimation.create(this, this.board[a.r][a.c].sprite, this.board[b.r][b.c].sprite, {
        duration: 220,
        onComplete: () => {
          if (!this.demoActive) return;
          this._swapCells(a, b);
          this.introTimers.push(this.time.delayedCall(350, () => {
            if (!this.demoActive) return;
            Juice.SwapAnimation.create(this, this.board[a.r][a.c].sprite, this.board[b.r][b.c].sprite, {
              duration: 220,
              onComplete: () => {
                if (!this.demoActive) return;
                this._swapCells(a, b);
                this._endIntroDemo();
              }
            });
          }));
        }
      });
    }));
  }

  _endIntroDemo() {
    this.demoActive = false;
    if (this.introBanner) { this.introBanner.destroy(); this.introBanner = null; }
    if (this.introHighlight) { this.introHighlight.destroy(); this.introHighlight = null; }
    this.startText.setVisible(true);
  }

  _resyncSpritePositions() {
    for (let r = 0; r < ROWS; r++) {
      for (let c = 0; c < COLS; c++) {
        const cell = this.board[r][c];
        if (cell && cell.sprite) { cell.sprite.x = cellX(c); cell.sprite.y = cellY(r); }
      }
    }
  }

  // ---- board setup ----

  _buildBoard() {
    // Build with no pre-existing matches so the opening board never
    // auto-resolves before the player makes a move.
    for (let r = 0; r < ROWS; r++) {
      this.board[r] = [];
      for (let c = 0; c < COLS; c++) {
        let color;
        do {
          color = COLORS[Phaser.Math.Between(0, COLORS.length - 1)];
        } while (this._wouldMatchAt(r, c, color));
        this.board[r][c] = { color, sprite: null };
      }
    }
  }

  _wouldMatchAt(r, c, color) {
    if (c >= 2 && this.board[r][c - 1] && this.board[r][c - 1].color === color && this.board[r][c - 2] && this.board[r][c - 2].color === color) return true;
    if (r >= 2 && this.board[r - 1][c] && this.board[r - 1][c].color === color && this.board[r - 2][c] && this.board[r - 2][c].color === color) return true;
    return false;
  }

  _renderBoardStatic() {
    for (let r = 0; r < ROWS; r++) {
      for (let c = 0; c < COLS; c++) {
        this._spawnGemSprite(r, c, cellY(r));
      }
    }
  }

  _spawnGemSprite(r, c, startY) {
    const cell = this.board[r][c];
    const x = cellX(c);
    const y = cellY(r);
    const container = this.add.container(x, startY);
    const glow = this.add.circle(0, 0, 17, cell.color, 0.25).setScale(1.3);
    const body = this.add.circle(0, 0, 16, cell.color);
    body.setStrokeStyle(2, 0xffffff, 0.7);
    const shine = this.add.circle(-5, -5, 5, 0xffffff, 0.5);
    container.add([glow, body, shine]);
    cell.sprite = container;
    if (startY !== y) {
      this.tweens.add({ targets: container, y, duration: 260, ease: 'Bounce.easeOut' });
    }
    return container;
  }

  // ---- input ----

  _screenToCell(x, y) {
    const c = Math.floor((x - BOARD_X) / CELL);
    const r = Math.floor((y - BOARD_Y) / CELL);
    if (c < 0 || c >= COLS || r < 0 || r >= ROWS) return null;
    return { c, r };
  }

  _onPointerDown(p) {
    if (this.state === STATE.START) {
      this._begin();
      return;
    }
    if (this.state === STATE.END) {
      this.scene.restart();
      return;
    }
    if (this.state !== STATE.IDLE) return;
    const cell = this._screenToCell(p.x, p.y);
    if (!cell) return;
    this.dragStart = cell;
    this._select(cell);
  }

  _onPointerUp(p) {
    if (this.state !== STATE.IDLE || !this.dragStart) { this.dragStart = null; return; }
    const cell = this._screenToCell(p.x, p.y);
    const start = this.dragStart;
    this.dragStart = null;
    if (!cell) return;
    if (cell.c === start.c && cell.r === start.r) return; // plain tap, selection already shown
    if (this._isAdjacent(start, cell)) {
      this._attemptSwap(start, cell);
    } else {
      this._select(cell);
    }
  }

  _isAdjacent(a, b) {
    const dc = Math.abs(a.c - b.c);
    const dr = Math.abs(a.r - b.r);
    return (dc === 1 && dr === 0) || (dc === 0 && dr === 1);
  }

  _select(cell) {
    if (this.selected && this._isAdjacent(this.selected, cell)) {
      this._attemptSwap(this.selected, cell);
      return;
    }
    this.selected = cell;
    if (this.selectionHighlight) {
      this.selectionHighlight.setPosition(BOARD_X + cell.c * CELL, BOARD_Y + cell.r * CELL);
    } else {
      this.selectionHighlight = Juice.GemSelectionHighlight.create(this, BOARD_X + cell.c * CELL, BOARD_Y + cell.r * CELL, CELL);
    }
  }

  _clearSelection() {
    this.selected = null;
    if (this.selectionHighlight) {
      this.selectionHighlight.destroy();
      this.selectionHighlight = null;
    }
  }

  // ---- swapping ----

  _attemptSwap(a, b) {
    this._clearSelection();
    this.state = STATE.BUSY;
    this._swapCells(a, b);
    Juice.SwapAnimation.create(this, this.board[a.r][a.c].sprite, this.board[b.r][b.c].sprite, {
      duration: 150,
      onComplete: () => {
        const matches = this._findAllMatches();
        if (matches.length === 0) {
          // invalid swap: revert with a shake
          this._swapCells(a, b);
          Juice.SwapAnimation.create(this, this.board[a.r][a.c].sprite, this.board[b.r][b.c].sprite, {
            duration: 160,
            isRevert: true,
            shakeCamera: true,
            onComplete: () => { this.state = STATE.IDLE; }
          });
          return;
        }
        this.moves -= 1;
        this.movesCounter.setMoves(this.moves);
        this.comboDepth = 0;
        this._resolveMatches();
      }
    });
  }

  _swapCells(a, b) {
    const tmp = this.board[a.r][a.c];
    this.board[a.r][a.c] = this.board[b.r][b.c];
    this.board[b.r][b.c] = tmp;
  }

  // ---- matching ----

  _findAllMatches() {
    const marked = new Set();
    for (let r = 0; r < ROWS; r++) {
      let runStart = 0;
      for (let c = 1; c <= COLS; c++) {
        const same = c < COLS && this.board[r][c] && this.board[r][runStart] && this.board[r][c].color === this.board[r][runStart].color;
        if (!same) {
          if (c - runStart >= 3) for (let k = runStart; k < c; k++) marked.add(r + ',' + k);
          runStart = c;
        }
      }
    }
    for (let c = 0; c < COLS; c++) {
      let runStart = 0;
      for (let r = 1; r <= ROWS; r++) {
        const same = r < ROWS && this.board[r] && this.board[r][c] && this.board[runStart][c] && this.board[r][c].color === this.board[runStart][c].color;
        if (!same) {
          if (r - runStart >= 3) for (let k = runStart; k < r; k++) marked.add(k + ',' + c);
          runStart = r;
        }
      }
    }
    return Array.from(marked).map((s) => { const [r, c] = s.split(',').map(Number); return { r, c }; });
  }

  _resolveMatches() {
    const cascade = Juice.CascadeSystem.create(this, this.board, {
      cols: COLS,
      rows: ROWS,
      cellSize: CELL,
      colors: COLORS,
      getCellCenter: (c, r) => [cellX(c), cellY(r)],
      onMatch: (matches, comboDepth) => {
        const mult = comboDepth;
        const points = matches.length * 10 * mult;
        this.score += points;
        this.scoreText.setText('Score: ' + this.score);
        this.game.registry.set('score', this.score);
        return points;
      },
      onCascadeEnd: () => this._afterCascade(),
      onGemGone: (r, c) => { this.board[r][c] = null; }
    });
    cascade.resolve();
  }

  _afterCascade() {
    if (this.moves <= 0 && this.score < TARGET_SCORE) {
      this._end(false);
      return;
    }
    if (this.score >= TARGET_SCORE) {
      this._end(true);
      return;
    }
    this.state = STATE.IDLE;
  }

  // ---- end states ----

  _end(won) {
    this.state = STATE.END;
    this.best = Math.max(this.best, this.score);
    localStorage.setItem('match3_best', String(this.best));

    Juice.GameOverPanel.create(this, {
      won,
      score: this.score,
      target: TARGET_SCORE,
      best: this.best,
      onRetry: () => this.scene.restart(),
      onCTA: () => {}
    });
  }

  _begin() {
    if (this.demoActive) {
      this.introTimers.forEach((t) => t.remove(false));
      this.introTimers = [];
      this._resyncSpritePositions();
      this._endIntroDemo();
    }
    this.state = STATE.IDLE;
    this.startText.setVisible(false);
  }

  update(time, dt) {
    // ambient background hue drift, echoes endless_runner's tunnel treatment
    this.hue += dt * 0.00002;
    if (this.hue > 1) this.hue -= 1;
    const c1 = Phaser.Display.Color.HSVToRGB(this.hue, 0.5, 0.12);
    this.bgG.clear();
    this.bgG.fillStyle(Phaser.Display.Color.GetColor(c1.r, c1.g, c1.b), 1);
    this.bgG.fillRect(0, 0, 800, 450);
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