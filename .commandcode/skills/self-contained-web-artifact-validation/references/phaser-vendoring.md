# Phaser Vendoring Reference

## Download Command

```bash
mkdir -p pipeline/vendor
curl -sL "https://cdn.jsdelivr.net/npm/phaser@3.80.1/dist/phaser.min.js" \
  -o pipeline/vendor/phaser.min.js
```

## File Size

- Phaser 3.80.1 minified: ~1.18 MB (1,181,917 bytes)

## Version Pinning

Pin to a specific version (3.80.1) to ensure reproducible builds. Update when intentionally upgrading.

## Alternative: Subset Phaser

For smaller artifacts, consider building a custom Phaser build with only needed modules:
- https://github.com/photonstorm/phaser/tree/v3.80.1#custom-builds
- Can reduce size significantly for simple 2D games