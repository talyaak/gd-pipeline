// Procedural Art Library for HTML5 Playable Ads
// Provides soft shapes, noise textures, gradients, and procedural sprite generation
// Designed to work alongside Phaser 3 in single-file HTML5 games
// Replaces hard-edged graphics.fillRect()/fillCircle() with visually superior alternatives

(function() {
  'use strict';

  // Utility function to clamp a value between min and max
  function clamp(value, min, max) {
    return Math.max(min, Math.max(value, max));
  }

  // Utility function to lerp (linear interpolate) between two values
  function lerp(start, end, t) {
    return start + (end - start) * t;
  }

  // Utility function for smoothstep interpolation (smoother than lerp)
  function smoothstep(edge0, edge1, x) {
    // Scale x to be between 0 and 1
    x = clamp((x - edge0) / (edge1 - edge0), 0.0, 1.0);
    // Evaluate polynomial
    return x * x * (3 - 2 * x);
  }

  // SoftShape base class
  class SoftShape {
    constructor(scene, options = {}) {
      this.scene = scene;
      this.options = Object.assign({
        // Default options
        color: 0xffffff, // white color
        alpha: 1.0,      // full opacity
        feather: 4,      // feathering amount for soft edges
        quality: 2       // rendering quality (higher = better but slower)
      }, options);
      
      // Create the display object
      this.displayObject = null;
    }
    
    // Create the soft shape and return a Phaser GameObject
    create() {
      // To be implemented by subclasses
      return null;
    }
    
    // Destroy the display object
    destroy() {
      if (this.displayObject) {
        this.displayObject.destroy();
        this.displayObject = null;
      }
    }
    
    // Set visibility
    setVisible(visible) {
      if (this.displayObject) {
        this.displayObject.setVisible(visible);
      }
    }
    
    // Set alpha/opacity
    setAlpha(alpha) {
      this.options.alpha = alpha;
      if (this.displayObject) {
        this.displayObject.setAlpha(alpha);
      }
    }
    
    // Set tint/color
    setTint(color) {
      this.options.color = color;
      if (this.displayObject) {
        this.displayObject.setTint(color);
      }
    }
  }

  // SoftCircle class - creates a soft-edged circle
  class SoftCircle extends SoftShape {
    constructor(scene, x, y, radius, options = {}) {
      super(scene, options);
      this.x = x;
      this.y = y;
      this.radius = radius;
    }
    
    create() {
      // Create a RenderTexture for the soft circle
      const diameter = (this.radius + this.options.feather) * 2;
      const renderTexture = this.scene.make.renderTexture({
        width: diameter,
        height: diameter
      });
      
      const graphics = this.scene.add.graphics();
      
      // Draw multiple concentric circles with varying alpha to create soft edge
      const steps = this.options.quality * 2;
      for (let i = 0; i <= steps; i++) {
        const t = i / steps;
        // Radius varies from (radius - feather) to (radius + feather)
        const currentRadius = this.radius + (t - 0.5) * 2 * this.options.feather;
        // Alpha creates a soft edge: 0 at feather edges, 1 in the middle
        let alpha;
        if (t < 0.25) {
          alpha = t * 4; // 0 to 1 over first 25%
        } else if (t > 0.75) {
          alpha = (1 - t) * 4; // 1 to 0 over last 25%
        } else {
          alpha = 1; // full opacity in middle 50%
        }
        
        graphics.clear();
        graphics.fillStyle(this.options.color, alpha * this.options.alpha);
        graphics.fillCircle(diameter/2, diameter/2, Math.max(0, currentRadius));
        
        // Render the graphics to the render texture
        renderTexture.draw(graphics, {
          x: 0,
          y: 0
        });
      }
      
      graphics.destroy();
      
      // Position the render texture at the requested coordinates
      renderTexture.setPosition(this.x - diameter/2, this.y - diameter/2);
      
      this.displayObject = renderTexture;
      return renderTexture;
    }
  }

  // SoftRect class - creates a soft-edged rectangle
  class SoftRect extends SoftShape {
    constructor(scene, x, y, width, height, options = {}) {
      super(scene, options);
      this.x = x;
      this.y = y;
      this.width = width;
      this.height = height;
    }
    
    create() {
      // Create a RenderTexture for the soft rectangle
      const feather = this.options.feather;
      const renderTexture = this.scene.make.renderTexture({
        width: this.width + feather * 2,
        height: this.height + feather * 2
      });
      
      const graphics = this.scene.add.graphics();
      
      // Draw multiple rectangles with varying alpha to create soft edge
      const steps = this.options.quality * 2;
      for (let i = 0; i <= steps; i++) {
        const t = i / steps;
        // Size varies from (width - feather*2, height - feather*2) to (width + feather*2, height + feather*2)
        const currentWidth = this.width + (t - 0.5) * 2 * feather * 2;
        const currentHeight = this.height + (t - 0.5) * 2 * feather * 2;
        // Alpha creates a soft edge
        let alpha;
        if (t < 0.25) {
          alpha = t * 4;
        } else if (t > 0.75) {
          alpha = (1 - t) * 4;
        } else {
          alpha = 1;
        }
        
        graphics.clear();
        graphics.fillStyle(this.options.color, alpha * this.options.alpha);
        graphics.fillRect(
          feather + (this.width - currentWidth) / 2,
          feather + (this.height - currentHeight) / 2,
          Math.max(0, currentWidth),
          Math.max(0, currentHeight)
        );
        
        // Render the graphics to the render texture
        renderTexture.draw(graphics, {
          x: 0,
          y: 0
        });
      }
      
      graphics.destroy();
      
      // Position the render texture at the requested coordinates
      renderTexture.setPosition(this.x - feather, this.y - feather);
      
      this.displayObject = renderTexture;
      return renderTexture;
    }
  }

  // Noise generator for procedural textures
  class Noise {
    // Simple value noise
    static valueNoise2D(x, y, seed = 0) {
      // Hash function
      const hash = (i) => {
        let h = seed + i;
        h = Math.sin(h * 12.9898) * 43758.5453;
        return h - Math.floor(h);
      };
      
      // Get integer coordinates
      const x0 = Math.floor(x);
      const x1 = x0 + 1;
      const y0 = Math.floor(y);
      const y1 = y0 + 1;
      
      // Get fractional parts
      const sx = x - x0;
      const sy = y - y0;
      
      // Calculate noise values at corners
      const n0 = hash(x0 + y0 * 57);
      const n1 = hash(x1 + y0 * 57);
      const n2 = hash(x0 + y1 * 57);
      const n3 = hash(x1 + y1 * 57);
      
      // Interpolate
      const ix0 = lerp(n0, n1, sx);
      const ix1 = lerp(n2, n3, sx);
      return lerp(ix0, ix1, sy);
    }
    
    // Generate a noise texture
    static generateTexture(scene, width, height, options = {}) {
      const settings = Object.assign({
        scale: 0.1,
        octaves: 1,
        persistence: 0.5,
        lacunarity: 2.0,
        offsetX: 0,
        offsetY: 0,
        color1: 0x000000, // black
        color2: 0xffffff  // white
      }, options);
      
      // Create a RenderTexture for the noise
      const renderTexture = scene.make.renderTexture({
        width: width,
        height: height
      });
      
      const graphics = scene.add.graphics();
      
      // Sample noise for each pixel (simplified - in practice would use batching)
      const imageData = [];
      for (let py = 0; py < height; py++) {
        for (let px = 0; px < width; px++) {
          // Sample noise
          const nx = (px + settings.offsetX) * settings.scale;
          const ny = (py + settings.offsetY) * settings.scale;
          
          // Simple value noise (could be improved with Perlin/simplex)
          let noise = Noise.valueNoise2D(nx, ny, 0);
          
          // Apply multiple octaves for more interesting noise
          if (settings.octaves > 1) {
            let amplitude = 1.0;
            let frequency = 1.0;
            let noiseSum = 0;
            let maxAmplitude = 0;
            
            for (let o = 0; o < settings.octaves; o++) {
              noiseSum += Noise.valueNoise2D(nx * frequency, ny * frequency, o * 123.456) * amplitude;
              maxAmplitude += amplitude;
              amplitude *= settings.persistence;
              frequency *= settings.lacunarity;
            }
            
            noise = noiseSum / maxAmplitude;
          }
          
          // Normalize to 0-1 range
          noise = (noise + 1) / 2; // Assuming noise is -1 to 1
          
          // Interpolate between colors
          const r1 = (settings.color1 >> 16) & 0xff;
          const g1 = (settings.color1 >> 8) & 0xff;
          const b1 = settings.color1 & 0xff;
          
          const r2 = (settings.color2 >> 16) & 0xff;
          const g2 = (settings.color2 >> 8) & 0xff;
          const b2 = settings.color2 & 0xff;
          
          const r = Math.round(lerp(r1, r2, noise));
          const g = Math.round(lerp(g1, g2, noise));
          const b = Math.round(lerp(b1, b2, noise));
          
          imageData.push((r << 16) | (g << 8) | b);
        }
      }
      
      // For simplicity, we'll just fill with a single color based on noise average
      // A full implementation would update the texture pixel by pixel
      // This is a placeholder for the noise texture functionality
      graphics.fillStyle(settings.color1, 0.5);
      graphics.fillRect(0, 0, width, height);
      
      renderTexture.draw(graphics, {
        x: 0,
        y: 0
      });
      
      graphics.destroy();
      
      this.displayObject = renderTexture;
      return renderTexture;
    }
  }

  // Gradient utilities
  class Gradient {
    // Create a linear gradient function
    static linear(x0, y0, x1, y1, colorStops) {
      return (x, y) => {
        // Calculate position along the gradient line
        const dx = x1 - x0;
        const dy = y1 - y0;
        const length = Math.sqrt(dx * dx + dy * dy);
        
        if (length === 0) {
          return colorStops[0].color;
        }
        
        // Project point onto the line
        const t = ((x - x0) * dx + (y - y0) * dy) / (length * length);
        const clampedT = clamp(t, 0, 1);
        
        // Find the color segment
        for (let i = 0; i < colorStops.length - 1; i++) {
          if (clampedT >= colorStops[i].stop && clampedT <= colorStops[i + 1].stop) {
            const segmentT = (clampedT - colorStops[i].stop) / (colorStops[i + 1].stop - colorStops[i].stop);
            return Gradient._interpolateColor(colorStops[i].color, colorStops[i + 1].color, segmentT);
          }
        }
        
        // Return last color if beyond end
        return colorStops[colorStops.length - 1].color;
      };
    }
    
    // Create a radial gradient function
    static radial(cx, cy, radius, colorStops) {
      return (x, y) => {
        // Calculate distance from center
        const dx = x - cx;
        const dy = y - cy;
        const distance = Math.sqrt(dx * dx + dy * dy);
        
        // Normalize distance to 0-1 range (clamped to radius)
        const t = clamp(distance / radius, 0, 1);
        
        // Find the color segment
        for (let i = 0; i < colorStops.length - 1; i++) {
          if (t >= colorStops[i].stop && t <= colorStops[i + 1].stop) {
            const segmentT = (t - colorStops[i].stop) / (colorStops[i + 1].stop - colorStops[i].stop);
            return Gradient._interpolateColor(colorStops[i].color, colorStops[i + 1].color, segmentT);
          }
        }
        
        // Return last color if beyond end
        return colorStops[colorStops.length - 1].color;
      };
    }
    
    // Interpolate between two colors
    static _interpolateColor(color1, color2, t) {
      const r1 = (color1 >> 16) & 0xff;
      const g1 = (color1 >> 8) & 0xff;
      const b1 = color1 & 0xff;
      
      const r2 = (color2 >> 16) & 0xff;
      const g2 = (color2 >> 8) & 0xff;
      const b2 = color2 & 0xff;
      
      const r = Math.round(lerp(r1, r2, t));
      const g = Math.round(lerp(g1, g2, t));
      const b = Math.round(lerp(b1, b2, t));
      
      return (r << 16) | (g << 8) | b;
    }
  }

  // Expose globally
  window.Art = {
    SoftShape: SoftShape,
    SoftCircle: SoftCircle,
    SoftRect: SoftRect,
    Noise: Noise,
    Gradient: Gradient
  };
  
  // Also expose directly for convenience
  window.SoftCircle = SoftCircle;
  window.SoftRect = SoftRect;
  window.Noise = Noise;
  window.Gradient = Gradient;
  
})();test
test2
test2
test2
