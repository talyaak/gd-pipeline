// Juice Toolkit for HTML5 Playable Ads
// Reusable game-juice utilities extracted from proven-fun harnesses
// Use in single-file HTML5 games alongside Phaser 3

(function() {
  'use strict';

  // =========================================================================
  // SCREEN SHAKE & FLASH
  // =========================================================================
  class ScreenEffects {
    static shake(camera, duration = 100, intensity = 0.01) {
      if (camera && camera.shake) {
        camera.shake(duration, intensity);
      }
    }

    static flash(camera, duration = 100, r = 255, g = 255, b = 255, force = true) {
      if (camera && camera.flash) {
        camera.flash(duration, r, g, b, force);
      }
    }

    static deathFlash(camera) {
      this.shake(camera, 220, 0.02);
      this.flash(camera, 120, 255, 40, 80);
    }

    static hitPause(scene, duration = 50) {
      scene.time.delayedCall(duration, () => {});
    }
  }

  // =========================================================================
  // PARTICLE BURSTS (using window.ParticleEngine)
  // =========================================================================
  class ParticleBurst {
    static emitBurst(scene, x, y, options = {}) {
      const defaults = {
        count: 20,
        color: 0x33e6ff,
        speed: 100,
        startSize: 6,
        endSize: 2,
        life: 500,
        angle: 0,
        angleVariance: 360,
        gravity: 0,
      };
      const opts = { ...defaults, ...options };

      if (window.ParticleEngine && window.ParticleEngine.ParticleEmitter) {
        const emitter = new window.ParticleEngine.ParticleEmitter({
          x, y,
          maxParticles: opts.count,
          life: opts.life,
          speed: opts.speed,
          angle: opts.angle,
          angleVariance: opts.angleVariance,
          startSize: opts.startSize,
          endSize: opts.endSize,
          startColor: '#' + opts.color.toString(16).padStart(6, '0'),
          endColor: '#' + opts.color.toString(16).padStart(6, '0'),
          gravity: opts.gravity,
          startAlpha: 1,
          endAlpha: 0,
        });
        return emitter.burst(opts.count);
      }

      // Fallback: simple Phaser graphics particles
      const particles = [];
      for (let i = 0; i < opts.count; i++) {
        const angle = Math.random() * Math.PI * 2;
        const dist = 40 + Math.random() * 80;
        const p = scene.add.rectangle(x, y, opts.startSize, opts.startSize, opts.color);
        scene.tweens.add({
          targets: p,
          x: x + Math.cos(angle) * dist,
          y: y + Math.sin(angle) * dist,
          alpha: 0,
          scale: { from: 1, to: opts.endSize / opts.startSize },
          duration: opts.life + Math.random() * 200,
          ease: 'Cubic.easeOut',
          onComplete: () => p.destroy(),
        });
        particles.push(p);
      }
      return particles;
    }

    static pickupSparkle(scene, x, y, color = 0x33ffbb) {
      return this.emitBurst(scene, x, y, {
        count: 8,
        color,
        speed: 80,
        startSize: 4,
        endSize: 1,
        life: 350,
      });
    }

    static matchExplosion(scene, x, y, color = 0xffff00) {
      return this.emitBurst(scene, x, y, {
        count: 30,
        color,
        speed: 150,
        startSize: 8,
        endSize: 2,
        life: 600,
      });
    }
  }

  // =========================================================================
  // TRAIL EFFECT
  // =========================================================================
  class TrailEffect {
    constructor(scene, target, options = {}) {
      this.scene = scene;
      this.target = target;
      this.length = options.length || 6;
      this.historyLength = options.historyLength || 40;
      this.spacing = options.spacing || 6;
      this.baseAlpha = options.baseAlpha || 0.12;
      this.alphaStep = options.alphaStep || 0.018;
      this.color = options.color || 0x33e6ff;
      this.size = options.size || 34;

      this.history = [];
      this.trail = [];

      for (let i = 0; i < this.length; i++) {
        const alpha = this.baseAlpha - i * this.alphaStep;
        const g = scene.add.rectangle(target.x, target.y, this.size, this.size, this.color, Math.max(0, alpha));
        g.setDepth(target.depth !== undefined ? target.depth - 1 : 0);
        this.trail.push(g);
      }
    }

    update() {
      this.history.unshift({ x: this.target.x, y: this.target.y });
      if (this.history.length > this.historyLength) this.history.pop();

      this.trail.forEach((g, i) => {
        const h = this.history[i * this.spacing];
        if (h) { g.x = h.x; g.y = h.y; }
      });
    }

    setVisible(visible) {
      this.trail.forEach(g => g.setVisible(visible));
    }

    destroy() {
      this.trail.forEach(g => g.destroy());
      this.trail = [];
      this.history = [];
    }
  }

  // =========================================================================
  // PARALLAX / TUNNEL BACKGROUND
  // =========================================================================
  class ParallaxBackground {
    constructor(scene, options = {}) {
      this.scene = scene;
      this.graphics = scene.add.graphics();
      this.ringCount = options.ringCount || 7;
      this.ringPhase = 0;
      this.speed = options.speed || 0.12;
      this.colorHue = options.colorHue || 0.5; // HSV hue (0-1)
      this.colorSaturation = options.colorSaturation || 0.6;
      this.colorValue = options.colorValue || 0.9;
      this.maxScale = options.maxScale || 1.0;
      this.centerX = options.centerX || scene.cameras.main.width / 2;
      this.centerY = options.centerY || scene.cameras.main.height / 2;
    }

    update(dt, difficulty = 0) {
      this.ringPhase += dt * this.speed;
      this.graphics.clear();

      const hue = this.colorHue + difficulty * 0.35;
      const color = Phaser.Display.Color.HSVToRGB(hue, this.colorSaturation, this.colorValue);

      for (let i = 0; i < this.ringCount; i++) {
        const t = ((this.ringPhase + i * 40) % 280) / 280;
        const scale = t * this.maxScale;
        const alpha = 0.5 * (1 - t);
        this.graphics.lineStyle(2, Phaser.Display.Color.GetColor(color.r, color.g, color.b), alpha);
        const w = 60 + scale * 700;
        const h = 40 + scale * 420;
        this.graphics.strokeRect(this.centerX - w / 2, this.centerY - h / 2, w, h);
      }
    }

    destroy() {
      this.graphics.destroy();
    }
  }

  // =========================================================================
  // SCORE / MULTIPLIER UI
  // =========================================================================
  class ScoreDisplay {
    constructor(scene, options = {}) {
      this.scene = scene;
      this.score = 0;
      this.best = options.best || 0;
      this.multiplier = 1;
      this.fontFamily = options.fontFamily || 'monospace';

      // Main score
      this.scoreText = scene.add.text(
        options.scoreX || 16, options.scoreY || 12,
        'Score: 0',
        { fontFamily: this.fontFamily, fontSize: options.scoreSize || '22px', color: options.scoreColor || '#33e6ff' }
      );

      // Best score
      this.bestText = scene.add.text(
        options.bestX || 16, options.bestY || 38,
        'Best: ' + this.best,
        { fontFamily: this.fontFamily, fontSize: options.bestSize || '16px', color: options.bestColor || '#ff33cc' }
      );

      // Multiplier
      this.multText = scene.add.text(
        options.multX || 784, options.multY || 12,
        'x1',
        { fontFamily: this.fontFamily, fontSize: options.multSize || '22px', color: options.multColor || '#ffe14d' }
      ).setOrigin(1, 0);

      // Optional: pulse when low moves/time (for puzzle genres)
      this.warningThreshold = options.warningThreshold || 0;
      this.warningColor = options.warningColor || '#ff3355';
      this.normalColor = options.scoreColor || '#33e6ff';
    }

    addScore(points) {
      this.score += points * this.multiplier;
      this._updateScoreText();
    }

    setMultiplier(mult) {
      this.multiplier = mult;
      this.multText.setText('x' + this.multiplier);
    }

    setBest(best) {
      this.best = best;
      this.bestText.setText('Best: ' + this.best);
    }

    _updateScoreText() {
      this.scoreText.setText('Score: ' + Math.floor(this.score));
      if (this.warningThreshold > 0 && this.score <= this.warningThreshold) {
        this.scoreText.setColor(this.warningColor);
      } else {
        this.scoreText.setColor(this.normalColor);
      }
    }

    getScore() { return Math.floor(this.score); }
    getMultiplier() { return this.multiplier; }

    destroy() {
      this.scoreText.destroy();
      this.bestText.destroy();
      this.multText.destroy();
    }
  }

  // =========================================================================
  // GAME OVER / CTA END CARD
  // =========================================================================
  class EndCard {
    constructor(scene, options = {}) {
      this.scene = scene;
      this.width = options.width || 340;
      this.height = options.height || 220;
      this.bgColor = options.bgColor || 0x0a0a18;
      this.bgAlpha = options.bgAlpha || 0.92;
      this.borderColor = options.borderColor || 0x33e6ff;
      this.titleColor = options.titleColor || '#ff3377';
      this.scoreColor = options.scoreColor || '#33e6ff';
      this.bestColor = options.bestColor || '#ffe14d';
      this.ctaText = options.ctaText || 'PLAY FULL VERSION';
      this.ctaBgColor = options.ctaBgColor || '#ff3377';
      this.restartText = options.restartText || 'TAP TO RESTART';
      this.restartBgColor = options.restartBgColor || '#33e6ff';
      this.restartTextColor = options.restartTextColor || '#0a0a18';
      this.fontFamily = options.fontFamily || 'monospace';

      this.visible = false;
      this.elements = [];
      this.restartCallback = options.onRestart || null;
      this.ctaCallback = options.onCTA || null;

      this._create();
      this.setVisible(false);
    }

    _create() {
      const cx = this.scene.cameras.main.width / 2;
      const cy = this.scene.cameras.main.height / 2;

      this.panel = this.scene.add.rectangle(cx, cy, this.width, this.height, this.bgColor, this.bgAlpha)
        .setStrokeStyle(2, this.borderColor);
      this.elements.push(this.panel);

      this.title = this.scene.add.text(cx, cy - 75, 'GAME OVER', {
        fontFamily: this.fontFamily, fontSize: '32px', color: this.titleColor
      }).setOrigin(0.5);
      this.elements.push(this.title);

      this.scoreText = this.scene.add.text(cx, cy - 25, 'Score: 0', {
        fontFamily: this.fontFamily, fontSize: '20px', color: this.scoreColor
      }).setOrigin(0.5);
      this.elements.push(this.scoreText);

      this.bestText = this.scene.add.text(cx, cy + 3, 'Best: 0', {
        fontFamily: this.fontFamily, fontSize: '16px', color: this.bestColor
      }).setOrigin(0.5);
      this.elements.push(this.bestText);

      this.restartBtn = this.scene.add.text(cx, cy + 45, this.restartText, {
        fontFamily: this.fontFamily, fontSize: '16px', color: this.restartTextColor,
        backgroundColor: this.restartBgColor, padding: { x: 14, y: 8 }
      }).setOrigin(0.5).setInteractive({ useHandCursor: true });
      this.restartBtn.on('pointerdown', () => { if (this.restartCallback) this.restartCallback(); });
      this.elements.push(this.restartBtn);

      this.ctaBtn = this.scene.add.text(cx, cy + 90, this.ctaText, {
        fontFamily: this.fontFamily, fontSize: '16px', color: '#ffffff',
        backgroundColor: this.ctaBgColor, padding: { x: 14, y: 8 }
      }).setOrigin(0.5).setInteractive({ useHandCursor: true });
      this.ctaBtn.on('pointerdown', () => { 
        if (this.ctaCallback) this.ctaCallback();
        else if (typeof mraid !== 'undefined') mraid.open('https://example.com');
        else window.open('https://example.com', '_blank');
      });
      this.elements.push(this.ctaBtn);

      // Set depth so end card appears on top
      this.elements.forEach((el, i) => el.setDepth(100 + i));
    }

    show(score, best) {
      this.scoreText.setText('Score: ' + Math.floor(score));
      this.bestText.setText('Best: ' + best);
      this.setVisible(true);
      // Fade in animation
      this.elements.forEach(el => {
        el.setAlpha(0);
        this.scene.tweens.add({ targets: el, alpha: 1, duration: 250 });
      });
    }

    setVisible(visible) {
      this.visible = visible;
      this.elements.forEach(el => el.setVisible(visible));
    }

    isVisible() { return this.visible; }

    destroy() {
      this.elements.forEach(el => el.destroy());
      this.elements = [];
    }
  }

  // =========================================================================
  // SCORE POPUP (floating score numbers)
  // =========================================================================
  class ScorePopup {
    static show(scene, x, y, text, options = {}) {
      const color = options.color || '#33ffbb';
      const fontSize = options.fontSize || '16px';
      const fontFamily = options.fontFamily || 'monospace';
      const duration = options.duration || 600;
      const rise = options.rise || 40;

      const popup = scene.add.text(x, y, text, {
        fontFamily, fontSize, color
      }).setOrigin(0.5);

      scene.tweens.add({
        targets: popup,
        y: y - rise,
        alpha: 0,
        duration,
        onComplete: () => popup.destroy(),
      });

      return popup;
    }
  }

  // =========================================================================
  // LANE GUIDES (for lane-based games)
  // =========================================================================
  class LaneGuides {
    constructor(scene, lanesX, options = {}) {
      this.scene = scene;
      this.lanesX = lanesX;
      this.graphics = scene.add.graphics();
      this.color = options.color || 0x2a2a55;
      this.alpha = options.alpha || 0.5;
      this.thickness = options.thickness || 1;
      this.height = options.height || scene.cameras.main.height;
    }

    draw() {
      this.graphics.clear();
      this.graphics.lineStyle(this.thickness, this.color, this.alpha);
      this.lanesX.forEach(x => {
        this.graphics.lineBetween(x, 0, x, this.height);
      });
    }

    destroy() {
      this.graphics.destroy();
    }
  }

  // =========================================================================
  // MRAID GATING (standard pattern)
  // =========================================================================
  class MraidGate {
    static waitForReadyAndViewable(startGameplay) {
      if (typeof mraid === 'undefined') {
        startGameplay();
        return;
      }

      const state = mraid.getState();
      if (state === 'loading') {
        mraid.addEventListener('ready', () => {
          if (mraid.isViewable()) {
            startGameplay();
          } else {
            mraid.addEventListener('viewableChange', (viewable) => {
              if (viewable) startGameplay();
            });
          }
        });
      } else if (mraid.isViewable()) {
        startGameplay();
      } else {
        mraid.addEventListener('viewableChange', (viewable) => {
          if (viewable) startGameplay();
        });
      }
    }
  }

  // =========================================================================
  // AUDIO CONTEXT HELPER (muted until first interaction)
  // =========================================================================
  class AudioHelper {
    constructor() {
      this.ctx = null;
      this.gain = null;
      this.unlocked = false;
    }

    init() {
      if (this.ctx) return this.ctx;
      this.ctx = new (window.AudioContext || window.webkitAudioContext)();
      this.gain = this.ctx.createGain();
      this.gain.connect(this.ctx.destination);
      this.gain.gain.value = 0; // Start muted
      return this.ctx;
    }

    unlockOnInteraction() {
      if (this.unlocked) return;
      const unlock = () => {
        if (this.ctx && this.ctx.state === 'suspended') {
          this.ctx.resume().then(() => {
            this.gain.gain.value = 1;
            this.unlocked = true;
          });
        } else if (this.ctx) {
          this.gain.gain.value = 1;
          this.unlocked = true;
        }
        document.removeEventListener('pointerdown', unlock);
        document.removeEventListener('keyup', unlock);
      };
      document.addEventListener('pointerdown', unlock, { once: true });
      document.addEventListener('keyup', unlock, { once: true });
    }

    playTone(frequency, duration, type = 'sine', volume = 0.1) {
      if (!this.ctx || !this.unlocked) return;
      const osc = this.ctx.createOscillator();
      const gain = this.ctx.createGain();
      osc.connect(gain);
      gain.connect(this.ctx.destination);
      osc.frequency.value = frequency;
      osc.type = type;
      gain.gain.value = volume;
      osc.start();
      osc.stop(this.ctx.currentTime + duration / 1000);
    }
  }

  // Expose globally
  window.Juice = {
    ScreenEffects,
    ParticleBurst,
    TrailEffect,
    ParallaxBackground,
    ScoreDisplay,
    EndCard,
    ScorePopup,
    LaneGuides,
    MraidGate,
    AudioHelper,
  };
})();