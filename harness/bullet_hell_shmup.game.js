// Hand-built bullet hell shmup harness. Every value here is hardcoded and tuned by
// actually playing the game -- same approach as harness/endless_runner.game.js.
// This genre is STRATEGY.md priority #8. Do not add a config layer here; pull
// constants out only after this is confirmed fun by actually playing it.
//
// Uses Juice toolkit (pipeline/vendor/juice.js) for shared juice utilities.

const W = 450, H = 800;
const CTA_LINK = "https://example.com/game";
const PLAYER_X = W / 2, PLAYER_Y = H - 80;
const PLAYER_SPEED = 320;           // px/sec normal
const PLAYER_FOCUS_SPEED = 160;     // px/sec with Shift held
const HITBOX_RADIUS = 4;            // visible hitbox radius
const AUTO_FIRE_INTERVAL = 120;     // ms between shots
const FOCUS_FIRE_INTERVAL = 80;     // ms between shots in focus mode
const MAX_POWER_LEVEL = 5;
const BOMB_COUNT = 3;
const WIN_TIME_MS = 180000;         // 3 minutes survival = win
const INITIAL_SPAWN_INTERVAL = 2000; // ms between spawns at session start
const SPAWN_INTERVAL_MIN = 600;      // ms between spawns at max difficulty
const WAVE_INTERVAL_MS = 15000;      // ms of survival per wave increment

const STATE = { BOOT: 'boot', START: 'start', PLAYING: 'playing', DEAD: 'dead', WIN: 'win' };

// Enemy types
const ENEMY_TYPES = {
  BASIC: { hp: 1, color: 0xff3355, score: 10, size: 18, firePattern: 'radial', fireInterval: 2500 },
  SHOOTER: { hp: 2, color: 0xff9933, score: 25, size: 22, firePattern: 'aimed', fireInterval: 1800 },
  TANK: { hp: 4, color: 0xaa66ff, score: 50, size: 28, firePattern: 'spiral', fireInterval: 1200 },
};

class PlayScene extends Phaser.Scene {
  constructor() {
    super('PlayScene');
  }

