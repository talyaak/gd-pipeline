// Local MRAID 3.0 simulator — used only when no host-provided `mraid` exists yet.
//
// In a real ad network placement (Google Ads, Unity Ads, AppLovin, ironSource,
// Vungle, Mintegral, ...), the network's own WebView SDK injects its own real
// `window.mraid` implementation before this creative's scripts run — that real
// bridge is what actually talks to the native host. This file must never
// overwrite that; it only fills in `window.mraid` when nothing has claimed
// it yet (e.g. previewing the creative directly, or under this pipeline's own
// browser-execution validation harness), so the creative's `mraid.*` calls have
// something to run against instead of throwing on an undefined `mraid`.
(function() {
  'use strict';

  // A real host bridge has already claimed window.mraid — never clobber it.
  if (typeof window.mraid !== 'undefined') {
    return;
  }

  // MRAID State
  const MRAID_VERSION = '3.0';
  let state = 'loading';
  let viewable = false;
  let listeners = {};
  let expandProperties = {
    width: 0,
    height: 0,
    useCustomClose: false,
    isModal: true
  };
  let resizeProperties = {
    width: 0,
    height: 0,
    offsetX: 0,
    offsetY: 0,
    customClosePosition: 'top-right',
    allowOffscreen: true
  };
  let orientationProperties = {
    allowOrientationChange: true,
    forceOrientation: 'none'
  };
  let currentPosition = { x: 0, y: 0, width: 0, height: 0 };
  let defaultPosition = { x: 0, y: 0, width: 0, height: 0 };
  let screenSize = { width: 0, height: 0 };
  let maxSize = { width: 0, height: 0 };
  let supports = ['sms', 'tel', 'calendar', 'storePicture', 'inlineVideo', 'audioVideo', 'location', 'accelerometer', 'gyroscope', 'compass', 'orientation', 'proximity', 'screenOrientation'];

  // No real native host to talk to here (see file header) — these calls are
  // deliberately no-ops in the common case. The window.webkit/android checks
  // below are a best-effort hook for local WebView test harnesses that expose
  // a bridge under one of these names; they are NOT how any real ad network's
  // SDK exposes its bridge, so this function has no effect inside a real
  // placement (where window.mraid is the host's own object and this file's
  // guard above means this code never runs at all).
  function bridge(method, args) {
    if (window.webkit && window.webkit.messageHandlers && window.webkit.messageHandlers.mraid) {
      window.webkit.messageHandlers.mraid.postMessage({ method, args });
    } else if (window.mraidBridge && window.mraidBridge[method]) {
      window.mraidBridge[method].apply(null, args);
    } else if (window.android && window.android.mraid) {
      window.android.mraid[method].apply(null, args);
    }
  }

  // Event system
  function fireEvent(event, ...args) {
    if (listeners[event]) {
      listeners[event].forEach(cb => {
        try { cb.apply(null, args); } catch (e) { console.error('MRAID listener error:', e); }
      });
    }
  }

  function addEventListener(event, listener) {
    if (!listeners[event]) listeners[event] = [];
    if (typeof listener === 'function' && !listeners[event].includes(listener)) {
      listeners[event].push(listener);
    }
  }

  function removeEventListener(event, listener) {
    if (listeners[event] && typeof listener === 'function') {
      const idx = listeners[event].indexOf(listener);
      if (idx > -1) listeners[event].splice(idx, 1);
    }
  }

  // Core API
  const mraid = {
    // Version & Capabilities
    getVersion: () => {
      // Check for URL parameter override first
      const params = new URLSearchParams(window.location.search);
      return params.get('mraidVersion') || MRAID_VERSION;
    },
    getPlacementType: () => {
      // Check for URL parameter override first
      const params = new URLSearchParams(window.location.search);
      return params.get('placement') || 'interstitial';
    },
    getState: () => state,
    isViewable: () => viewable,

    // Event Handling
    addEventListener,
    removeEventListener,

    // Lifecycle - NO ready() method. Per MRAID spec, ready is fired BY the bridge.
    // Creative code MUST NOT call mraid.ready(). It should listen:
    // mraid.addEventListener('ready', cb) or check mraid.getState() !== 'loading'
    
    // Viewability
    _setViewable: (v) => {
      const wasViewable = viewable;
      viewable = v;
      if (v !== wasViewable) {
        fireEvent('viewableChange', v);
      }
    },

    // Expand/Close
    expand: (url) => {
      if (state === 'expanded') return;
      if (url) {
        // Open URL in browser
        mraid.open(url);
        return;
      }
      state = 'expanded';
      fireEvent('stateChange', state);
      bridge('expand', [expandProperties]);
    },

    close: () => {
      if (state === 'default' || state === 'resized') {
        bridge('close', []);
      } else if (state === 'expanded') {
        state = 'default';
        fireEvent('stateChange', state);
        bridge('close', []);
      }
    },

    // Resize
    resize: () => {
      if (state === 'expanded') return;
      state = 'resized';
      fireEvent('stateChange', state);
      fireEvent('resize');
      bridge('resize', [resizeProperties]);
    },

    setResizeProperties: (props) => {
      resizeProperties = { ...resizeProperties, ...props };
      bridge('setResizeProperties', [resizeProperties]);
    },

    getResizeProperties: () => ({ ...resizeProperties }),

    // Orientation
    setOrientationProperties: (props) => {
      orientationProperties = { ...orientationProperties, ...props };
      bridge('setOrientationProperties', [orientationProperties]);
    },

    getOrientationProperties: () => ({ ...orientationProperties }),

    // Position & Size
    getCurrentPosition: () => ({ ...currentPosition }),
    getDefaultPosition: () => ({ ...defaultPosition }),
    getScreenSize: () => ({ ...screenSize }),
    getMaxSize: () => ({ ...maxSize }),

    // Open URL
    open: (url) => {
      if (!url || typeof url !== 'string') return;
      // Validate URL scheme
      const validSchemes = ['http:', 'https:', 'tel:', 'sms:', 'mailto:', 'market:', 'itms-apps:'];
      const isValid = validSchemes.some(s => url.startsWith(s));
      if (!isValid) {
        console.warn('MRAID: Invalid URL scheme', url);
        return;
      }
      bridge('open', [url]);
    },

    // Supports
    supports: (feature) => supports.includes(feature),

    // Audio/Video (MRAID 3.0)
    createCalendarEvent: (params) => bridge('createCalendarEvent', [params]),
    playVideo: (url) => bridge('playVideo', [url]),
    storePicture: (url) => bridge('storePicture', [url]),

    // Internal: called by native bridge
    _setState: (newState) => {
      const oldState = state;
      state = newState;
      if (oldState !== newState) {
        fireEvent('stateChange', state);
      }
    },

    _setPosition: (pos) => {
      currentPosition = { ...pos };
      fireEvent('sizeChange', currentPosition.width, currentPosition.height);
    },

    _setScreenSize: (size) => {
      screenSize = { ...size };
    },

    _setMaxSize: (size) => {
      maxSize = { ...size };
    },

    _setDefaultPosition: (pos) => {
      defaultPosition = { ...pos };
      currentPosition = { ...pos };
    },

    _setExpandProperties: (props) => {
      expandProperties = { ...props };
    },

    // For debugging
    _getListeners: () => listeners,
    _getState: () => state,
  };

  // Expose globally
  window.mraid = mraid;

  // Auto-initialize when DOM is ready - fire ready event automatically
  // This simulates the host bridge firing ready after it initializes
  function autoInit() {
    if (state === 'loading') {
      state = 'default';
      fireEvent('ready');
      // Simulate viewable for local testing
      mraid._setViewable(true);
    }
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', autoInit);
  } else {
    autoInit();
  }

  // Notify native that JS is loaded
  bridge('mraidLoaded', []);

})();