"""
Spill Sense ML Detection Pipeline
================================

Two-stage computer-vision pipeline for oil spill detection in satellite SAR
(Synthetic Aperture Radar) imagery:

  1. UNET SEGMENTATION
     A U-Net convolutional network classifies every pixel as "oil slick"
     (1) or "open water" (0). The architecture is fully trainable from
     scratch -- see ``train_unet.py``.

  2. DBSCAN CLUSTERING
     The segmented oil pixels are clustered into distinct spill objects
     with DBSCAN (scikit-learn). Scattered single-pixel noise is discarded
     and every surviving cluster is converted into a geographic polygon
     (GeoJSON) ready to be drawn on the Leaflet map.

Prototype behaviour
-------------------
* If a trained checkpoint exists at ``server/checkpoints/unet_oil_spill.pth``
  and torch is installed, inference runs through the *real* model.
* Otherwise the module synthesises a SAR-like scene and uses its ground-truth
  mask (lightly perturbed) so the entire pipeline -- segmentation --> DBSCAN
  --> polygon extraction --> GeoJSON -- can be exercised end-to-end with zero
  ML dependencies installed.
* If scikit-learn is missing, a small 4-connectivity fallback clustering is
  used and flagged in the response (``dbscan_engine``).
"""

from __future__ import annotations

import base64
import io
import math
import os
import random
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

# ---------------------------------------------------------------------------
# Optional dependency detection
# ---------------------------------------------------------------------------
try:
    import numpy as np

    HAS_NUMPY = True
except ImportError:  # pragma: no cover - optional dependency
    np = None
    HAS_NUMPY = False

try:
    import torch
    import torch.nn as nn
    import torch.nn.functional as F

    HAS_TORCH = True
except ImportError:  # pragma: no cover - optional dependency
    torch = None
    nn = None
    F = None
    HAS_TORCH = False

try:
    from sklearn.cluster import DBSCAN as _SKLEARN_DBSCAN

    HAS_SKLEARN = True
except ImportError:  # pragma: no cover - optional dependency
    _SKLEARN_DBSCAN = None
    HAS_SKLEARN = False

try:
    from PIL import Image

    HAS_PIL = True
except ImportError:  # pragma: no cover - optional dependency
    Image = None
    HAS_PIL = False

# ---------------------------------------------------------------------------
# Paths / constants
# ---------------------------------------------------------------------------
CHECKPOINT_DIR = Path(__file__).resolve().parent / "checkpoints"
CHECKPOINT_PATH = CHECKPOINT_DIR / "unet_oil_spill.pth"
DEFAULT_CHECKPOINT_NAME = "unet_oil_spill.pth"


def model_status() -> Dict[str, Any]:
    """Report which pieces of the ML stack are currently available."""
    return {
        "torch_available": HAS_TORCH,
        "sklearn_available": HAS_SKLEARN,
        "numpy_available": HAS_NUMPY,
        "checkpoint_exists": has_checkpoint(),
        "checkpoint_path": str(CHECKPOINT_PATH),
        "pipeline_ready": bool(HAS_TORCH and has_checkpoint()),
        "mode": "real" if (HAS_TORCH and has_checkpoint()) else "demo",
    }


def has_checkpoint() -> bool:
    try:
        return CHECKPOINT_PATH.is_file()
    except OSError:
        return False