  create() {
    this.state = STATE.START;
    this.game.state = STATE.START;
    this.sessionTime = 0;
    this.score = 0;
    this.best = Number(localStorage.getItem('shmup_best') || 0);
    this.powerLevel = 1;
    this.bombs = BOMB_COUNT;
    this.enemies = [];
    this.enemyBullets = [];
    this.playerBullets = [];
    this.powerUps = [];
    this.popups = [];
    this.spawnTimer = 0;
    this.spawnInterval = INITIAL_SPAWN_INTERVAL;
    this.wave = 1;
    this.combo = 1;
    this.comboTimer = 0;
    this.lastHitTime = -Infinity;
    this.focusMode = false;

    this.cameras.main.setBackgroundColor('#0a0a18');

    // Tunnel background for speed sensation
    this.tunnelG = this.add.graphics();
    this.ringPhase = 0;
    this.hue = 0.55;

    // Player ship (triangle pointing up)
    this.player = this.add.container(PLAYER_X, PLAYER_Y);
    const shipBody = this.add.triangle(0, 0, 0, -18, -14, 12, 14, 12, 0x33e6ff);
    shipBody.setStrokeStyle(2, 0xffffff, 0.9);
    this.player.add(shipBody);

    // Visible hitbox (small circle at center)
    this.hitbox = this.add.circle(0, 0, HITBOX_RADIUS, 0xff3377, 0.8);
    this.hitbox.setStrokeStyle(1.5, 0xffffff, 0.9);
    this.player.add(this.hitbox);

    // Hitbox glow pulse when focused
    this.hitboxGlow = this.add.circle(0, 0, HITBOX_RADIUS + 6, 0x33e6ff, 0.15).setScale(0);
    this.player.add(this.hitboxGlow);

    // Trail emitter
    this.trailTimer = null;

    // UI
    this.scoreText = this.add.text(16, 12, 'Score: 0', { fontFamily: 'monospace', fontSize: '20px', color: '#33e6ff' });
    this.bestText = this.add.text(16, 36, 'Best: ' + this.best, { fontFamily: 'monospace', fontSize: '14px', color: '#ff33cc' });
    this.timeText = this.add.text(W - 16, 12, 'Time: 0:00', { fontFamily: 'monospace', fontSize: '16px', color: '#ffe14d' }).setOrigin(1, 0);
    this.powerText = this.add.text(W - 16, 36, 'Power: 1', { fontFamily: 'monospace', fontSize: '14px', color: '#33ff88' }).setOrigin(1, 0);
    this.bombText = this.add.text(16, H - 30, 'Bombs: ' + '◆'.repeat(this.bombs), { fontFamily: 'monospace', fontSize: '16px', color: '#ff33cc' });

    // Combo display
    this.comboText = this.add.text(W / 2, 60, '', { fontFamily: 'monospace', fontSize: '18px', color: '#ffe14d' }).setOrigin(0.5).setVisible(false);

    // Intro
    this.startText = this.add.text(W / 2, 300, 'ARROWS to move  •  HOLD SHIFT for focus\nTAP / SPACE to bomb (3)', {
      fontFamily: 'monospace', fontSize: '16px', color: '#ffffff', align: 'center'
    }).setOrigin(0.5);
    this.tweens.add({ targets: this.startText, alpha: 0.4, duration: 700, yoyo: true, repeat: -1 });

    const introBanner = Juice.IntroBanner.create(this, { label: 'DODGE BULLETS • AUTO-FIRE • SURVIVE 3:00' });
    const introHint = Juice.TapHint.create(this, PLAYER_X, PLAYER_Y, { color: 0x33e6ff });
    this.time.delayedCall(2500, () => { introBanner.destroy(); introHint.destroy(); });

    // Input
    this.cursors = this.input.keyboard.createCursorKeys();
    this.shiftKey = this.input.keyboard.addKey(Phaser.Input.Keyboard.KeyCodes.SHIFT);
    this.spaceKey = this.input.keyboard.addKey(Phaser.Input.Keyboard.KeyCodes.SPACE);
    this.zKey = this.input.keyboard.addKey(Phaser.Input.Keyboard.KeyCodes.Z);

    // Touch: drag to move, tap with two fingers or hold for bomb
    this._touchStartTime = 0;
    this._touchStartPos = { x: 0, y: 0 };
    this.input.on('pointerdown', (p) => {
      this._touchStartTime = this.time.now;
      this._touchStartPos = { x: p.x, y: p.y };
    });
    this.input.on('pointermove', (p) => {
      if (!p.isDown) return;
      if (this.state !== STATE.PLAYING) return;
      this.player.x = Phaser.Math.Clamp(p.x, 20, W - 20);
      this.player.y = Phaser.Math.Clamp(p.y, H * 0.3, H - 20);
    });
    this.input.on('pointerup', (p) => {
      if (this.state !== STATE.PLAYING) return;
      const heldMs = this.time.now - this._touchStartTime;
      const moved = Math.hypot(p.x - this._touchStartPos.x, p.y - this._touchStartPos.y);
      if (heldMs > 400 && moved < 30) this._useBomb(); // long press = bomb
    });

    window.__GAME__ = this.game;
    this.game.registry.set('score', 0);
  }

  _startGame() {
    this.state = STATE.PLAYING;
    this.game.state = STATE.PLAYING;
    this.startText.setVisible(false);
    this.sessionStartTime = this.time.now;
    this.sessionTime = 0;
    this.spawnTimer = -1500; // grace period before first spawn
    this._startTrail();
  }

  _startTrail() {
    this.trailTimer = this.time.addEvent({
      delay: 30,
      callback: () => {
        if (this.state !== STATE.PLAYING) { this.trailTimer?.remove(); return; }
        const p = this.add.circle(this.player.x, this.player.y, 4, 0x33e6ff, 0.4);
        this.tweens.add({ targets: p, alpha: 0, scale: 0, duration: 200, ease: 'Cubic.easeOut', onComplete: () => p.destroy() });
      },
      loop: true
    });
  }

  _useBomb() {
    if (this.bombs <= 0) return;
    this.bombs--;
    this.bombText.setText('Bombs: ' + '◆'.repeat(this.bombs));

    // Screen clear effect
    Juice.ScreenShake.create(this, { intensity: 0.015, duration: 300 });
    Juice.CameraFlash.create(this, { color: 0xffffff, duration: 200 });

    // Destroy all enemy bullets with particles
    this.enemyBullets.forEach(b => {
      Juice.ParticleBurst.create(this, b.x, b.y, { color: 0x33e6ff, count: 6, speed: 100 });
      b.destroy();
    });
    this.enemyBullets = [];

    // Damage all enemies on screen
    this.enemies.forEach(e => {
      e.hp = 0;
      this._killEnemy(e);
    });
  }

