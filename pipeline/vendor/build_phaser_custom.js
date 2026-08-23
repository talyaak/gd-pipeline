/**
 * Custom Phaser 3 Build Script
 * Uses esbuild to create a minimal Phaser bundle with only the modules
 * actually used by generated games.
 *
 * Required modules:
 * - Phaser.Game, Phaser.Scene
 * - Phaser.Physics.Arcade
 * - Phaser.GameObjects.Graphics
 * - Phaser.GameObjects.Image, Phaser.GameObjects.Text
 * - Phaser.Input (Keyboard, Pointer)
 * - Phaser.Math (Between, FloatBetween, Interpolate)
 * - Phaser.Display.Color
 * - Phaser.Cameras.Scene2D
 * - Phaser.Time
 * - Phaser.Sound (WebAudio)
 * - Phaser.Animations (for tweens)
 * - Phaser.Tweens
 */

const esbuild = require('esbuild');
const fs = require('fs');
const path = require('path');

const VENDOR_DIR = path.join(__dirname);
const OUTPUT_FILE = path.join(VENDOR_DIR, 'phaser.custom.min.js');

// Entry point that imports only the required Phaser modules
const entryPoint = `
import Phaser from 'phaser';

// Core
import Game from 'phaser/src/core/Game';
import Scene from 'phaser/src/scene/Scene';
import SceneManager from 'phaser/src/scene/SceneManager';
import Settings from 'phaser/src/settings';

// Physics - Arcade
import ArcadePhysics from 'phaser/src/physics/arcade/ArcadePhysics';
import Body from 'phaser/src/physics/arcade/Body';
import StaticBody from 'phaser/src/physics/arcade/StaticBody';
import Collider from 'phaser/src/physics/arcade/Collider';
import Overlap from 'phaser/src/physics/arcade/Overlap';
import World from 'phaser/src/physics/arcade/World';

// GameObjects - Graphics (procedural textures)
import Graphics from 'phaser/src/gameobjects/graphics/Graphics';
import GraphicsFactory from 'phaser/src/gameobjects/graphics/GraphicsFactory';
import GraphicsCreator from 'phaser/src/gameobjects/graphics/GraphicsCreator';

// GameObjects - Image
import Image from 'phaser/src/gameobjects/image/Image';
import ImageFactory from 'phaser/src/gameobjects/image/ImageFactory';
import ImageCreator from 'phaser/src/gameobjects/image/ImageCreator';

// GameObjects - Text
import Text from 'phaser/src/gameobjects/text/Text';
import TextFactory from 'phaser/src/gameobjects/text/TextFactory';
import TextCreator from 'phaser/src/gameobjects/text/TextCreator';

// Input - Keyboard
import KeyboardPlugin from 'phaser/src/input/keyboard/KeyboardPlugin';
import Key from 'phaser/src/input/keyboard/Key';
import KeyCodes from 'phaser/src/input/keyboard/KeyCodes';
import JustDown from 'phaser/src/input/keyboard/JustDown';
import JustUp from 'phaser/src/input/keyboard/JustUp';

// Input - Pointer (Mouse/Touch)
import InputPlugin from 'phaser/src/input/InputPlugin';
import Pointer from 'phaser/src/input/Pointer';
import Touch from 'phaser/src/input/Touch';
import MouseManager from 'phaser/src/input/MouseManager';

// Input - Gamepad (optional, but small)
import GamepadPlugin from 'phaser/src/input/gamepad/GamepadPlugin';

// Math
import Between from 'phaser/src/math/Between';
import FloatBetween from 'phaser/src/math/FloatBetween';
import Interpolate from 'phaser/src/math/Interpolate';
import Clamp from 'phaser/src/math/Clamp';
import Wrap from 'phaser/src/math/Wrap';
import Snap from 'phaser/src/math/Snap';
import Linear from 'phaser/src/math/Linear';
import SmoothStep from 'phaser/src/math/SmoothStep';
import Angle from 'phaser/src/math/angle';
import Distance from 'phaser/src/math/distance';
import Easing from 'phaser/src/math/easing';

// Display - Color
import Color from 'phaser/src/display/color/Color';
import HSVColorWheel from 'phaser/src/display/color/HSVColorWheel';
import ColorInterpolation from 'phaser/src/display/color/Interpolation';
import RGBToHSV from 'phaser/src/display/color/RGBToHSV';
import HSVToRGB from 'phaser/src/display/color/HSVToRGB';
import ColorToRGBA from 'phaser/src/display/color/ColorToRGBA';
import IntegerToRGB from 'phaser/src/display/color/IntegerToRGB';
import IntegerToColor from 'phaser/src/display/color/IntegerToColor';
import GetColor from 'phaser/src/display/color/GetColor';
import GetColor32 from 'phaser/src/display/color/GetColor32';
import ObjectToColor from 'phaser/src/display/color/ObjectToColor';
import RGBToString from 'phaser/src/display/color/RGBToString';

// Cameras - Scene2D
import CameraManager from 'phaser/src/cameras/2d/CameraManager';
import Camera from 'phaser/src/cameras/2d/Camera';
import Effects from 'phaser/src/cameras/2d/effects';

// Time
import Clock from 'phaser/src/time/Clock';
import TimerEvent from 'phaser/src/time/TimerEvent';

// Sound - WebAudio
import WebAudioSoundManager from 'phaser/src/sound/webaudio/WebAudioSoundManager';
import WebAudioSound from 'phaser/src/sound/webaudio/WebAudioSound';

// Tweens
import TweenManager from 'phaser/src/tweens/TweenManager';
import Tween from 'phaser/src/tweens/Tween';
import TweenData from 'phaser/src/tweens/TweenData';
import TweenFrameData from 'phaser/src/tweens/TweenFrameData';

// Animations
import AnimationManager from 'phaser/src/animations/AnimationManager';
import Animation from 'phaser/src/animations/Animation';
import AnimationFrame from 'phaser/src/animations/AnimationFrame';

// Textures
import TextureManager from 'phaser/src/textures/TextureManager';
import Texture from 'phaser/src/textures/Texture';
import Frame from 'phaser/src/textures/Frame';
import CanvasTexture from 'phaser/src/textures/CanvasTexture';

// Renderer - WebGL/Canvas
import WebGLRenderer from 'phaser/src/renderer/webgl/WebGLRenderer';
import CanvasRenderer from 'phaser/src/renderer/canvas/CanvasRenderer';
import WebGLPipeline from 'phaser/src/renderer/webgl/pipelines/WebGLPipeline';
import TextureTintPipeline from 'phaser/src/renderer/webgl/pipelines/TextureTintPipeline';
import MultiPipeline from 'phaser/src/renderer/webgl/pipelines/MultiPipeline';
import PostPipeline from 'phaser/src/renderer/webgl/pipelines/PostPipeline';

// Scale Manager
import ScaleManager from 'phaser/src/scale/ScaleManager';

// DOM
import DOMContainer from 'phaser/src/gameobjects/dom/DOMContainer';
import DOMElement from 'phaser/src/gameobjects/dom/DOMElement';

// DataManager
import DataManager from 'phaser/src/data/DataManager';
import DataManagerPlugin from 'phaser/src/data/DataManagerPlugin';

// EventEmitter
import EventEmitter from 'phaser/src/events/EventEmitter';

// RTree (for physics)
import RTree from 'phaser/src/structs/RTree';

// Register all plugins and game objects with Phaser
Game.registerType('Graphics', Graphics);
Game.registerType('Image', Image);
Game.registerType('Text', Text);

console.log('Phaser custom build entry point loaded');

// Export the Phaser namespace with only our selected modules
export default Phaser;
`;

