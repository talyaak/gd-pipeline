from pathlib import Path
import gzip
import json
import re

from pipeline.execute import run_execution_report
from pipeline.output import stage_dir, write_text, write_json
from pipeline.schemas import RunState
from pipeline.validate import check_html_game


def _apply_palette_swap(html: str, variant_name: str) -> str:
    """Apply a color palette transformation."""
    palettes = {
        "neon": {
            "0x1a1a2e": "0x0a0a1a",
            "0x00ff00": "0x00ffff",
            "0xff0044": "0xff00ff",
            "0xffff00": "0xffffff",
            "#111": "#000",
            "#1a1a2e": "#0a0a1a",
            "#00ff00": "#00ffff",
            "#ff0044": "#ff00ff",
            "#ffff00": "#ffffff",
        },
        "retro": {
            "0x1a1a2e": "0x2d1b0e",
            "0x00ff00": "0xffaa00",
            "0xff0044": "0xff4400",
            "0xffff00": "0xffff88",
            "#111": "#1a1a1a",
            "#1a1a2e": "#2d1b0e",
            "#00ff00": "#ffaa00",
            "#ff0044": "#ff4400",
            "#ffff00": "#ffff88",
        },
        "pastel": {
            "0x1a1a2e": "0xf0e6f6",
            "0x00ff00": "0x9bff9b",
            "0xff0044": "0xff9bb3",
            "0xffff00": "0xffffb3",
            "#111": "#e0e0e0",
            "#1a1a2e": "#f0e6f6",
            "#00ff00": "#9bff9b",
            "#ff0044": "#ff9bb3",
            "#ffff00": "#ffffb3",
        },
        "mono": {
            "0x1a1a2e": "0x111111",
            "0x00ff00": "0xffffff",
            "0xff0044": "0xaaaaaa",
            "0xffff00": "0xcccccc",
            "#111": "#000",
            "#1a1a2e": "#111111",
            "#00ff00": "#ffffff",
            "#ff0044": "#aaaaaa",
            "#ffff00": "#cccccc",
        },
    }
    palette = palettes.get(variant_name, palettes["neon"])
    result = html
    for old, new in palette.items():
        result = result.replace(old, new)
    return result


def _apply_difficulty_tweak(html: str, variant_name: str) -> str:
    """Modify balance values in the game code."""
    tweaks = {
        "easy": {
            "baseSpeed = 200": "baseSpeed = 150",
            "maxSpeed = 800": "maxSpeed = 500",
            "speedIncrement = 10": "speedIncrement = 5",
            "gravity = 1200": "gravity = 800",
            "jump_velocity\": \"-450": "jump_velocity\": \"-400",
            "spawn_interval\": \"2.0": "spawn_interval\": \"3.0",
        },
        "hard": {
            "baseSpeed = 200": "baseSpeed = 300",
            "maxSpeed = 800": "maxSpeed = 1000",
            "speedIncrement = 10": "speedIncrement = 15",
            "gravity = 1200": "gravity = 1500",
            "jump_velocity\": \"-450": "jump_velocity\": \"-500",
            "spawn_interval\": \"2.0": "spawn_interval\": \"1.2",
        },
        "insane": {
            "baseSpeed = 200": "baseSpeed = 400",
            "maxSpeed = 800": "maxSpeed = 1200",
            "speedIncrement = 10": "speedIncrement = 20",
            "gravity = 1200": "gravity = 1800",
            "jump_velocity\": \"-450": "jump_velocity\": \"-550",
            "spawn_interval\": \"2.0": "spawn_interval\": \"0.8",
        },
    }
    tweak = tweaks.get(variant_name, {})
    result = html
    for old, new in tweak.items():
        result = result.replace(old, new)
    return result


def _inject_cta(html: str, variant_name: str) -> str:
    """Inject CTA/end-card into the game."""
    cta_configs = {
        "install": {
            "text": "INSTALL NOW",
            "url": "https://example.com/install",
            "color": "#00aa00",
        },
        "play": {
            "text": "PLAY FULL VERSION",
            "url": "https://example.com/play",
            "color": "#0066ff",
        },
        "signup": {
            "text": "SIGN UP FOR BETA",
            "url": "https://example.com/signup",
            "color": "#aa00ff",
        },
    }
    config = cta_configs.get(variant_name, cta_configs["install"])
    
    # Find the game over text area and add CTA button
    cta_html = f'''
                // CTA Button
                this.ctaButton = this.add.rectangle(
                    this.cameras.main.width / 2,
                    this.cameras.main.height / 2 + 100,
                    300, 60,
                    Phaser.Display.Color.HexStringToColor("{config["color"]}").color
                ).setInteractive().setVisible(false);
                
                this.ctaText = this.add.text(
                    this.cameras.main.width / 2,
                    this.cameras.main.height / 2 + 100,
                    "{config["text"]}",
                    {{fontSize: '24px', fill: '#ffffff', fontStyle: 'bold'}}
                ).setOrigin(0.5).setVisible(false);
                
                this.ctaButton.on('pointerdown', () => {{
                    window.open("{config["url"]}", "_blank");
                }});
                
                this.ctaButton.on('pointerover', () => {{
                    this.ctaButton.setFillStyle(Phaser.Display.Color.HexStringToColor("{config["color"]}").color, 0.8);
                }});
                
                this.ctaButton.on('pointerout', () => {{
                    this.ctaButton.setFillStyle(Phaser.Display.Color.HexStringToColor("{config["color"]}").color, 1);
                }});'''
    
    # Inject before the closing of create()
    result = html.replace(
        "// Set initial background",
        cta_html + "\n                // Set initial background"
    )
    
    # Show CTA on game over
    result = result.replace(
        "this.gameOverText.setVisible(true);",
        f"this.gameOverText.setVisible(true);\n                this.ctaButton.setVisible(true);\n                this.ctaText.setVisible(true);"
    )
    
    return result


