// Procedural Particle Library for HTML5 Playable Ads
// Provides lightweight particle effects without external dependencies
// Designed to work alongside Phaser 3 in single-file HTML5 games

(function() {
  'use strict';

  // Simple 2D vector class
  class Vector2 {
    constructor(x = 0, y = 0) {
      this.x = x;
      this.y = y;
    }
    
    add(v) {
      return new Vector2(this.x + v.x, this.y + v.y);
    }
    
    subtract(v) {
      return new Vector2(this.x - v.x, this.y - v.y);
    }
    
    multiply(scalar) {
      return new Vector2(this.x * scalar, this.y * scalar);
    }
    
    divide(scalar) {
      return new Vector2(this.x / scalar, this.y / scalar);
    }
    
    length() {
      return Math.sqrt(this.x * this.x + this.y * this.y);
    }
    
    normalize() {
      const len = this.length();
      if (len > 0) {
        return new Vector2(this.x / len, this.y / len);
      }
      return new Vector2(0, 0);
    }
    
    clone() {
      return new Vector2(this.x, this.y);
    }
  }

  // Particle class representing a single particle
  class Particle {
    constructor(x, y, options = {}) {
      this.position = new Vector2(x, y);
      this.velocity = new Vector2(
        options.vx || 0,
        options.vy || 0
      );
      this.acceleration = new Vector2(
        options.ax || 0,
        options.ay || 0
      );
      
      this.life = options.life || 1000; // milliseconds
      this.maxLife = this.life;
      this.age = 0;
      
      this.startSize = options.startSize || 5;
      this.endSize = options.endSize || this.startSize;
      this.size = this.startSize;
      
      this.startColor = options.startColor || '#ffffff';
      this.endColor = options.endColor || this.startColor;
      this.color = this.startColor;
      
      this.startAlpha = options.startAlpha !== undefined ? options.startAlpha : 1;
      this.endAlpha = options.endAlpha !== undefined ? options.endAlpha : this.startAlpha;
      this.alpha = this.startAlpha;
      
      this.rotation = options.rotation || 0;
      this.rotationSpeed = options.rotationSpeed || 0;
      
      this.active = true;
    }
    
    update(deltaTime) {
      if (!this.active) return;
      
      // Update physics
      this.velocity = this.velocity.add(this.acceleration.multiply(deltaTime));
      this.position = this.position.add(this.velocity.multiply(deltaTime));
      
      // Update life
      this.age += deltaTime;
      if (this.age >= this.life) {
        this.active = false;
        return;
      }
      
      // Update size (linear interpolation)
      const lifeRatio = this.age / this.life;
      this.size = this.startSize + (this.endSize - this.startSize) * lifeRatio;
      
      // Update alpha (linear interpolation)
      this.alpha = this.startAlpha + (this.endAlpha - this.startAlpha) * lifeRatio;
      
      // Update rotation
      this.rotation += this.rotationSpeed * deltaTime;
    }
  }

  // ParticleEmitter class manages a group of particles
  class ParticleEmitter {
    constructor(options = {}) {
      this.position = new Vector2(
        options.x || 0,
        options.y || 0
      );
      
      this.particles = [];
      this.maxParticles = options.maxParticles || 100;
      this.particleCount = 0;
      
      // Emission properties
      this.emitRate = options.emitRate || 0; // particles per second
      this.emitTimer = 0;
      this.isEmitting = options.isEmitting !== undefined ? options.isEmitting : true;
      
      // Particle properties (defaults)
      this.options = {
        life: options.life || 1000,
        speed: options.speed || 50,
        angle: options.angle || 0, // degrees
        angleVariance: options.angleVariance || 0,
        startSize: options.startSize || 5,
        endSize: options.endSize || 5,
        startColor: options.startColor || '#ffffff',
        endColor: options.endColor || options.startColor,
        startAlpha: options.startAlpha !== undefined ? options.startAlpha : 1,
        endAlpha: options.endAlpha !== undefined ? options.endAlpha : options.startAlpha,
        gravity: options.gravity || 0,
        wind: options.wind || 0,
        rotationSpeed: options.rotationSpeed || 0,
        sizeVariance: options.sizeVariance || 0
      };
      
      // Callbacks
      this.onParticleUpdate = options.onParticleUpdate || null;
      this.onParticleExpire = options.onParticleExpire || null;
    }
    
    // Emit a single particle
    emit() {
      if (this.particleCount >= this.maxParticles) return null;
      
      // Calculate emission angle with variance
      const angleRad = (this.options.angle + 
                       (Math.random() * 2 - 1) * this.options.angleVariance) * 
                       Math.PI / 180;
      
      // Calculate speed with variance
      const speed = this.options.speed + 
                   (Math.random() * 2 - 1) * this.options.speed * 0.1; // 10% variance
      
      const vx = Math.cos(angleRad) * speed;
      const vy = Math.sin(angleRad) * speed;
      
      // Size with variance
      const sizeVariance = this.options.sizeVariance || 0;
      const startSize = this.options.startSize + 
                      (Math.random() * 2 - 1) * sizeVariance;
      
      const particle = new Particle(
        this.position.x,
        this.position.y,
        {
          vx: vx,
          vy: vy,
          ay: this.options.gravity, // gravity affects Y acceleration
          life: this.options.life,
          startSize: startSize,
          endSize: this.options.endSize + 
                 (Math.random() * 2 - 1) * sizeVariance,
          startColor: this.options.startColor,
          endColor: this.options.endColor,
          startAlpha: this.options.startAlpha,
          endAlpha: this.options.endAlpha,
          rotationSpeed: this.options.rotationSpeed
        }
      );
      
      this.particles.push(particle);
      this.particleCount++;
      
      return particle;
    }
    
    // Update all particles
    update(deltaTime) {
      // Update emitter timer for continuous emission
      if (this.isEmitting && this.emitRate > 0) {
        this.emitTimer += deltaTime;
        const emitInterval = 1000 / this.emitRate; // ms per particle
        
        while (this.emitTimer >= emitInterval && 
               this.particleCount < this.maxParticles) {
          this.emit();
          this.emitTimer -= emitInterval;
        }
      }
      
      // Update all particles
      for (let i = this.particles.length - 1; i >= 0; i--) {
        const particle = this.particles[i];
        particle.update(deltaTime);
        
        // Call update callback if provided
        if (this.onParticleUpdate) {
          this.onParticleUpdate(particle, i);
        }
        
        // Remove expired particles
        if (!particle.active) {
          if (this.onParticleExpire) {
            this.onParticleExpire(particle, i);
          }
          this.particles.splice(i, 1);
          this.particleCount--;
        }
      }
    }
    
    // Emit a burst of particles
    burst(count) {
      const emitted = [];
      for (let i = 0; i < count && this.particleCount < this.maxParticles; i++) {
        const particle = this.emit();
        if (particle) emitted.push(particle);
      }
      return emitted;
    }
    
    // Clear all particles
    clear() {
      this.particles = [];
      this.particleCount = 0;
    }
    
    // Get active particle count
    getCount() {
      return this.particleCount;
    }
  }

  // Expose globally
  window.ParticleEngine = {
    Vector2: Vector2,
    Particle: Particle,
    ParticleEmitter: ParticleEmitter
  };
  
  // Also expose directly for convenience
  window.Vector2 = Vector2;
  window.Particle = Particle;
  window.ParticleEmitter = ParticleEmitter;
  
})();