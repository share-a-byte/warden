# Facility model credits

This scene is a simulated pharmaceutical distribution facility, not a real scan or an accurate representation of an existing building.

## Downloaded assets (both CC0)

- **Warehouse building, low poly** — 32kda, OpenGameArt.
  Source: https://opengameart.org/node/175915
  Download: https://opengameart.org/sites/default/files/warehouse02.zip
  License: https://creativecommons.org/publicdomain/zero/1.0/
  Adaptation: resized building shell, removed roof/front facade for cutaway viewing, replaced textures with vertex colors.
- **Modular Industrial Pipes 01** — Jorge Camacho, Poly Haven.
  Source: https://polyhaven.com/a/modular_industrial_pipes_01
  License: https://polyhaven.com/license (CC0)
  Adaptation: reused valve/flange/pipe geometry in mechanical assemblies; replaced materials.

Additional framing, racks, tanks, ducts, conveyors and service fixtures were generated for this demo. Refrigeration units and sensor locations are simulated interactive overlays.

The point cloud is deterministically sampled from the composed mesh surfaces (350,000 points), with height-based display colors. It is not LiDAR measurement data.

Generated with scripts/build-facility.mjs. Source downloads are in work/facility-assets (not required at runtime). All runtime geometry is hosted locally under public/models/facility.