  _firePlayer() {
    const fireInterval = this.focusMode ? FOCUS_FIRE_INTERVAL : AUTO_FIRE_INTERVAL;
    if (this.time.now - (this.lastFireTime || 0) < fireInterval) return;
    this.lastFireTime = this.time.now;

    const bulletSpeed = -550; // upward
    const spread = this.powerLevel >= 3 ? 0.15 : 0;
    const count = this.powerLevel >= 5 ? 3 : (this.powerLevel >= 2 ? 2 : 1);

    for (let i = 0; i < count; i++) {
      const angle = (i - (count - 1) / 2) * spread;
      const bullet = this.add.rectangle(this.player.x, this.player.y - 20, 4, 14, 0x33e6ff);
      bullet.setStrokeStyle(1, 0xffffff, 0.8);
      bullet.angle = -90;
      bullet.vx = Math.sin(angle) * 50;
      bullet.vy = bulletSpeed;
      this.playerBullets.push(bullet);
    }

    // Muzzle flash
    Juice.ParticleBurst.create(this, this.player.x, this.player.y - 20, { color: 0x33e6ff, count: 3, speed: 50, size: 3 });
  }

  _spawnEnemy() {
    const types = Object.keys(ENEMY_TYPES);
    const typeKey = types[Phaser.Math.Between(0, types.length - 1)];
    const type = ENEMY_TYPES[typeKey];

    const x = Phaser.Math.Between(40, W - 40);
    const y = -30;
    const container = this.add.container(x, y);

    const body = this.add.polygon(0, 0, this._getPolygonPoints(type.size), type.color);
    body.setStrokeStyle(2, 0xffffff, 0.7);
    container.add(body);

    // Core glow
    const core = this.add.circle(0, 0, type.size * 0.3, type.color, 0.3);
    container.add(core);

    container.hp = type.hp;
    container.maxHp = type.hp;
    container.type = typeKey;
    container.typeData = type;
    container.vy = 40 + this.wave * 8;
    container.vx = (Math.random() - 0.5) * 30;
    container.fireTimer = 0;
    container.wobblePhase = Math.random() * Math.PI * 2;

    this.enemies.push(container);
  }

  _getPolygonPoints(size) {
    // Triangle for basic, square for shooter, hexagon for tank
    // Simplified: return triangle points for all, size varies
    return [0, -size, -size * 0.866, size * 0.5, size * 0.866, size * 0.5];
  }

  _enemyFire(enemy) {
    const type = enemy.typeData;
    const patterns = {
      radial: () => {
        const count = 8 + this.wave;
        for (let i = 0; i < count; i++) {
          const angle = (i / count) * Math.PI * 2;
          this._createEnemyBullet(enemy.x, enemy.y, Math.cos(angle) * 180, Math.sin(angle) * 180, type.color);
        }
      },
      aimed: () => {
        const dx = this.player.x - enemy.x;
        const dy = this.player.y - enemy.y;
        const dist = Math.hypot(dx, dy) || 1;
        const count = 1 + Math.min(this.wave, 3);
        for (let i = 0; i < count; i++) {
          const spread = (i - (count - 1) / 2) * 0.2;
          const angle = Math.atan2(dy, dx) + spread;
          this._createEnemyBullet(enemy.x, enemy.y, Math.cos(angle) * 200, Math.sin(angle) * 200, type.color);
        }
      },
      spiral: () => {
        const baseAngle = (enemy.fireTimer / 100) * Math.PI * 2;
        const count = 3;
        for (let i = 0; i < count; i++) {
          const angle = baseAngle + (i / count) * Math.PI * 2;
          this._createEnemyBullet(enemy.x, enemy.y, Math.cos(angle) * 160, Math.sin(angle) * 160, type.color);
        }
      }
    };
    patterns[type.firePattern]?.();
  }

  _createEnemyBullet(x, y, vx, vy, color) {
    const bullet = this.add.circle(x, y, 5, color);
    bullet.setStrokeStyle(1, 0xffffff, 0.6);
    bullet.vx = vx;
    bullet.vy = vy;
    this.enemyBullets.push(bullet);
  }

