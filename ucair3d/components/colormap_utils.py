# ucair3d/utils/colormap_utils.py
from typing import Optional
import numpy as np
import cmap

def cmap_from_pg(pg_color_map, n: int = 256) -> cmap.Colormap:
    """Convert a pyqtgraph.ColorMap to a cmap.Colormap (float RGBA in [0,1])."""
    lut = pg_color_map.getLookupTable(nPts=n, alpha=True)  # uint8 Nx4
    if lut.ndim != 2 or lut.shape[1] not in (3, 4):
        raise ValueError(f"Unexpected LUT shape: {lut.shape}")
    if lut.shape[1] == 3:  # add opaque alpha if needed
        lut = np.hstack([lut, np.full((lut.shape[0], 1), 255, dtype=lut.dtype)])
    lut = lut.astype(np.float32) / 255.0
    return cmap.Colormap(lut)

def pg_from_cmap(sq_cmap: cmap.Colormap) -> "pyqtgraph.ColorMap":
    """Convert a cmap.Colormap to pyqtgraph.ColorMap."""
    import pyqtgraph as pg
    arr = np.asarray(sq_cmap.colors, dtype=np.float32)  # Nx4 floats [0,1]
    if arr.ndim != 2 or arr.shape[1] not in (3, 4):
        raise ValueError(f"Unexpected colormap array shape: {arr.shape}")
    # pg.ColorMap wants positions + colors; use evenly spaced stops
    pos = np.linspace(0.0, 1.0, arr.shape[0], dtype=np.float32)
    return pg.ColorMap(pos, arr[:, :3], alpha=arr[:, 3] if arr.shape[1] == 4 else None)
