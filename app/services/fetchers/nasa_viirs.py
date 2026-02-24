from __future__ import annotations

import math
from pathlib import Path

from app.core.config import get_settings

try:
    import numpy as np
    import tifffile
except ImportError:  # pragma: no cover - runtime optional dependency
    np = None
    tifffile = None


def fetch_viirs_night_activity_index(center_lat: float, center_lng: float) -> float | None:
    settings = get_settings()
    return _read_local_viirs_index(
        center_lat=center_lat,
        center_lng=center_lng,
        tif_path=settings.viirs_local_radiance_tif,
        radius_km=settings.viirs_sample_radius_km,
    )


def _read_local_viirs_index(center_lat: float, center_lng: float, tif_path: str, radius_km: float) -> float | None:
    if tifffile is None or np is None:
        return None

    path = Path(tif_path)
    if not path.exists():
        return None

    try:
        with tifffile.TiffFile(path) as tif:
            page = tif.pages[0]
            scale_tag = page.tags.get("ModelPixelScaleTag")
            tie_tag = page.tags.get("ModelTiepointTag")
            if not scale_tag or not tie_tag:
                return None
            scale = scale_tag.value
            tie = tie_tag.value
            pixel_scale_x = float(scale[0])
            pixel_scale_y = float(scale[1])
            origin_x = float(tie[3])
            origin_y = float(tie[4])

        arr = tifffile.memmap(path)
    except Exception:
        return None

    if arr.ndim != 2:
        return None

    width = arr.shape[1]
    height = arr.shape[0]

    # Convert geographic coordinate to pixel index (north-up geotiff).
    px = int((center_lng - origin_x) / pixel_scale_x)
    py = int((origin_y - center_lat) / pixel_scale_y)
    if px < 0 or py < 0 or px >= width or py >= height:
        return None

    lat_delta = radius_km / 111.0
    lon_delta = radius_km / (111.0 * max(0.1, math.cos(math.radians(center_lat))))
    px_radius = max(1, int(math.ceil(lon_delta / pixel_scale_x)))
    py_radius = max(1, int(math.ceil(lat_delta / pixel_scale_y)))

    x0 = max(0, px - px_radius)
    x1 = min(width, px + px_radius + 1)
    y0 = max(0, py - py_radius)
    y1 = min(height, py + py_radius + 1)
    window = arr[y0:y1, x0:x1]

    # Remove invalid values (negative / zero background).
    valid = window[np.isfinite(window) & (window > 0)]
    if valid.size == 0:
        return 0.0

    mean_radiance = float(valid.mean())
    # Normalize with log scale: ~0-80 radiance maps to 0-100.
    normalized = min(100.0, max(0.0, (math.log1p(mean_radiance) / math.log1p(80.0)) * 100.0))
    return round(normalized, 2)