  _killEnemy(enemy) {
    // Score with combo
    const points = enemy.typeData.score * this.combo;
    this.score += points;
    this.scoreText.setText('Score: ' + this.score);
    this.game.registry.set('score', this.score);

    Juice.ScorePopup.create(this, enemy.x, enemy.y, '+' + points, { color: '#33ffbb', size: '16px' });
    Juice.ParticleBurst.create(this, enemy.x, enemy.y, { color: enemy.typeData.color, count: 12, speed: 150 });
    Juice.ComboText.create(this, enemy.x, enemy.y - 30, this.combo, { color: '#ffe14d' });

    // Combo system
    this.combo = Math.min(this.combo + 1, 8);
    this.comboTimer = this.time.now + 3000;
    this._updateComboDisplay();

    // Chance to drop power-up
    if (Math.random() < 0.15 && this.powerLevel < MAX_POWER_LEVEL) {
      const pu = this.add.container(enemy.x, enemy.y);
      const star = this.add.star(0, 0, 5, 8, 4, 0x33ff88);
      star.setStrokeStyle(1.5, 0xffffff, 0.9);
      pu.add(star);
      pu.vy = 60;
      pu.type = 'power';
      this.powerUps.push(pu);
    }

    // Chance to drop bomb piece (very rare)
    if (Math.random() < 0.05 && this.bombs < BOMB_COUNT) {
      const pu = this.add.container(enemy.x, enemy.y);
      const bombIcon = this.add.text(0, 0, '◆', { fontFamily: 'monospace', fontSize: '18px', color: '#ff33cc' }).setOrigin(0.5);
      pu.add(bombIcon);
      pu.vy = 60;
      pu.type = 'bomb';
      this.powerUps.push(pu);
    }

    enemy.destroy();
  }

  _collectPowerUp(pu) {
    if (pu.type === 'power') {
      this.powerLevel = Math.min(this.powerLevel + 1, MAX_POWER_LEVEL);
      this.powerText.setText('Power: ' + this.powerLevel);
      Juice.CameraFlash.create(this, { color: 0x33ff88, duration: 100 });
      Juice.ParticleBurst.create(this, pu.x, pu.y, { color: 0x33ff88, count: 15, speed: 180 });
    } else if (pu.type === 'bomb') {
      this.bombs = Math.min(this.bombs + 1, BOMB_COUNT);
      this.bombText.setText('Bombs: ' + '◆'.repeat(this.bombs));
      Juice.CameraFlash.create(this, { color: 0xff33cc, duration: 100 });
    }
    pu.destroy();
  }

  _updateComboDisplay() {
    if (this.combo > 1) {
      this.comboText.setText(this.combo + 'x COMBO').setVisible(true);
      this.comboText.setScale(1);
      this.tweens.add({ targets: this.comboText, scale: 1.2, duration: 100, yoyo: true });
    } else {
      this.comboText.setVisible(false);
    }
  }

  _playerHit() {
    if (this.state !== STATE.PLAYING) return;
    if (this.time.now - this.lastHitTime < 1500) return; // invincibility frames

    this.lastHitTime = this.time.now;
    this.combo = 1;
    this._updateComboDisplay();
    this.powerLevel = Math.max(1, this.powerLevel - 1);
    this.powerText.setText('Power: ' + this.powerLevel);

    Juice.ScreenShake.create(this, { intensity: 0.01, duration: 200 });
    Juice.CameraFlash.create(this, { color: 0xff3355, duration: 150 });

    // Hit effect on player
    this.player.setAlpha(0.3);
    this.tweens.add({ targets: this.player, alpha: 1, duration: 1500, ease: 'Sine.easeInOut' });

    // Death particles
    for (let i = 0; i < 20; i++) {
      const p = this.add.rectangle(this.player.x, this.player.y, 6, 6, 0x33e6ff);
      const angle = Math.random() * Math.PI * 2;
      const dist = 80 + Math.random() * 100;
      this.tweens.add({
        targets: p, x: this.player.x + Math.cos(angle) * dist, y: this.player.y + Math.sin(angle) * dist,
        alpha: 0, duration: 500 + Math.random() * 300, ease: 'Cubic.easeOut', onComplete: () => p.destroy()
      });
    }

    // Game over after hit (one-hit death for bullet hell feel, but with 3 lives via power level drop)
    // Actually, let's do: 3 hits = game over. Track hits via a life counter.
    if (!this.lives) this.lives = 3;
    this.lives--;
    if (this.lives <= 0) {
      this._die();
    }
  }