def _apply_visual_theme(html: str, variant_name: str) -> str:
    """Apply visual theme changes."""
    themes = {
        "particle_trails": {
            "this.trailParticles.push({": "this.trailParticles.push({\n                    // Enhanced trail with glow",
            "size: 4": "size: 6",
        },
        "glow_effects": {
            "shadow: { blur: 10, color: '#00FFFF', fill: true }": "shadow: { blur: 20, color: '#00FFFF', fill: true }",
            "strokeThickness: 2": "strokeThickness: 4",
        },
        "minimal": {
            "shadow: { blur: 10, color: '#00FFFF', fill: true }": "",
            "strokeThickness: 4": "strokeThickness: 1",
            "strokeThickness: 2": "strokeThickness: 0",
        },
    }
    theme = themes.get(variant_name, {})
    result = html
    for old, new in theme.items():
        if new:
            result = result.replace(old, new)
        else:
            # Remove the line
            result = result.replace(old, "")
    return result


def _generate_variants(base_html: str, spec_artifact: dict, variant_types: list[dict]) -> list[dict]:
    """Generate all variants from base HTML."""
    variants = []
    
    for variant_type in variant_types:
        vtype = variant_type["type"]
        vname = variant_type["name"]
        html = base_html
        
        if vtype == "palette":
            html = _apply_palette_swap(html, vname)
        elif vtype == "difficulty":
            html = _apply_difficulty_tweak(html, vname)
        elif vtype == "cta":
            html = _inject_cta(html, vname)
        elif vtype == "theme":
            html = _apply_visual_theme(html, vname)
        
        # Add variant identifier comment after DOCTYPE
        html = html.replace("<!DOCTYPE html>", f"<!DOCTYPE html>\n<!-- Variant: {vtype}:{vname} -->")
        
        variants.append({
            "type": vtype,
            "name": vname,
            "html": html,
            "spec": spec_artifact,
        })
    
    return variants


def variant_gen(state: RunState) -> dict:
    """Generate deterministic variants from a validated game."""
    code = state["code"]
    spec = state["spec"]["artifact"]
    
    if code["status"] != "passed":
        return {"variants": {"status": "skipped", "reason": "base game not passed"}}
    
    base_html = code["artifact"]["html"]
    
    # Define variant configurations
    variant_configs = [
        {"type": "palette", "name": "neon"},
        {"type": "palette", "name": "retro"},
        {"type": "palette", "name": "pastel"},
        {"type": "difficulty", "name": "easy"},
        {"type": "difficulty", "name": "hard"},
        {"type": "cta", "name": "install"},
        {"type": "cta", "name": "play"},
        {"type": "theme", "name": "particle_trails"},
    ]
    
    variants = _generate_variants(base_html, spec, variant_configs)
    
    # Validate and save each variant
    results = []
    for i, variant in enumerate(variants):
        out_dir = stage_dir(Path(state["run_dir"]), 6, "variants", 1)
        variant_dir = out_dir / f"variant_{i}_{variant['type']}_{variant['name']}"
        variant_dir.mkdir(parents=True, exist_ok=True)
        
        # Static validation
        static_issues = check_html_game(variant["html"])
        if static_issues:
            results.append({
                **variant,
                "status": "failed_static",
                "errors": static_issues,
            })
            write_text(variant_dir, "game.html", variant["html"])
            write_json(variant_dir, "errors.json", {"static": static_issues})
            continue
        
        # Execution validation
        report = run_execution_report(variant["html"], variant_dir)
        runtime_ok = report.loaded and not report.console_errors and report.canvas_rendered
        
        results.append({
            **variant,
            "status": "passed" if runtime_ok else "failed_runtime",
            "execution": report.model_dump(),
        })
        
        write_text(variant_dir, "game.html", variant["html"])
        write_json(variant_dir, "execution.json", report.model_dump())
    
    passed_count = sum(1 for r in results if r["status"] == "passed")
    
    return {
        "variants": {
            "status": "passed" if passed_count > 0 else "failed",
            "attempt": 1,
            "artifact": {"variants": results},
            "review": None,
            "error": None if passed_count > 0 else "no variants passed",
        }
    }