// Write the entry point to a temporary file
const ENTRY_FILE = path.join(VENDOR_DIR, 'phaser-custom-entry.js');

async function build() {
    console.log('Building custom Phaser bundle...');

    // Write entry file
    fs.writeFileSync(ENTRY_FILE, entryPoint);

    try {
        await esbuild.build({
            entryPoints: [ENTRY_FILE],
            bundle: true,
            outfile: OUTPUT_FILE,
            format: 'iife',
            globalName: 'Phaser',
            platform: 'browser',
            target: 'es2015',
            minify: true,
            sourcemap: false,
            treeShaking: true,
            drop: ['debugger', 'console'],
            legalComments: 'none',
            define: {
                'process.env.NODE_ENV': '"production"',
            },
            // Phaser uses some Node.js built-ins that need to be handled
            external: [],
            // Handle Phaser's define calls
            inject: [],
        });

        // Clean up entry file
        fs.unlinkSync(ENTRY_FILE);

        // Get file size
        const stats = fs.statSync(OUTPUT_FILE);
        const sizeKB = (stats.size / 1024).toFixed(2);
        const sizeMB = (stats.size / (1024 * 1024)).toFixed(2);

        console.log(`✅ Custom Phaser build complete!`);
        console.log(`   Output: ${OUTPUT_FILE}`);
        console.log(`   Size: ${sizeKB} KB (${sizeMB} MB)`);

        // Also create a gzipped version for size comparison
        const zlib = require('zlib');
        const gzipped = zlib.gzipSync(fs.readFileSync(OUTPUT_FILE));
        const gzipKB = (gzipped.length / 1024).toFixed(2);
        console.log(`   Gzipped: ${gzipKB} KB`);

    } catch (error) {
        console.error('❌ Build failed:', error);
        // Clean up entry file on error
        if (fs.existsSync(ENTRY_FILE)) {
            fs.unlinkSync(ENTRY_FILE);
        }
        process.exit(1);
    }
}

build();