  _die() {
    if (this.state === STATE.DEAD) return;
    this.state = STATE.DEAD;
    this.game.state = STATE.DEAD;

    this.trailTimer?.remove();

    this.best = Math.max(this.best, this.score);
    localStorage.setItem('shmup_best', String(this.best));

    Juice.GameOverPanel.create(this, {
      won: false,
      score: this.score,
      target: 0,
      best: this.best,
      onRetry: () => this.scene.restart(),
      onCTA: () => {
        if (typeof mraid !== 'undefined' && mraid.open) { mraid.open(CTA_LINK); }
        else { window.open(CTA_LINK, '_blank'); }
      }
    });
  }

  _win() {
    if (this.state === STATE.WIN) return;
    this.state = STATE.WIN;
    this.game.state = STATE.WIN;

    this.trailTimer?.remove();

    this.best = Math.max(this.best, this.score);
    localStorage.setItem('shmup_best', String(this.best));

    Juice.GameOverPanel.create(this, {
      won: true,
      score: this.score,
      target: 0,
      best: this.best,
      onRetry: () => this.scene.restart(),
      onCTA: () => {
        if (typeof mraid !== 'undefined' && mraid.open) { mraid.open(CTA_LINK); }
        else { window.open(CTA_LINK, '_blank'); }
      }
    });
  }

