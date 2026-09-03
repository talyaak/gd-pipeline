// Juice Toolkit — shared "game feel" utilities for gd-gpt harnesses
// Import in harness HTML: <script src="../pipeline/vendor/juice.js"></script>
// All classes expose static factory methods (create) for one-line usage.
// Style: no build step, no dependencies beyond Phaser 3 global.

/**
 * ScreenShake — one-call camera shake.
 *   Juice.ScreenShake.create(scene, { intensity: 0.008, duration: 160 })
 */
class ScreenShake {
  static create(scene, { intensity = 0.006, duration = 120 } = {}) {
    scene.cameras.main.shake(duration, intensity);
  }
}

/**
 * CameraFlash — white/colored flash on camera.
 *   Juice.CameraFlash.create(scene, { color: 0x33e6ff, duration: 150 })
 */
class CameraFlash {
  static create(scene, { color = 0xffffff, duration = 150 } = {}) {
    scene.cameras.main.flash(duration, (color >> 16) & 0xff, (color >> 8) & 0xff, color & 0xff, false);
  }
}

/**
 * ParticleBurst — radial particle burst at a point.
 *   Juice.ParticleBurst.create(scene, x, y, { color: 0x33e6ff, count: 12, speed: 180 })
 */
class ParticleBurst {
  static create(scene, x, y, { color = 0xffffff, count = 12, speed = 180, size = 4 } = {}) {
    for (let i = 0; i < count; i++) {
      const p = scene.add.circle(x, y, size, color);
      const angle = (i / count) * Math.PI * 2 + (Math.random() - 0.5) * 0.5;
      const dist = speed * 0.5 + Math.random() * speed * 0.5;
      scene.tweens.add({
        targets: p,
        x: x + Math.cos(angle) * dist,
        y: y + Math.sin(angle) * dist,
        alpha: 0,
        scale: 0.5,
        duration: 300 + Math.random() * 200,
        ease: 'Cubic.easeOut',
        onComplete: () => p.destroy()
      });
    }
  }
}

/**
 * ScorePopup — floating "+N" text that rises and fades.
 *   Juice.ScorePopup.create(scene, x, y, '+120', { color: '#33ffbb', size: '18px' })
 */
class ScorePopup {
  static create(scene, x, y, text, { color = '#ffffff', size = '16px', fontFamily = 'monospace', rise = 30, duration = 500 } = {}) {
    const t = scene.add.text(x, y, text, { fontFamily, fontSize: size, color }).setOrigin(0.5);
    scene.tweens.add({
      targets: t,
      y: y - rise,
      alpha: 0,
      duration,
      ease: 'Cubic.easeOut',
      onComplete: () => t.destroy()
    });
  }
}

/**
 * TrailEmitter — leaves a fading trail behind a moving object.
 *   Juice.TrailEmitter.create(scene, sprite, { color: 0x33e6ff, interval: 40, life: 200 })
 */
class TrailEmitter {
  static create(scene, target, { color = 0xffffff, interval = 50, life = 250, size = 6, alpha = 0.6 } = {}) {
    const timer = scene.time.addEvent({
      delay: interval,
      callback: () => {
        if (!target.active) { timer.destroy(); return; }
        const p = scene.add.circle(target.x, target.y, size, color, alpha);
        scene.tweens.add({
          targets: p,
          alpha: 0,
          scale: 0,
          duration: life,
          ease: 'Cubic.easeOut',
          onComplete: () => p.destroy()
        });
      },
      loop: true
    });
    return timer;
  }
}

/**
 * ParallaxBackground — multi-layer scrolling background.
 *   Juice.ParallaxBackground.create(scene, layers)
 *   layers: [{ color: 0x1a1a2e, speed: 0.1, y: 0, height: 450 }, ...]
 */
class ParallaxBackground {
  static create(scene, layers) {
    const gfx = layers.map((layer, i) => {
      const g = scene.add.graphics();
      g.fillStyle(layer.color, layer.alpha ?? 1);
      g.fillRect(0, layer.y, scene.scale.width, layer.height);
      g.setScrollFactor(layer.speed, layer.speed);
      return g;
    });
    return { destroy: () => gfx.forEach(g => g.destroy()) };
  }
}

/**
 * TunnelBackground — endless-runner style color-drifting tunnel.
 *   Juice.TunnelBackground.create(scene, { baseHue: 0.55, speed: 0.00002 })
 */
