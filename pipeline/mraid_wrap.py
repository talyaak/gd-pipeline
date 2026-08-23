from pathlib import Path

# Path to MRAID wrapper
MRAID_PATH = Path(__file__).parent / "vendor" / "mraid.js"
MRAID_JS = MRAID_PATH.read_text(encoding="utf-8")


def wrap_with_mraid(html: str, cta_url: str = "https://example.com") -> str:
    """
    Wrap a self-contained HTML game with MRAID 3.0 wrapper.
    
    Injects:
    1. mraid.js before the game script
    2. MRAID initialization (ready call)
    3. CTA handler that calls mraid.open()
    """
    # Ensure we have a CTA URL
    if not cta_url:
        cta_url = "https://example.com"
    
    # Inject MRAID script before </head> or at start of <body>
    if "</head>" in html:
        html = html.replace("</head>", f"<script>{MRAID_JS}</script></head>")
    else:
        html = html.replace("<body>", f"<body><script>{MRAID_JS}</script>")
    
    # Add MRAID CTA hook - inject after window.__GAME__ assignment
    # This patches the game's CTA to use mraid.open()
    mraid_cta_injection = f"""
    // MRAID CTA Integration
    (function() {{
        // Wait for game to be ready
        function initMraidCta() {{
            if (window.__GAME__ && window.__GAME__.scene) {{
                const scenes = window.__GAME__.scene.scenes;
                scenes.forEach(scene => {{
                    if (scene.ctaButton && scene.ctaButton.on) {{
                        // Replace CTA click handler with mraid.open
                        scene.ctaButton.off('pointerdown');
                        scene.ctaButton.on('pointerdown', () => {{
                            if (typeof mraid !== 'undefined' && mraid.open) {{
                                mraid.open("{cta_url}");
                            }} else {{
                                window.open("{cta_url}", "_blank");
                            }}
                        }});
                    }}
                }});
            }} else {{
                setTimeout(initMraidCta, 100);
            }}
        }}
        initMraidCta();
        
        // Call mraid.ready() when game loads
        if (typeof mraid !== 'undefined') {{
            mraid.addEventListener('ready', function() {{
                console.log('MRAID: ready event fired');
            }});
            // Ensure ready is called
            if (mraid.getState() === 'loading') {{
                mraid.ready();
            }}
        }}
    }})();
    """
    
    # Inject before closing </script> tag of the game, or before </body>
    if "</script></body>" in html:
        html = html.replace("</script></body>", f"<script>{mraid_cta_injection}</script></script></body>")
    elif "</script>" in html:
        # Find the last </script> (game script)
        last_script_idx = html.rfind("</script>")
        if last_script_idx > 0:
            html = html[:last_script_idx] + f"<script>{mraid_cta_injection}</script>" + html[last_script_idx:]
    elif "</body>" in html:
        html = html.replace("</body>", f"<script>{mraid_cta_injection}</script></body>")
    
    return html


def create_mraid_package(html: str, cta_url: str = "https://example.com", output_dir = None) -> dict:
    """
    Create a complete MRAID-compliant playable package.
    
    Returns dict with:
    - html: MRAID-wrapped HTML
    - manifest: dict for ad network submission
    """
    wrapped_html = wrap_with_mraid(html, cta_url)
    
    manifest = {
        "version": "1.0",
        "mraid_version": "3.0",
        "format": "playable",
        "cta_url": cta_url,
        "orientation": "portrait",
        "dimensions": {
            "width": 800,
            "height": 600
        },
        "networks": ["google_ads", "unity_ads", "applovin", "ironsource", "vungle", "mintegral"],
        "features": ["resize", "expand", "orientation", "calendar", "store_picture"],
        "entry_point": "index.html"
    }
    
    if output_dir:
        output_dir.mkdir(parents=True, exist_ok=True)
        (output_dir / "index.html").write_text(wrapped_html, encoding="utf-8")
        import json
        (output_dir / "manifest.json").write_text(json.dumps(manifest, indent=2))
        # Copy MRAID JS for reference
        (output_dir / "mraid.js").write_text(MRAID_JS)
    
    return {
        "html": wrapped_html,
        "manifest": manifest
    }