  update(time, dt) {
    if (this.state === STATE.START) {
      if (Phaser.Input.Keyboard.JustDown(this.spaceKey) || Phaser.Input.Keyboard.JustDown(this.zKey) ||
          this.input.activePointer.justDown) {
        this._startGame();
      }
      return;
    }

    if (this.state === STATE.DEAD || this.state === STATE.WIN) {
      if (Phaser.Input.Keyboard.JustDown(this.spaceKey) || this.input.activePointer.justDown) {
        this.scene.restart();
      }
      return;
    }

    // Session time
    this.sessionTime = time - this.sessionStartTime;
    const minutes = Math.floor(this.sessionTime / 60000);
    const seconds = Math.floor((this.sessionTime % 60000) / 1000);
    this.timeText.setText('Time: ' + minutes + ':' + seconds.toString().padStart(2, '0'));

    // Win check
    if (this.sessionTime >= WIN_TIME_MS) {
      this._win();
      return;
    }

    // Difficulty scaling
    const difficulty = Phaser.Math.Clamp(this.sessionTime / 120000, 0, 1);
    this.spawnInterval = Phaser.Math.Linear(INITIAL_SPAWN_INTERVAL, SPAWN_INTERVAL_MIN, difficulty);
    this.wave = Math.floor(this.sessionTime / WAVE_INTERVAL_MS) + 1;

    // Focus mode
    this.focusMode = this.shiftKey.isDown || (this.input.activePointer.isDown && this.input.pointer1.isDown && this.input.pointer2?.isDown);
    const speed = this.focusMode ? PLAYER_FOCUS_SPEED : PLAYER_SPEED;

    // Hitbox visual
    this.hitbox.setAlpha(this.focusMode ? 1 : 0.6);
    this.hitboxGlow.setScale(this.focusMode ? 1 : 0);
    if (this.focusMode) {
      this.tweens.add({ targets: this.hitboxGlow, scale: 1.5, alpha: 0, duration: 400, ease: 'Cubic.easeOut', onComplete: () => { this.hitboxGlow.setScale(0); this.hitboxGlow.setAlpha(0.15); } });
    }

    // Keyboard movement
    if (this.cursors.left.isDown) this.player.x -= (speed * dt) / 1000;
    if (this.cursors.right.isDown) this.player.x += (speed * dt) / 1000;
    if (this.cursors.up.isDown) this.player.y -= (speed * dt) / 1000;
    if (this.cursors.down.isDown) this.player.y += (speed * dt) / 1000;

    // Clamp to screen (with margin)
    this.player.x = Phaser.Math.Clamp(this.player.x, 20, W - 20);
    this.player.y = Phaser.Math.Clamp(this.player.y, H * 0.3, H - 20);

    // Bomb key
    if (Phaser.Input.Keyboard.JustDown(this.spaceKey) || Phaser.Input.Keyboard.JustDown(this.zKey)) {
      this._useBomb();
    }

    // Auto-fire
    this._firePlayer();

    // Tunnel background
    this.ringPhase += dt * 0.1;
    this.tunnelG.clear();
    for (let i = 0; i < 6; i++) {
      const t = ((this.ringPhase + i * 50) % 300) / 300;
      const scale = t;
      const alpha = 0.4 * (1 - t);
      const hue = (this.hue + difficulty * 0.3) % 1;
      const color = Phaser.Display.Color.HSVToRGB(hue, 0.6, 0.8);
      this.tunnelG.lineStyle(2, Phaser.Display.Color.GetColor(color.r, color.g, color.b), alpha);
      const w = 50 + scale * 400, h = 30 + scale * 800;
      this.tunnelG.strokeRect(W / 2 - w / 2, 200 - h / 2, w, h);
    }

    // Spawn enemies
    this.spawnTimer += dt;
    if (this.spawnTimer >= this.spawnInterval) {
      this.spawnTimer = 0;
      // Spawn 1-3 enemies per wave
      const count = 1 + Math.floor(this.wave / 3);
      for (let i = 0; i < count; i++) {
        this.time.delayedCall(i * 300, () => this._spawnEnemy());
      }
    }

    // Update enemies
    for (let i = this.enemies.length - 1; i >= 0; i--) {
      const e = this.enemies[i];
      e.y += (e.vy * dt) / 1000;
      e.x += (e.vx * dt) / 1000;
      e.wobblePhase += dt * 0.005;
      e.x += Math.sin(e.wobblePhase) * 0.5;

      // Fire
      e.fireTimer += dt;
      if (e.fireTimer >= e.typeData.fireInterval) {
        e.fireTimer = 0;
        this._enemyFire(e);
      }

      // Remove if off screen bottom
      if (e.y > H + 50) {
        e.destroy();
        this.enemies.splice(i, 1);
      }
    }

    // Update player bullets
    for (let i = this.playerBullets.length - 1; i >= 0; i--) {
      const b = this.playerBullets[i];
      b.x += (b.vx * dt) / 1000;
      b.y += (b.vy * dt) / 1000;
      if (b.y < -20) { b.destroy(); this.playerBullets.splice(i, 1); continue; }

      // Collision with enemies
      for (let j = this.enemies.length - 1; j >= 0; j--) {
        const e = this.enemies[j];
        const dx = b.x - e.x;
        const dy = b.y - e.y;
        if (dx * dx + dy * dy < (e.typeData.size + 10) ** 2) {
          b.destroy();
          this.playerBullets.splice(i, 1);
          e.hp--;
          // Hit flash
          const flash = this.add.circle(e.x, e.y, e.typeData.size * 1.5, 0xffffff, 0.5);
          this.tweens.add({ targets: flash, alpha: 0, scale: 2, duration: 80, onComplete: () => flash.destroy() });
          if (e.hp <= 0) {
            this._killEnemy(e);
            this.enemies.splice(j, 1);
          }
          break;
        }
      }
    }

    // Update enemy bullets
    for (let i = this.enemyBullets.length - 1; i >= 0; i--) {
      const b = this.enemyBullets[i];
      b.x += (b.vx * dt) / 1000;
      b.y += (b.vy * dt) / 1000;
      if (b.x < -20 || b.x > W + 20 || b.y < -20 || b.y > H + 20) {
        b.destroy(); this.enemyBullets.splice(i, 1); continue;
      }

      // Collision with player hitbox
      const dx = b.x - this.player.x;
      const dy = b.y - this.player.y;
      if (dx * dx + dy * dy < (HITBOX_RADIUS + 5) ** 2) {
        b.destroy();
        this.enemyBullets.splice(i, 1);
        this._playerHit();
      }
    }

    // Update power-ups
    for (let i = this.powerUps.length - 1; i >= 0; i--) {
      const pu = this.powerUps[i];
      pu.y += (pu.vy * dt) / 1000;
      pu.rotation += dt * 0.003;
      if (pu.y > H + 30) { pu.destroy(); this.powerUps.splice(i, 1); continue; }

      const dx = pu.x - this.player.x;
      const dy = pu.y - this.player.y;
      if (dx * dx + dy * dy < 30 ** 2) {
        this._collectPowerUp(pu);
        this.powerUps.splice(i, 1);
      }
    }

    // Combo decay
    if (this.combo > 1 && this.time.now > this.comboTimer) {
      this.combo = 1;
      this._updateComboDisplay();
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