class TunnelBackground {
  static create(scene, { baseHue = 0.55, speed = 0.00002, saturation = 0.5, lightness = 0.12 } = {}) {
    let hue = baseHue;
    const g = scene.add.graphics();
    scene.events.on('update', (_, dt) => {
      hue += dt * speed;
      if (hue > 1) hue -= 1;
      const c = Phaser.Display.Color.HSVToRGB(hue, saturation, lightness);
      g.clear();
      g.fillStyle(Phaser.Display.Color.GetColor(c.r, c.g, c.b), 1);
      g.fillRect(0, 0, scene.scale.width, scene.scale.height);
    });
    return { destroy: () => { scene.events.off('update'); g.destroy(); } };
  }
}

/**
 * UIScoreDisplay — score + best + target row.
 *   Juice.UIScoreDisplay.create(scene, { score: 0, best: 0, target: 1000 })
 */
class UIScoreDisplay {
  static create(scene, { score = 0, best = 0, target = 0, x = 16, y = 12 } = {}) {
    const scoreText = scene.add.text(x, y, 'Score: ' + score, { fontFamily: 'monospace', fontSize: '20px', color: '#33e6ff' });
    const bestText = scene.add.text(x, y + 24, 'Best: ' + best, { fontFamily: 'monospace', fontSize: '14px', color: '#ff33cc' });
    const targetText = target ? scene.add.text(scene.scale.width - 16, y, 'Target: ' + target, { fontFamily: 'monospace', fontSize: '16px', color: '#ffe14d' }).setOrigin(1, 0) : null;
    return {
      setScore(v) { score = v; scoreText.setText('Score: ' + score); },
      setBest(v) { best = v; bestText.setText('Best: ' + best); },
      destroy: () => { scoreText.destroy(); bestText.destroy(); if (targetText) targetText.destroy(); }
    };
  }
}

/**
 * GameOverPanel — win/lose end card with retry + CTA.
 *   Juice.GameOverPanel.create(scene, { won: true, score: 1200, target: 1000, best: 1500 })
 */
class GameOverPanel {
  static create(scene, { won = true, score = 0, target = 0, best = 0, onRetry, onCTA } = {}) {
    scene.cameras.main.flash(150, won ? 51 : 255, won ? 230 : 51, won ? 255 : 119, false);
    const panel = scene.add.rectangle(400, 225, 360, 220, 0x0a0a18, 0.94).setStrokeStyle(2, won ? 0x33e6ff : 0xff3377);
    const title = scene.add.text(400, 155, won ? 'LEVEL CLEAR!' : 'GAME OVER', { fontFamily: 'monospace', fontSize: '28px', color: won ? '#33ffbb' : '#ff3377' }).setOrigin(0.5);
    const scoreT = scene.add.text(400, 200, 'Score: ' + score + (target ? ' / ' + target : ''), { fontFamily: 'monospace', fontSize: '18px', color: '#33e6ff' }).setOrigin(0.5);
    const bestT = scene.add.text(400, 226, 'Best: ' + best, { fontFamily: 'monospace', fontSize: '14px', color: '#ffe14d' }).setOrigin(0.5);
    const retry = scene.add.text(400, 268, 'TAP TO RETRY', { fontFamily: 'monospace', fontSize: '16px', color: '#0a0a18', backgroundColor: '#33e6ff', padding: { x: 14, y: 8 } }).setOrigin(0.5).setInteractive({ useHandCursor: true });
    const cta = scene.add.text(400, 312, 'PLAY FULL VERSION', { fontFamily: 'monospace', fontSize: '16px', color: '#ffffff', backgroundColor: '#ff3377', padding: { x: 14, y: 8 } }).setOrigin(0.5).setInteractive({ useHandCursor: true });

    scene.tweens.add({ targets: [panel, title, scoreT, bestT, retry, cta], alpha: { from: 0, to: 1 }, duration: 250 });

    retry.on('pointerdown', () => onRetry?.());
    cta.on('pointerdown', () => onCTA?.());

    if (won) {
      for (let i = 0; i < 20; i++) {
        const p = scene.add.rectangle(400, 120, 6, 10, Phaser.Display.Color.HSVToRGB(i / 20, 0.8, 0.9));
        const angle = -Math.PI / 2 + (Math.random() - 0.5) * 2.2;
        const dist = 120 + Math.random() * 160;
        scene.tweens.add({
          targets: p,
          x: 400 + Math.cos(angle) * dist,
          y: 120 + Math.sin(angle) * dist + 120,
          rotation: Math.random() * 6,
          alpha: 0,
          duration: 900 + Math.random() * 400,
          ease: 'Cubic.easeOut',
          onComplete: () => p.destroy()
        });
      }
    }
    return { destroy: () => [panel, title, scoreT, bestT, retry, cta].forEach(o => o.destroy()) };
  }
}