# ===========================================================================
# U-NET MODEL (trainable from scratch)
# ===========================================================================
if torch is not None and nn is not None and F is not None:

    class DoubleConv(nn.Module):
        """(Conv3x3 -> BatchNorm -> ReLU) x 2"""

        def __init__(self, in_ch: int, out_ch: int, mid_ch: Optional[int] = None):
            super().__init__()
            assert nn is not None
            mid_ch = mid_ch or out_ch
            self.conv = nn.Sequential(
                nn.Conv2d(in_ch, mid_ch, kernel_size=3, padding=1, bias=False),
                nn.BatchNorm2d(mid_ch),
                nn.ReLU(inplace=True),
                nn.Conv2d(mid_ch, out_ch, kernel_size=3, padding=1, bias=False),
                nn.BatchNorm2d(out_ch),
                nn.ReLU(inplace=True),
            )

        def forward(self, x):
            return self.conv(x)

    class Down(nn.Module):
        """MaxPool2d -> DoubleConv"""

        def __init__(self, in_ch: int, out_ch: int):
            super().__init__()
            assert nn is not None
            self.mpconv = nn.Sequential(nn.MaxPool2d(2), DoubleConv(in_ch, out_ch))

        def forward(self, x):
            return self.mpconv(x)

    class Up(nn.Module):
        """Transpose-conv upsample -> concat skip -> DoubleConv"""

        def __init__(self, in_ch: int, out_ch: int):
            super().__init__()
            assert nn is not None
            self.up = nn.ConvTranspose2d(in_ch, in_ch // 2, kernel_size=2, stride=2)
            self.conv = DoubleConv(in_ch, out_ch)

        def forward(self, x1, x2):
            x1 = self.up(x1)
            # Align dimensions when upsampling yields odd sizes
            if x1.size(2) != x2.size(2) or x1.size(3) != x2.size(3):
                assert F is not None
                x1 = F.interpolate(x1, size=(x2.size(2), x2.size(3)), mode="bilinear", align_corners=True)
            assert torch is not None
            x = torch.cat([x2, x1], dim=1)
            return self.conv(x)

    class UNet(nn.Module):
        """Classic encoder-decoder U-Net for binary segmentation.

        Input :  (N, 1, H, W)  grayscale SAR patch, normalised 0..1
        Output:  (N, 1, H, W)  raw logits (apply sigmoid for probabilities)
        """

        def __init__(self, in_channels: int = 1, base: int = 32):
            super().__init__()
            assert nn is not None
            self.inc = DoubleConv(in_channels, base)
            self.d1 = Down(base, base * 2)
            self.d2 = Down(base * 2, base * 4)
            self.d3 = Down(base * 4, base * 8)
            self.u1 = Up(base * 8, base * 4)
            self.u2 = Up(base * 4, base * 2)
            self.u3 = Up(base * 2, base)
            self.outc = nn.Conv2d(base, 1, kernel_size=1)

        def forward(self, x):
            s0 = self.inc(x)
            s1 = self.d1(s0)
            s2 = self.d2(s1)
            x3 = self.d3(s2)
            x = self.u1(x3, s2)
            x = self.u2(x, s1)
            x = self.u3(x, s0)
            return self.outc(x)


def run_unet_probabilities(
    patch: Any,
    checkpoint: Path = CHECKPOINT_PATH,
) -> Optional[Any]:
    """Run the trained U-Net on a grayscale SAR patch.

    Returns per-pixel oil probabilities when torch + a checkpoint are
    available, otherwise ``None`` (the caller falls back to demo mode).
    """
    if (
        torch is None
        or nn is None
        or F is None
        or np is None
        or not checkpoint
        or not Path(checkpoint).is_file()
    ):
        return None

    try:
        state = torch.load(
            str(checkpoint),
            map_location="cpu",
            weights_only=False,
        )
        if isinstance(state, dict) and "state_dict" in state:
            config = state.get("config", {})
            model = UNet(
                in_channels=int(config.get("input_channels", 1)),
                base=int(config.get("base", 32)),
            )
            state = state["state_dict"]
        else:
            model = UNet()
        model.load_state_dict(state)
        model.eval()
    except Exception as exc:  # pragma: no cover - defensive
        print(f"Spill Sense: could not load UNet checkpoint ({exc}); using demo mode.")
        return None

    patch = np.asarray(patch, dtype=np.float32)
    if patch.ndim == 3:
        patch = patch.mean(axis=2)
    h, w = patch.shape
    pad_h = (16 - h % 16) % 16
    pad_w = (16 - w % 16) % 16
    if pad_h or pad_w:
        patch = np.pad(patch, ((0, pad_h), (0, pad_w)), mode="edge")

    tensor = torch.from_numpy(patch / 255.0).unsqueeze(0).unsqueeze(0)
    with torch.no_grad():
        logits = model(tensor)
        prob = torch.sigmoid(logits)[0, 0, :h, :w].numpy()

    return prob


def run_unet_inference(
    patch: Any,
    checkpoint: Path = CHECKPOINT_PATH,
    threshold: float = 0.5,
) -> Optional[Any]:
    """Run the trained U-Net and return a binary 0/1 uint8 oil mask."""
    probabilities = run_unet_probabilities(patch, checkpoint)
    if probabilities is None:
        return None
    if np is None:  # pragma: no cover - probabilities require numpy
        raise RuntimeError("numpy is required for U-Net inference.")
    return (probabilities >= threshold).astype(np.uint8)


# ===========================================================================
# SYNTHETIC SAR SCENE (offline demo fallback)
# ===========================================================================
def synthesize_sar_patch(size: int = 256, seed: Optional[int] = None) -> Tuple[Any, Any]:
    """Create a SAR-like grayscale patch containing several dark oil slicks.

    Returns ``(image, mask_gt)``. ``image`` is uint8 0..255 with speckle-style
    noise and broad brightness variation (SAR look). ``mask_gt`` is uint8
    0/1 marking the true slick pixels.

    Requires numpy; raises a clear error if it is missing.
    """
    if np is None:  # pragma: no cover - numpy ships with requirements.txt
        raise RuntimeError(
            "numpy is required for the Spill Sense ML pipeline. "
            "Install it with: pip install numpy"
        )

    if seed is not None:
        random.seed(seed)

    rng = np.random.default_rng(seed)
    size = int(size)

    # Sea surface speckle + large-scale brightness variation (SAR texture)
    img = rng.normal(140.0, 16.0, (size, size)).astype(np.float32)
    yy, xx = np.mgrid[0:size, 0:size].astype(np.float32)
    img += 22.0 * np.sin(2.0 * np.pi * yy / size) * np.cos(2.0 * np.pi * xx / size)
    img += rng.normal(0.0, 5.5, (size, size))

    mask = np.zeros((size, size), dtype=np.uint8)

    # A few separate irregular ellipses = distinct oil slicks. Centers are
    # kept well apart so DBSCAN recovers them as separate clusters.
    n_slicks = 3 + rng.integers(0, 3)
    centers = []
    for _ in range(int(n_slicks)):
        for _attempt in range(120):
            cx = rng.uniform(0.25, 0.75) * size
            cy = rng.uniform(0.25, 0.75) * size
            if all(math.hypot(cx - ox, cy - oy) >= size * 0.30 for ox, oy in centers):
                break
        centers.append((float(cx), float(cy)))

        a = rng.uniform(size * 0.08, size * 0.15)
        b = rng.uniform(size * 0.045, size * 0.10)
        rot = rng.uniform(0.0, np.pi)
        warp = rng.uniform(0.6, 1.15)

        d = (
            (((xx - cx) * np.cos(rot) + (yy - cy) * np.sin(rot)) / a) ** 2
            + (((-(xx - cx) * np.sin(rot) + (yy - cy) * np.cos(rot)) / (b * warp))) ** 2
        )
        blob = d < 1.0
        mask[blob] = 1

    # Oil dams the surface waves => darker radar return in the mask region
    damp = rng.normal(52.0, 12.0, (size, size)).astype(np.float32)
    img[mask > 0] -= damp[mask > 0]

    img = np.clip(img, 0.0, 255.0)
    return np.clip(img, 0, 255).astype(np.uint8), mask


def _mock_segmentation_mask(mask_gt: Any, seed: int = 7) -> Any:
    """Perturb a ground-truth mask to simulate imperfect CNN segmentation."""
    if np is None:  # pragma: no cover - required by the demo pipeline
        raise RuntimeError("numpy is required for the Spill Sense ML pipeline.")
    predicted = np.array(mask_gt, copy=True)
    flip = np.random.default_rng(seed).random(predicted.shape)
    predicted[flip < 0.012] = 1 - predicted[flip < 0.012]  # ~1.2% salt & pepper
    return predicted


# ===========================================================================
# DBSCAN-BASED CLUSTERING OF OIL PIXELS
# ===========================================================================
def _grid_connectivity_labels(coords: List[Tuple[float, float]], eps_px: int) -> List[int]:
    """Very small pure-Python 4-connectivity fallback used when scikit-learn
    is not installed. Merges any pixels within ``eps_px`` Chebyshev distance."""
    coords = list(coords)
    labels: List[int] = [-1] * len(coords)
    lookup: Dict[Tuple[float, float], int] = {}
    next_label = 0

    for idx, (x, y) in enumerate(coords):
        found = None
        for dx in range(-eps_px, eps_px + 1):
            for dy in range(-eps_px, eps_px + 1):
                if dx * dx + dy * dy > eps_px * eps_px:
                    continue
                buddy = lookup.get((x + dx, y + dy))
                if buddy is not None:
                    found = buddy
                    break
            if found is not None:
                break
        if found is None:
            lookup[(x, y)] = next_label
            labels[idx] = next_label
            next_label += 1
        else:
            lookup[(x, y)] = found
            labels[idx] = found
    return labels


def cluster_oil_pixels(
    coords: Any,
    eps_px: float = 3.0,
    min_samples: int = 8,
) -> Tuple[List[int], str]:
    """Cluster oil-pixel coordinates into distinct spill objects with DBSCAN.

    ``coords`` can be an (N, 2) numpy array or an iterable of (x, y) tuples.
    Returns ``(labels, engine_name)`` where ``engine_name`` documents whether
    real scikit-learn DBSCAN or the fallback was used. Label ``-1`` = noise.
    """
    if HAS_SKLEARN and _SKLEARN_DBSCAN is not None:
        if HAS_NUMPY and np is not None:
            coords = np.asarray(coords, dtype=np.float64)
            if coords.ndim != 2 or coords.shape[0] == 0:
                return [], "scikit-learn DBSCAN"
            if coords.shape[0] > 20000:  # cap for memory safety on big masks
                keep = np.random.default_rng(0).choice(
                    coords.shape[0], 20000, replace=False
                )
                coords = coords[keep]
            labels = _SKLEARN_DBSCAN(
                eps=eps_px, min_samples=min_samples, n_jobs=1
            ).fit_predict(coords)
            return labels.tolist(), "scikit-learn DBSCAN"
        coords = [(float(c[0]), float(c[1])) for c in coords]
        return _grid_connectivity_labels(coords, int(math.ceil(eps_px))), "scikit-learn unavailable (fallback)"

    pts = [(float(c[0]), float(c[1])) for c in coords]
    return _grid_connectivity_labels(pts, int(math.ceil(eps_px))), "fallback (install scikit-learn for DBSCAN)"


# ===========================================================================
# POLYGON EXTRACTION (convex hull via monotone chain)
# ===========================================================================
def convex_hull(points: List[Tuple[float, float]]) -> List[Tuple[float, float]]:
    """Monotone-chain convex hull; returns hull vertices in CCW order."""
    pts = sorted(set((float(x), float(y)) for x, y in points))
    if len(pts) <= 2:
        return pts

    def cross(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

    lower: List[Tuple[float, float]] = []
    for p in pts:
        while len(lower) >= 2 and cross(lower[-2], lower[-1], p) <= 0:
            lower.pop()
        lower.append(p)

    upper: List[Tuple[float, float]] = []
    for p in reversed(pts):
        while len(upper) >= 2 and cross(upper[-2], upper[-1], p) <= 0:
            upper.pop()
        upper.append(p)

    return lower[:-1] + upper[:-1]


def pixel_to_latlon(
    x: float,
    y: float,
    width: int,
    height: int,
    center_lat: float,
    center_lon: float,
    resolution_m: float,
) -> Tuple[float, float]:
    """Map an image pixel to geographic coordinates (lat, lon).

    The image centre corresponds to ``(center_lat, center_lon)``; rows grow
    southward, columns grow eastward (top-left origin, standard image order).
    """
    meters_per_deg_lat = 111320.0
    meters_per_deg_lon = 111320.0 * math.cos(math.radians(center_lat)) or 111320.0

    col_offset = x - (width - 1) / 2.0
    row_offset = y - (height - 1) / 2.0

    dlat = row_offset * resolution_m / meters_per_deg_lat
    dlon = col_offset * resolution_m / meters_per_deg_lon

    return center_lat - dlat, center_lon + dlon


def _mask_to_binary(mask: Any) -> Any:
    if np is None:  # pragma: no cover - required by the detection pipeline
        raise RuntimeError("numpy is required for the Spill Sense ML pipeline.")
    return np.asarray(mask > 0, dtype=np.uint8)


# ===========================================================================
# MAIN PIPELINE
# ===========================================================================
def run_detection(
    center_lat: float = 2.3812,
    center_lon: float = 101.9124,
    resolution_m: float = 10.0,
    patch_size: int = 256,
    threshold: float = 0.5,
    eps_px: float = 3.0,
    min_samples: int = 8,
    min_pixels: int = 25,
    image_patch: Optional[Any] = None,
    invalid_mask: Optional[Any] = None,
    pixel_to_geo: Optional[Callable[[float, float], Tuple[float, float]]] = None,
    pixel_area_km2: Optional[float] = None,
    input_source: str = "synthetic",
) -> Dict[str, Any]:
    """Run the full segmentation + clustering pipeline and return GeoJSON.

    This is the endpoint handler's workhorse. Docstring output structure:

    {
      "status": "ok",
      "mode": "real" | "demo",
      "engines": {...model_status()...},
      "dbscan_engine": "scikit-learn DBSCAN" | "fallback ...",
      "input": {...},
      "segmentation": {"oil_pixels": int, "oil_ratio_pct": float},
      "clusters": [...summary...],
      "polygons": {GeoJSON FeatureCollection},
      "preview_png_b64": str | None,
    }
    """
    if np is None:  # pragma: no cover
        raise RuntimeError("numpy is required for the Spill Sense ML pipeline.")

    if image_patch is None:
        patch, mask_gt = synthesize_sar_patch(size=patch_size)
    else:
        patch = np.asarray(image_patch)
        if patch.ndim != 2 or not patch.size:
            raise ValueError("Detection image must be a non-empty grayscale patch.")
        mask_gt = None
    height, width = patch.shape

    if invalid_mask is not None:
        invalid_mask = np.asarray(invalid_mask, dtype=bool)
        if invalid_mask.shape != patch.shape:
            raise ValueError("Invalid-pixel mask must match the image dimensions.")

    # --- Stage 1: UNet segmentation (real model OR demo mask) ---------------
    probabilities = run_unet_probabilities(patch, CHECKPOINT_PATH)
    mode = "real" if probabilities is not None else "demo"
    if probabilities is None:
        if mask_gt is None:
            raise RuntimeError("A trained U-Net checkpoint is required for supplied imagery.")
        predicted = _mock_segmentation_mask(mask_gt)
    else:
        predicted = probabilities >= threshold
    predicted = _mask_to_binary(predicted)
    if invalid_mask is not None:
        predicted[invalid_mask] = 0

    ys, xs = np.nonzero(predicted)
    oil_pixels = int(len(xs))
    if oil_pixels > 20000:
        raise ValueError(
            "Predicted mask exceeds the 20,000-pixel clustering limit; "
            "use a lower-resolution input or adjust the detection threshold."
        )

    # --- Stage 2: DBSCAN clustering of oil pixels ---------------------------
    labels, engine_name = cluster_oil_pixels(
        np.stack([xs, ys], axis=1), eps_px=eps_px, min_samples=min_samples
    )

    clusters = []
    features = []
    cluster_ids = sorted({int(l) for l in labels if int(l) != -1})

    for cid in cluster_ids:
        idxs = [i for i, l in enumerate(labels) if int(l) == cid]
        if len(idxs) < min_pixels:
            continue

        cx = xs[idxs]
        cy = ys[idxs]

        if probabilities is not None:
            score_type = "mean_model_probability"
            score = float(np.mean(probabilities[cy, cx]))
        else:
            if mask_gt is None:
                raise RuntimeError("Synthetic ground truth is unavailable for demo scoring.")
            score_type = "synthetic_ground_truth_agreement"
            score = float(np.mean(mask_gt[cy, cx] > 0))

        pts = list(zip([float(v) for v in cx], [float(v) for v in cy]))
        hull = convex_hull(pts)

        if pixel_to_geo is None:
            geographic_points = [
                pixel_to_latlon(
                    px, py, width, height, center_lat, center_lon, resolution_m
                )
                for px, py in hull
            ]
            centroid_lat, centroid_lon = pixel_to_latlon(
                float(np.mean(cx)), float(np.mean(cy)), width, height,
                center_lat, center_lon, resolution_m,
            )
        else:
            geographic_points = [pixel_to_geo(px, py) for px, py in hull]
            centroid_lat, centroid_lon = pixel_to_geo(
                float(np.mean(cx)), float(np.mean(cy))
            )
        ring = [[(lon, lat) for lat, lon in geographic_points]]
        # Close the ring
        ring[0].append(ring[0][0])

        area_km2 = len(idxs) * (
            pixel_area_km2
            if pixel_area_km2 is not None
            else (resolution_m / 1000.0) ** 2
        )

        clusters.append({
            "cluster_id": int(cid),
            "oil_pixels": int(len(idxs)),
            "area_km2": round(area_km2, 4),
            "score_pct": round(score * 100.0, 1),
            "score_type": score_type,
            "centroid": [round(centroid_lat, 6), round(centroid_lon, 6)],
        })
        features.append({
            "type": "Feature",
            "properties": {
                "cluster_id": int(cid),
                "area_km2": round(area_km2, 4),
                "oil_pixels": int(len(idxs)),
                "score_pct": round(score * 100.0, 1),
                "score_type": score_type,
                "centroid": [round(centroid_lat, 6), round(centroid_lon, 6)],
            },
            "geometry": {"type": "Polygon", "coordinates": ring},
        })

    features.sort(key=lambda f: f["properties"]["area_km2"], reverse=True)

    return {
        "status": "ok",
        "mode": mode,
        "dbscan_engine": engine_name,
        "dbscan_params": {
            "eps_px": eps_px,
            "min_samples": min_samples,
            "min_pixels": min_pixels,
        },
        "input": {
            "source": input_source,
            "center_lat": center_lat,
            "center_lon": center_lon,
            "resolution_m": resolution_m,
            "patch_size": patch_size if image_patch is None else height,
            "image_width": width,
            "image_height": height,
            "threshold": threshold,
        },
        "segmentation": {
            "oil_pixels": oil_pixels,
            "oil_ratio_pct": round(100.0 * oil_pixels / (patch_size * patch_size), 3),
        },
        "clusters": clusters,
        "polygons": {
            "type": "FeatureCollection",
            "features": features,
        },
        "preview_png_b64": _build_preview_png(patch, mask_gt, predicted),
        "warning": (
            "Investigation support, not final proof. Model scores are not "
            "validated for real-world oil-spill accuracy."
        ),
    }


def run_detection_on_geotiff(
    geotiff_data: bytes,
    backscatter_min_db: float = -30.0,
    backscatter_max_db: float = 0.0,
    threshold: float = 0.5,
    max_dimension: int = 256,
) -> Dict[str, Any]:
    """Detect on a single-band, metre-projected GeoTIFF with dB backscatter."""
    if not math.isfinite(backscatter_min_db) or not math.isfinite(backscatter_max_db):
        raise ValueError("Backscatter dB bounds must be finite numbers.")
    if backscatter_min_db >= backscatter_max_db:
        raise ValueError("backscatter_min_db must be less than backscatter_max_db.")
    if max_dimension < 16:
        raise ValueError("max_dimension must be at least 16 pixels.")
    if not geotiff_data:
        raise ValueError("GeoTIFF upload is empty.")
    if torch is None or not has_checkpoint():
        raise RuntimeError("A trained U-Net checkpoint is required for satellite imagery.")
    if np is None:
        raise RuntimeError("numpy is required for GeoTIFF inference.")

    try:
        from rasterio.errors import RasterioError
        from rasterio.enums import Resampling
        from rasterio.io import MemoryFile
        from rasterio.transform import Affine
        from rasterio.warp import transform as transform_coordinates
    except ImportError as exc:  # pragma: no cover - depends on optional ML dependencies
        raise RuntimeError(
            "GeoTIFF support requires rasterio. Install requirements-ml.txt."
        ) from exc

    with MemoryFile(geotiff_data) as memory_file:
        try:
            dataset_context = memory_file.open()
        except RasterioError as exc:
            raise ValueError("Upload is not a readable GeoTIFF.") from exc
        with dataset_context as dataset:
            if dataset.count != 1:
                raise ValueError(
                    "GeoTIFF must contain exactly one band; select one calibrated polarization."
                )
            if dataset.crs is None or not dataset.crs.is_projected:
                raise ValueError("GeoTIFF must have a projected coordinate reference system.")
            unit_name, unit_conversion_factor = dataset.crs.linear_units_factor
            if unit_name.lower() not in {"metre", "meter"}:
                raise ValueError("GeoTIFF projected coordinates must use metres.")
            if dataset.width < 1 or dataset.height < 1:
                raise ValueError("GeoTIFF dimensions must be non-zero.")

            scale = min(1.0, max_dimension / max(dataset.width, dataset.height))
            width = max(1, int(round(dataset.width * scale)))
            height = max(1, int(round(dataset.height * scale)))
            source = dataset.read(
                1,
                out_shape=(height, width),
                masked=True,
                resampling=Resampling.bilinear,
            )
            source = np.ma.asarray(source, dtype=np.float32)
            invalid = np.ma.getmaskarray(source) | ~np.isfinite(source.filled(np.nan))
            backscatter = source.filled(backscatter_min_db)
            normalized = np.clip(
                (backscatter - backscatter_min_db)
                / (backscatter_max_db - backscatter_min_db),
                0.0,
                1.0,
            )
            image_patch = np.rint(normalized * 255.0).astype(np.uint8)
            image_patch[invalid] = 0

            image_transform = dataset.transform @ Affine.scale(
                dataset.width / width,
                dataset.height / height,
            )
            pixel_area_km2 = abs(
                image_transform.a * image_transform.e
                - image_transform.b * image_transform.d
            ) * unit_conversion_factor**2 / 1_000_000.0
            if not math.isfinite(pixel_area_km2) or pixel_area_km2 <= 0:
                raise ValueError("GeoTIFF has an invalid pixel-to-ground transform.")
            source_crs = dataset.crs

    def pixel_to_geo(column: float, row: float) -> Tuple[float, float]:
        easting, northing = image_transform @ (column + 0.5, row + 0.5)
        coordinates = transform_coordinates(
            source_crs, "EPSG:4326", [easting], [northing]
        )
        longitudes, latitudes = coordinates[0], coordinates[1]
        return latitudes[0], longitudes[0]

    center_lat, center_lon = pixel_to_geo((width - 1) / 2, (height - 1) / 2)
    result = run_detection(
        center_lat=center_lat,
        center_lon=center_lon,
        resolution_m=math.sqrt(pixel_area_km2) * 1000.0,
        patch_size=height,
        threshold=threshold,
        image_patch=image_patch,
        invalid_mask=invalid,
        pixel_to_geo=pixel_to_geo,
        pixel_area_km2=pixel_area_km2,
        input_source="sentinel1_geotiff",
    )
    result["input"]["backscatter_min_db"] = backscatter_min_db
    result["input"]["backscatter_max_db"] = backscatter_max_db
    return result


def _build_preview_png(patch: Any, mask_gt: Any, predicted: Any) -> Optional[str]:
    """Render a small composite preview (SAR | segmentation overlay) as a
    base64 PNG data-URI. Returns None when Pillow is unavailable."""
    if not HAS_PIL or Image is None or np is None:
        return None
    try:
        height, width = patch.shape
        rgb = np.zeros((height, width * 2, 3), dtype=np.uint8)
        # Left: raw SAR patch
        rgb[:, :width, :] = np.stack([patch] * 3, axis=-1)
        # Right: dark panel, amber where segmented oil
        rgb[:, width:, :] = (16, 24, 40)
        overlay = (predicted > 0)
        rgb[:, width:, :][overlay] = (255, 130, 40)

        buf = io.BytesIO()
        Image.fromarray(rgb).save(buf, format="PNG")
        return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode("ascii")
    except Exception:  # pragma: no cover - cosmetic feature
        return None


if __name__ == "__main__":  # pragma: no cover
    import json

    result = run_detection()
    print("status      :", result["status"])
    print("mode        :", result["mode"])
    print("dbscan      :", result["dbscan_engine"])
    print("oil pixels  :", result["segmentation"]["oil_pixels"])
    print("clusters    :", len(result["clusters"]))
    print("preview     :", "yes" if result["preview_png_b64"] else "no")
    for c in result["clusters"]:
        print("  ", c)
    print(json.dumps(result, indent=2)[:2000])