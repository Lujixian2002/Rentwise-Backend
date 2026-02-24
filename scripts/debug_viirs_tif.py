from __future__ import annotations

import math
from pathlib import Path

import numpy as np
import tifffile

from app.core.config import get_settings
from scripts.seed_communities import SEED_ROWS


def main() -> None:
    settings = get_settings()
    tif_path = Path(settings.viirs_local_radiance_tif)
    if not tif_path.exists():
        print(f"Missing file: {tif_path}")
        return

    with tifffile.TiffFile(tif_path) as tif:
        page = tif.pages[0]
        scale_tag = page.tags.get("ModelPixelScaleTag")
        tie_tag = page.tags.get("ModelTiepointTag")
        if not scale_tag or not tie_tag:
            print("Missing georeference tags in tif")
            return
        scale = scale_tag.value
        tie = tie_tag.value
        pixel_scale_x = float(scale[0])
        pixel_scale_y = float(scale[1])
        origin_x = float(tie[3])
        origin_y = float(tie[4])
        height, width = page.shape

    arr = tifffile.memmap(tif_path)
    valid = arr[np.isfinite(arr) & (arr > 0)]

    print("=== TIFF Summary ===")
    print("path:", tif_path)
    print("shape:", arr.shape)
    print("pixel_scale:", pixel_scale_x, pixel_scale_y)
    print("origin:", origin_x, origin_y)
    print(
        "bbox:",
        {
            "west": origin_x,
            "east": origin_x + width * pixel_scale_x,
            "north": origin_y,
            "south": origin_y - height * pixel_scale_y,
        },
    )
    print("valid_ratio:", round(float(valid.size / arr.size), 6))
    if valid.size:
        print("valid_min/max/mean:", float(valid.min()), float(valid.max()), float(valid.mean()))

    print("\n=== Community Sampling (radius=2km) ===")
    for row in SEED_ROWS:
        name = row["community_id"]
        lat = float(row["center_lat"])
        lng = float(row["center_lng"])
        sample = sample_window(arr, lat, lng, origin_x, origin_y, pixel_scale_x, pixel_scale_y, 2.0)
        print(name, sample)


def sample_window(
    arr: np.ndarray,
    center_lat: float,
    center_lng: float,
    origin_x: float,
    origin_y: float,
    pixel_scale_x: float,
    pixel_scale_y: float,
    radius_km: float,
) -> dict:
    height, width = arr.shape
    col = int((center_lng - origin_x) / pixel_scale_x)
    row = int((origin_y - center_lat) / pixel_scale_y)

    in_tile = 0 <= row < height and 0 <= col < width
    if not in_tile:
        return {"in_tile": False, "valid_px": 0, "mean": None}

    lat_delta = radius_km / 111.0
    lon_delta = radius_km / (111.0 * max(0.1, math.cos(math.radians(center_lat))))
    col_radius = max(1, int(math.ceil(lon_delta / pixel_scale_x)))
    row_radius = max(1, int(math.ceil(lat_delta / pixel_scale_y)))

    x0 = max(0, col - col_radius)
    x1 = min(width, col + col_radius + 1)
    y0 = max(0, row - row_radius)
    y1 = min(height, row + row_radius + 1)

    window = arr[y0:y1, x0:x1]
    valid = window[np.isfinite(window) & (window > 0)]
    if valid.size == 0:
        return {"in_tile": True, "valid_px": 0, "mean": None}
    return {"in_tile": True, "valid_px": int(valid.size), "mean": float(valid.mean())}


if __name__ == "__main__":
    main()