/**
 * ComboText — "2x COMBO", "3x COMBO" popups with scaling animation.
 *   Juice.ComboText.create(scene, x, y, multiplier)
 */
class ComboText {
  static create(scene, x, y, multiplier, { color = '#ffe14d', size = '22px', fontFamily = 'monospace' } = {}) {
    const t = scene.add.text(x, y, multiplier + 'x COMBO', { fontFamily, fontSize: size, color }).setOrigin(0.5).setScale(0.5);
    scene.tweens.add({
      targets: t,
      scale: 1.1,
      duration: 160,
      yoyo: true,
      onComplete: () => scene.tweens.add({
        targets: t,
        alpha: 0,
        y: y - 30,
        duration: 300,
        onComplete: () => t.destroy()
      })
    });
  }
}

/**
 * GemSelectionHighlight — highlights a grid cell with a rounded outline.
 *   Juice.GemSelectionHighlight.create(scene, x, y, cellSize)
 */
class GemSelectionHighlight {
  static create(scene, x, y, cellSize, { color = 0xffffff, alpha = 0.9, thickness = 3, inset = 3, radius = 8 } = {}) {
    const g = scene.add.graphics();
    g.lineStyle(thickness, color, alpha);
    g.strokeRoundedRect(x + inset, y + inset, cellSize - inset * 2, cellSize - inset * 2, radius);
    return {
      setPosition(x, y) { g.clear(); g.lineStyle(thickness, color, alpha); g.strokeRoundedRect(x + inset, y + inset, cellSize - inset * 2, cellSize - inset * 2, radius); },
      clear() { g.clear(); },
      destroy() { g.destroy(); }
    };
  }
}

/**
 * SwapAnimation — animates two objects swapping positions.
 *   Juice.SwapAnimation.create(scene, objA, objB, { duration: 150, onComplete, isRevert: false })
 */
class SwapAnimation {
  static create(scene, objA, objB, { duration = 150, onComplete, isRevert = false, ease = 'Cubic.easeOut', shakeCamera = false } = {}) {
    const xa = objA.x, ya = objA.y;
    const xb = objB.x, yb = objB.y;
    let remaining = 2;
    const done = () => { if (--remaining === 0 && onComplete) onComplete(); };
    scene.tweens.add({ targets: objA, x: xb, y: yb, duration, ease, onComplete: done });
    scene.tweens.add({ targets: objB, x: xa, y: ya, duration, ease, onComplete: done });
    if (isRevert && shakeCamera) scene.cameras.main.shake(120, 0.006);
  }
}

/**
 * CascadeSystem — match-3 gravity/cascade engine.
 *   const cascade = Juice.CascadeSystem.create(scene, board, { cols, rows, cellSize, colors, onMatch, onCascadeEnd })
 *   board: 2D array board[r][c] = { color, sprite } or null
 *   onMatch(matches, comboDepth) -> points
 *   onCascadeEnd() called when no more matches
 */
