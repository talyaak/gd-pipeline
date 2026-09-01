// Procedural UI Kit for HTML5 Playable Ads
// Provides reusable UI components (Button, ProgressBar, Popup) with states, transitions, and theming
// Designed to work alongside Phaser 3 in single-file HTML5 games

(function() {
  'use strict';

  // Utility function to ease between two values
  function ease(start, end, t, easeFn = Phaser.Math.Easing.Sine.InOut) {
    return start + (end - start) * easeFn(t);
  }

  // Button class with states: normal, hover, pressed, disabled
  class Button {
    /**
     * @param {Phaser.Scene} scene - The scene to add the button to
     * @param {number} x - X position
     * @param {number} y - Y position
     * @param {string} text - Button text
     * @param {object} styles - Style configuration from visual spec
     * @param {function} callback - Function to call when button is clicked
     * @param {number} width - Button width (optional, auto-calculated if not provided)
     * @param {number} height - Button height (optional, auto-calculated if not provided)
     */
    constructor(scene, x, y, text, styles, callback, width = null, height = null) {
      this.scene = scene;
      this.x = x;
      this.y = y;
      this.text = text;
      this.styles = styles || {};
      this.callback = callback;
      this.enabled = true;
      this.hovered = false;
      this.pressed = false;
      
      // Default styles if not provided
      this.defaultStyles = {
        button_states: {
          normal: '#00aa00',
          hover: '#00cc00', 
          pressed: '#008800',
          disabled: '#555555'
        },
        text_styles: {
          ui: {fontSize: '24px', fill: '#ffffff'}
        }
      };
      
      // Create button background
      this.bg = scene.add.rectangle(x, y, width || 200, height || 60, 0x00aa00);
      this.bg.setOrigin(0.5);
      this.bg.setDepth(1);
      
      // Create button text
      this.label = scene.add.text(x, y, text, this._getStyle('text_styles.ui'));
      this.label.setOrigin(0.5);
      this.label.setDepth(2);
      
      // Set initial state
      this._updateStyle('normal');
      
      // Make interactive
      this.bg.setInteractive({ useHandCursor: true });
      this.bg.on('pointerover', this._onPointerOver, this);
      this.bg.on('pointerout', this._onPointerOut, this);
      this.bg.on('pointerdown', this._onPointerDown, this);
      this.bg.on('pointerup', this._onPointerUp, this);
      this.bg.on('pointerupoutside', this._onPointerUpOutside, this);
    }
    
    _getStyle(path) {
      const parts = path.split('.');
      let value = this.styles;
      for (const part of parts) {
        if (value[part] !== undefined) {
          value = value[part];
        } else {
          // Fallback to default styles
          let defaultValue = this.defaultStyles;
          for (const defPart of parts) {
            if (defaultValue[defPart] !== undefined) {
              defaultValue = defaultValue[defPart];
            } else {
              return null;
            }
          }
          return defaultValue;
        }
      }
      return value;
    }
    
    _updateStyle(state) {
      if (!this.enabled && state !== 'disabled') return;
      
      let color;
      if (this.enabled) {
        switch(state) {
          case 'normal': color = this._getStyle('button_states.normal'); break;
          case 'hover': color = this._getStyle('button_states.hover'); break;
          case 'pressed': color = this._getStyle('button_states.pressed'); break;
          default: color = this._getStyle('button_states.normal');
        }
      } else {
        color = this._getStyle('button_states.disabled');
      }
      
      if (color) {
        // Handle both visual spec format (string: "#rrggbb") and codegen format (object: { bg: 0xrrggbb })
        let fillColor;
        if (typeof color === 'object' && color.bg !== undefined) {
          fillColor = color.bg;
        } else if (typeof color === 'string') {
          fillColor = parseInt(color.replace('#', '0x'), 16);
        } else {
          // Assume it's already a number (0xRRGGBB)
          fillColor = color;
        }
        this.bg.setFillStyle(fillColor);
      }
    }
    
    _onPointerOver() {
      if (!this.enabled) return;
      this.hovered = true;
      this._updateStyle('hover');
      // Scale up slightly on hover
      this.scene.tweens.add({
        targets: this.bg,
        scaleX: 1.05,
        scaleY: 1.05,
        duration: 100,
        ease: 'Sine.easeInOut'
      });
      this.scene.tweens.add({
        targets: this.label,
        scaleX: 1.05,
        scaleY: 1.05,
        duration: 100,
        ease: 'Sine.easeInOut'
      });
    }
    
    _onPointerOut() {
      if (!this.enabled) return;
      this.hovered = false;
      if (!this.pressed) {
        this._updateStyle('normal');
      }
      // Scale back to normal
      this.scene.tweens.add({
        targets: this.bg,
        scaleX: 1,
        scaleY: 1,
        duration: 100,
        ease: 'Sine.easeInOut'
      });
      this.scene.tweens.add({
        targets: this.label,
        scaleX: 1,
        scaleY: 1,
        duration: 100,
        ease: 'Sine.easeInOut'
      });
    }
    
    _onPointerDown() {
      if (!this.enabled) return;
      this.pressed = true;
      this._updateStyle('pressed');
      // Scale down slightly on press
      this.scene.tweens.add({
        targets: this.bg,
        scaleX: 0.95,
        scaleY: 0.95,
        duration: 100,
        ease: 'Sine.easeInOut'
      });
      this.scene.tweens.add({
        targets: this.label,
        scaleX: 0.95,
        scaleY: 0.95,
        duration: 100,
        ease: 'Sine.easeInOut'
      });
    }
    
    _onPointerUp() {
      if (!this.enabled) return;
      if (this.hovered && this.pressed) {
        this.pressed = false;
        this._updateStyle('hover');
        // Scale back to hover state
        this.scene.tweens.add({
          targets: this.bg,
          scaleX: 1.05,
          scaleY: 1.05,
          duration: 100,
          ease: 'Sine.easeInOut'
        });
        this.scene.tweens.add({
          targets: this.label,
          scaleX: 1.05,
          scaleY: 1.05,
          duration: 100,
          ease: 'Sine.easeInOut'
        });
        // Execute callback
        if (this.callback) this.callback();
      } else {
        this._onPointerOut();
      }
    }
    
    _onPointerUpOutside() {
      if (!this.enabled) return;
      this.pressed = false;
      this._updateStyle('normal');
      // Scale back to normal
      this.scene.tweens.add({
        targets: this.bg,
        scaleX: 1,
        scaleY: 1,
        duration: 100,
        ease: 'Sine.easeInOut'
      });
      this.scene.tweens.add({
        targets: this.label,
        scaleX: 1,
        scaleY: 1,
        duration: 100,
        ease: 'Sine.easeInOut'
      });
    }
    
    setEnabled(enabled) {
      this.enabled = enabled;
      if (enabled) {
        if (this.hovered) {
          this._updateStyle('hover');
        } else if (this.pressed) {
          this._updateStyle('pressed');
        } else {
          this._updateStyle('normal');
        }
      } else {
        this._updateStyle('disabled');
      }
      this.bg.setInteractive(enabled ? { useHandCursor: true } : false);
    }
    
    setText(text) {
      this.text = text;
      this.label.setText(text);
    }
    
    destroy() {
      this.bg.destroy();
      this.label.destroy();
      this.bg.removeAllListeners();
      this.label.removeAllListeners();
    }
    setVisible(visible) {
      if (this.bg) this.bg.setVisible(visible);
      if (this.label) this.label.setVisible(visible);
    }
    setDepth(depth) {
      if (this.bg) this.bg.setDepth(depth);
      if (this.label) this.label.setDepth(depth + 1);
      return this;
    }
  }

  // ProgressBar class
  class ProgressBar {
    /**
     * @param {Phaser.Scene} scene - The scene to add the progress bar to
     * @param {number} x - X position
     * @param {number} y - Y position
     * @param {number} width - Width of the progress bar
     * @param {number} height - Height of the progress bar
     * @param {object} styles - Style configuration from visual spec
     */
    constructor(scene, x, y, width, height, styles) {
      this.scene = scene;
      this.x = x;
      this.y = y;
      this.width = width;
      this.height = height;
      this.styles = styles || {};
      this.value = 0; // 0 to 1
      
      // Default styles if not provided
      this.defaultStyles = {
        progress_bar: {
          background: '#333333',
          fill: '#00aa00',
          text: '#ffffff'
        },
        text_styles: {
          ui: {fontSize: '20px', fill: '#ffffff'}
        }
      };
      
      // Create background
      this.bg = scene.add.rectangle(x, y, width, height, 0x333333);
      this.bg.setOrigin(0.5);
      this.bg.setDepth(1);
      
      // Create fill bar
      this.fill = scene.add.rectangle(x - width/2 + 2, y, width - 4, height - 4, 0x00aa00);
      this.fill.setOrigin(0, 0.5);
      this.fill.setDepth(2);
      
      // Create text label
      this.label = scene.add.text(x, y, '0%', this._getStyle('text_styles.ui'));
      this.label.setOrigin(0.5);
      this.label.setDepth(3);
      
      this._updateDisplay();
    }
    
    _getStyle(path) {
      const parts = path.split('.');
      let value = this.styles;
      for (const part of parts) {
        if (value[part] !== undefined) {
          value = value[part];
        } else {
          // Fallback to default styles
          let defaultValue = this.defaultStyles;
          for (const defPart of parts) {
            if (defaultValue[defPart] !== undefined) {
              defaultValue = defaultValue[defPart];
            } else {
              return null;
            }
          }
          return defaultValue;
        }
      }
      return value;
    }
    
    setValue(value) {
      this.value = Phaser.Math.Clamp(value, 0, 1);
      this._updateDisplay();
    }
    
    getValue() {
      return this.value;
    }
    
    _updateDisplay() {
      // Update fill width
      const fillWidth = (this.width - 4) * this.value;
      this.fill.setWidth(fillWidth);
      this.fill.setPosition(this.x - this.width/2 + 2, this.y);
      
      // Update text
      const percent = Math.round(this.value * 100);
      this.label.setText(`${percent}%`);
      
      // Update colors - handle both visual spec format (string: "#rrggbb") and codegen format (object: { bg: 0xrrggbb })
      const bgColor = this._getStyle('progress_bar.background');
      const fillColor = this._getStyle('progress_bar.fill');
      const textColor = this._getStyle('progress_bar.text');
      
      function parseColor(color) {
        if (typeof color === 'object' && color.bg !== undefined) {
          return color.bg;
        } else if (typeof color === 'string') {
          return parseInt(color.replace('#', '0x'), 16);
        } else {
          // Assume it's already a number (0xRRGGBB)
          return color;
        }
      }
      
      if (bgColor) {
        this.bg.setFillStyle(parseColor(bgColor));
      }
      if (fillColor) {
        this.fill.setFillStyle(parseColor(fillColor));
      }
      if (textColor) {
        this.label.setStyle({ fill: textColor });
      }
    }
    
    destroy() {
      this.bg.destroy();
      this.fill.destroy();
      this.label.destroy();
    }
    setVisible(visible) {
      if (this.bg) this.bg.setVisible(visible);
      if (this.fill) this.fill.setVisible(visible);
      if (this.label) this.label.setVisible(visible);
    }
  }

  // Popup class for dialogs and overlays
  class Popup {
    /**
     * @param {Phaser.Scene} scene - The scene to add the popup to
     * @param {object} config - Popup configuration
     * @param {number} config.width - Width of popup
     * @param {number} config.height - Height of popup
     * @param {string} config.title - Title text (optional)
     * @param {string} config.message - Message text (optional)
     * @param {array} config.buttons - Array of button configs {text, callback}
     * @param {object} styles - Style configuration from visual spec
     */
    constructor(scene, config = {}, styles) {
      this.scene = scene;
      this.config = {
        width: config.width || 400,
        height: config.height || 300,
        title: config.title || '',
        message: config.message || '',
        buttons: config.buttons || []
      };
      this.styles = styles || {};
      this.enabled = true;
      
      // Default styles if not provided
      this.defaultStyles = {
        color_palette: {
          background: '#000000',
          ui_normal: '#00aa00',
          ui_hover: '#00cc00',
          ui_pressed: '#008800',
          ui_disabled: '#555555'
        },
        button_states: {
          normal: '#00aa00',
          hover: '#00cc00', 
          pressed: '#008800',
          disabled: '#555555'
        },
        text_styles: {
          title: {fontSize: '32px', fill: '#ffffff'},
          ui: {fontSize: '24px', fill: '#ffffff'}
        }
      };
      
      // Create background (dark overlay)
      this.background = scene.add.rectangle(
        scene.cameras.main.width/2, 
        scene.cameras.main.height/2, 
        scene.cameras.main.width, 
        scene.cameras.main.height, 
        0x000000
      );
      this.background.setOrigin(0.5);
      this.background.setAlpha(0.7);
      this.background.setDepth(1);
      this.background.setInteractive(); // Block clicks to underlying game
      
      // Create popup container
      this.container = scene.add.container(
        scene.cameras.main.width/2,
        scene.cameras.main.height/2
      );
      this.container.setDepth(2);
      
      // Create popup background
      this.popupBg = scene.add.rectangle(0, 0, this.config.width, this.config.height, 0x000000);
      this.popupBg.setOrigin(0.5);
      this.popupBg.setDepth(1);
      
      // Create popup border
      this.popupBorder = scene.add.rectangle(0, 0, this.config.width, this.config.height, 0x00aa00);
      this.popupBorder.setOrigin(0.5);
      this.popupBorder.setStrokeStyle(2, 0x00aa00);
      this.popupBorder.setFillStyle(0x000000);
      this.popupBorder.setDepth(2);
      
      // Create title text (if provided)
      this.titleText = null;
      if (this.config.title) {
        this.titleText = scene.add.text(0, -this.config.height/2 + 40, this.config.title, this._getStyle('text_styles.title'));
        this.titleText.setOrigin(0.5);
        this.titleText.setDepth(3);
        this.container.add(this.titleText);
      }
      
      // Create message text (if provided)
      this.messageText = null;
      if (this.config.message) {
        this.messageText = scene.add.text(0, this.titleText ? -this.config.height/2 + 80 : 0, this.config.message, this._getStyle('text_styles.ui'));
        this.messageText.setOrigin(0.5);
        this.messageText.setWordWrapWidth(this.config.width - 40);
        this.messageText.setAlign('center');
        this.messageText.setDepth(3);
        this.container.add(this.messageText);
      }
      
      // Create buttons
      this.buttonObjects = [];
      if (this.config.buttons.length > 0) {
        const buttonWidth = 120;
        const buttonHeight = 50;
        const buttonSpacing = 20;
        const totalButtonsWidth = (buttonWidth * this.config.buttons.length) + (buttonSpacing * (this.config.buttons.length - 1));
        const startX = -totalButtonsWidth/2;
        
        this.config.buttons.forEach((buttonConfig, index) => {
          const buttonX = startX + (index * (buttonWidth + buttonSpacing));
          const buttonY = this.config.height/2 - 60;
          
          const button = new Button(
            scene,
            buttonX,
            buttonY,
            buttonConfig.text,
            this.styles,
            buttonConfig.callback,
            buttonWidth,
            buttonHeight
          );
          
          this.buttonObjects.push(button);
          this.container.add(button.bg);
          this.container.add(button.label);
        });
      }
      
      // Add all elements to container
      this.container.add(this.popupBg);
      this.container.add(this.popupBorder);
      
      // Start hidden
      this.hide();
    }
    
    _getStyle(path) {
      const parts = path.split('.');
      let value = this.styles;
      for (const part of parts) {
        if (value[part] !== undefined) {
          value = value[part];
        } else {
          // Fallback to default styles
          let defaultValue = this.defaultStyles;
          for (const defPart of parts) {
            if (defaultValue[defPart] !== undefined) {
              defaultValue = defaultValue[defPart];
            } else {
              return null;
            }
          }
          return defaultValue;
        }
      }
      return value;
    }
    
    show() {
      if (!this.enabled) return;
      this.background.setVisible(true);
      this.container.setVisible(true);
      
      // Add popup-in animation
      this.container.scaleX = 0.5;
      this.container.scaleY = 0.5;
      this.container.alpha = 0;
      
      this.scene.tweens.add({
        targets: this.container,
        scaleX: 1,
        scaleY: 1,
        alpha: 1,
        duration: 300,
        ease: 'Back.easeOut'
      });
      
      this.background.setInteractive();
    }
    
    hide() {
      this.background.setVisible(false);
      this.container.setVisible(false);
      this.background.disableInteractive();
    }
    
    setTitle(title) {
      this.config.title = title;
      if (this.titleText) {
        this.titleText.setText(title);
      } else if (title) {
        this.titleText = this.scene.add.text(0, -this.config.height/2 + 40, title, this._getStyle('text_styles.title'));
        this.titleText.setOrigin(0.5);
        this.titleText.setDepth(3);
        this.container.add(this.titleText, 0); // Add at beginning
      }
    }
    
    setMessage(message) {
      this.config.message = message;
      if (this.messageText) {
        this.messageText.setText(message);
      } else if (message) {
        this.messageText = this.scene.add.text(0, this.titleText ? -this.config.height/2 + 80 : 0, message, this._getStyle('text_styles.ui'));
        this.messageText.setOrigin(0.5);
        this.messageText.setWordWrapWidth(this.config.width - 40);
        this.messageText.setAlign('center');
        this.messageText.setDepth(3);
        this.container.add(this.messageText, this.titleText ? 1 : 0); // Add after title if exists
      }
    }
    
    destroy() {
      // Destroy all button objects
      this.buttonObjects.forEach(button => {
        button.destroy();
      });
      
      this.background.destroy();
      this.popupBg.destroy();
      this.popupBorder.destroy();
      if (this.titleText) this.titleText.destroy();
      if (this.messageText) this.messageText.destroy();
      this.container.removeAll(true);
      this.container.destroy();
    }
    setVisible(visible) {
      if (this.background) this.background.setVisible(visible);
      if (this.container) this.container.setVisible(visible);
      if (this.popupBg) this.popupBg.setVisible(visible);
      if (this.popupBorder) this.popupBorder.setVisible(visible);
      if (this.titleText) this.titleText.setVisible(visible);
      if (this.messageText) this.messageText.setVisible(visible);
      this.buttonObjects.forEach(button => {
        if (button.bg) button.bg.setVisible(visible);
        if (button.label) button.label.setVisible(visible);
      });
    }
  }

  // Expose globally
  window.UIKit = {
    Button: Button,
    ProgressBar: ProgressBar,
    Popup: Popup
  };
  
  // Also expose directly for convenience
  window.Button = Button;
  window.ProgressBar = ProgressBar;
  window.Popup = Popup;
  
})();