class CascadeSystem {
  static create(scene, board, { cols, rows, cellSize, colors, getCellCenter, onMatch, onCascadeEnd, onGemGone } = {}) {
    const findAllMatches = () => {
      const marked = new Set();
      for (let r = 0; r < rows; r++) {
        let runStart = 0;
        for (let c = 1; c <= cols; c++) {
          const same = c < cols && board[r][c] && board[r][runStart] && board[r][c].color === board[r][runStart].color;
          if (!same) {
            if (c - runStart >= 3) for (let k = runStart; k < c; k++) marked.add(r + ',' + k);
            runStart = c;
          }
        }
      }
      for (let c = 0; c < cols; c++) {
        let runStart = 0;
        for (let r = 1; r <= rows; r++) {
          const same = r < rows && board[r] && board[r][c] && board[runStart][c] && board[r][c].color === board[runStart][c].color;
          if (!same) {
            if (r - runStart >= 3) for (let k = runStart; k < r; k++) marked.add(k + ',' + c);
            runStart = r;
          }
        }
      }
      return Array.from(marked).map(s => { const [r, c] = s.split(',').map(Number); return { r, c }; });
    };

    const applyGravity = () => {
      let anyFell = false;
      const falls = [];
      for (let c = 0; c < cols; c++) {
        let writeR = rows - 1;
        for (let r = rows - 1; r >= 0; r--) {
          if (board[r][c]) {
            if (writeR !== r) {
              board[writeR][c] = board[r][c];
              board[r][c] = null;
              falls.push({ cell: board[writeR][c], toR: writeR, c });
              anyFell = true;
            }
            writeR -= 1;
          }
        }
        for (let r = writeR; r >= 0; r--) {
          const color = colors[Phaser.Math.Between(0, colors.length - 1)];
          board[r][c] = { color, sprite: null };
          anyFell = true;
        }
      }
      falls.forEach(({ cell, toR, c }) => {
        const [x, y] = getCellCenter(c, toR);
        scene.tweens.add({ targets: cell.sprite, y, duration: 220, ease: 'Cubic.easeIn' });
      });
      return anyFell;
    };

    let comboDepth = 0;
    const resolve = () => {
      const matches = findAllMatches();
      if (matches.length === 0) {
        onCascadeEnd?.();
        return;
      }
      comboDepth++;
      const points = onMatch?.(matches, comboDepth) ?? (matches.length * 10 * comboDepth);
      const cx = matches.reduce((s, m) => s + getCellCenter(m.c, m.r)[0], 0) / matches.length;
      const cy = matches.reduce((s, m) => s + getCellCenter(m.c, m.r)[1], 0) / matches.length;
      if (comboDepth > 1) Juice.ComboText.create(scene, cx, cy, comboDepth);
      Juice.ScorePopup.create(scene, cx, cy, '+' + points);

      let pending = matches.length;
      const onOneGone = () => { if (--pending === 0) { applyGravity(); scene.time.delayedCall(260, resolve); } };
      matches.forEach(({ r, c }) => {
        const cell = board[r][c];
        const [sx, sy] = getCellCenter(c, r);
        Juice.ParticleBurst.create(scene, sx, sy, { color: cell.color, count: 8 });
        scene.tweens.add({
          targets: cell.sprite,
          scale: 1.35,
          duration: 90,
          yoyo: true,
          ease: 'Sine.easeOut',
          onComplete: () => scene.tweens.add({
            targets: cell.sprite,
            scale: 0,
            alpha: 0,
            duration: 160,
            ease: 'Cubic.easeIn',
            onComplete: () => { cell.sprite.destroy(); onGemGone?.(r, c); onOneGone(); }
          })
        });
        board[r][c] = null;
      });
    };

    return { resolve, get comboDepth() { return comboDepth; } };
  }
}

/**
 * BoardBackground — styled board container with border.
 *   Juice.BoardBackground.create(scene, { x, y, width, height, bgColor, borderColor, radius })
 */
class BoardBackground {
  static create(scene, { x, y, width, height, bgColor = 0x14142a, bgAlpha = 0.9, borderColor = 0x33e6ff, borderAlpha = 0.4, borderWidth = 2, radius = 10 } = {}) {
    const g = scene.add.graphics();
    g.fillStyle(bgColor, bgAlpha);
    g.fillRoundedRect(x, y, width, height, radius);
    g.lineStyle(borderWidth, borderColor, borderAlpha);
    g.strokeRoundedRect(x, y, width, height, radius);
    return g;
  }
}

/**
 * MovesCounter — move counter with low-moves warning color.
 *   Juice.MovesCounter.create(scene, { moves: 20, x, y, warnThreshold: 5 })
 */
class MovesCounter {
  static create(scene, { moves = 20, x, y, warnThreshold = 5, normalColor = '#ffffff', warnColor = '#ff3355', fontFamily = 'monospace', fontSize = '18px' } = {}) {
    const text = scene.add.text(x, y, 'Moves: ' + moves, { fontFamily, fontSize, color: normalColor }).setOrigin(1, 0);
    return {
      setMoves(m) { moves = m; text.setText('Moves: ' + moves); text.setColor(moves <= warnThreshold ? warnColor : normalColor); },
      get moves() { return moves; },
      destroy: () => text.destroy()
    };
  }
}

// namespace export
window.Juice = {
  ScreenShake,
  CameraFlash,
  ParticleBurst,
  ScorePopup,
  TrailEmitter,
  ParallaxBackground,
  TunnelBackground,
  UIScoreDisplay,
  GameOverPanel,
  ComboText,
  GemSelectionHighlight,
  SwapAnimation,
  CascadeSystem,
  BoardBackground,
  MovesCounter
};