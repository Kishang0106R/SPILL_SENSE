# Spill Sense Backend

This project now includes a lightweight FastAPI backend for vessel matching, suspect ranking, and drift analysis.

## Prerequisites

- Python 3.10+
- pip
- PostgreSQL 14+

## Install dependencies

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

Set the PostgreSQL connection string before starting the API. PowerShell example:

```powershell
$env:DATABASE_URL = "postgresql://postgres:postgres@localhost:5432/spillguard"
```

To provision a local PostgreSQL database, run
`createdb -h 127.0.0.1 -U postgres spillguard`, then set `DATABASE_URL` to a PostgreSQL URI such as
`postgresql://spillguard_app:YOUR_PASSWORD@127.0.0.1:5432/spillguard`. Replace
the example role and password with credentials provisioned in PostgreSQL, and
percent-encode reserved characters in URI credentials. The role needs
permission to create tables and indexes in the `spillguard` database. Schema
creation and initial data seeding are performed in one transaction; the seed
check takes a table lock so concurrent API workers cannot seed duplicate data.

## Real emergency delivery

The emergency buttons use demo mode by default. For production delivery, set
`EMERGENCY_ALERT_MODE=production` and configure Twilio for SMS plus an HTTPS
authority gateway. Keep these values in Vercel Environment Variables; never
commit them.

```powershell
$env:EMERGENCY_ALERT_MODE = "production"
$env:TWILIO_ACCOUNT_SID = "AC..."
$env:TWILIO_AUTH_TOKEN = "..."
$env:TWILIO_FROM_NUMBER = "+15551234567"
$env:EMERGENCY_SMS_TO = "+15557654321"
$env:EMERGENCY_OFFICIAL_WEBHOOK_URL = "https://authority.example.gov/spill-alerts"
```

`SEND VIA SMS` sends through Twilio. `SEND OFFICIAL ALERT` posts the complete
alert payload to `EMERGENCY_OFFICIAL_WEBHOOK_URL`.

For local PostgreSQL, create the `spillguard` database first. The API creates
its tables and seeds the initial dashboard data on startup. With Supabase, use
the PostgreSQL database named in the Supabase connection URI.

## Supabase setup

Create a Supabase project, then open **Connect** in the project dashboard and
copy a PostgreSQL connection URI. For a local Windows machine, use the
**Session pooler** URI if the direct database host is unreachable over IPv6.
The Supabase database password is set for the project; it is not the Supabase
anon key, service-role key, or AISStream key. Keep the URI private.

In the same PowerShell window used to start FastAPI, set the copied URI and the
AISStream key:

```powershell
$env:DATABASE_URL = 'paste-the-Supabase-PostgreSQL-URI-here'
$env:AISSTREAM_API_KEY = 'paste-your-AISStream-key-here'
$env:AIS_TRACK_RETENTION_DAYS = '30'
uvicorn server.api:app --reload --host 127.0.0.1 --port 8000
```

Use the complete URI supplied by Supabase, including its SSL parameters. If the
URI does not contain `sslmode`, the backend requires TLS for remote database
hosts. Connection pooling is enabled with a maximum of five server connections
per API process; prepared statements are disabled for compatibility with
Supabase's transaction pooler. The application creates its tables and indexes
on startup and enables row-level security on its tables. All database access
must go through this backend; do not expose the database URI or add anonymous
RLS policies for these tables.

Verify the database connection at `http://127.0.0.1:8000/api/database/status`.
A successful response reports the PostgreSQL database, role, and server
version. `503` means FastAPI cannot connect; check that the URI is copied
correctly, the database password is correct, and your network can reach the
selected Supabase endpoint. The endpoint does not return credentials.

## Run the backend

Register for a free AISStream key at
[aisstream.io](https://aisstream.io/authenticate). Set it in the backend
environment; do not put the key in `js/config.js`, frontend code, or a committed
file:

```powershell
$env:AISSTREAM_API_KEY = "YOUR_AISSTREAM_KEY"
$env:AIS_TRACK_RETENTION_DAYS = "30"
```

With the key set, the FastAPI process runs the AISStream WebSocket receiver and
stores the latest vessel state plus one position sample per vessel per minute
in PostgreSQL. Track samples older than 30 days are pruned every six hours.
The browser reads up to 200 current vessels in the map viewport and a
five-minute display sample of the last six hours of tracks. The database still
retains minute-level samples for 30 days.
Without a key or available live positions, the map labels its fallback as demo
simulation.

AISStream is a live feed, not a historical replay service, and provides no
delivery guarantee. This setup subscribes to the whole world; that can produce
high traffic and exceed a local machine's capacity. Start one API worker only,
watch the API logs and `/api/ais/status`, and narrow the subscription area if
messages are dropped or PostgreSQL cannot keep up. Do not use Vercel functions
as the WebSocket receiver; run the receiver in a continuously running process.

```bash
uvicorn server.api:app --reload --host 127.0.0.1 --port 8000
```

Then open:

```text
http://127.0.0.1:8000
```

If PostgreSQL is unavailable, the API uses a 3-second connection timeout so the
static site can still load with its bundled demo data instead of waiting indefinitely.

## Available endpoints

- `POST /api/match-vessels`
- `POST /api/sar-ais/candidates` — query stored AIS positions near a SAR observation for investigative review; requires an ISO-8601 acquisition timestamp with a UTC offset, target coordinates, and supports optional time-window/radius limits
- `POST /api/sar-ais/correlate` — correlate a SAR target to caller-supplied AIS records
- `POST /api/rank-suspects`
- `POST /api/drift`
- `GET /api/health`
- `GET /api/database/status` — verify the PostgreSQL/Supabase connection
- `GET /api/bootstrap`
- `GET /api/ais/status` — AISStream configuration and connection status
- `GET /api/ais/vessels?min_lat=...&min_lon=...&max_lat=...&max_lon=...` — up to 200 current ships and decimated six-hour tracks in a bounding box
- `GET /api/detect/model` — ML stack status (torch/sklearn/checkpoint)
- `GET /api/detect/demo?lat=2.3812&lon=101.9124&resolution_m=10&patch_size=256` — run the UNet + DBSCAN detection pipeline
- `POST /api/detect/image?backscatter_min_db=-30&backscatter_max_db=0` — detect on a binary single-band Sentinel-1 GeoTIFF upload
- `POST /api/detect/image/candidates?sar_time=2025-01-01T12:00:00Z&drift_hours=12` — run GeoTIFF detection, backtrack each cluster using hourly environmental vectors, then search stored AIS positions near the estimated source position/time; requires the actual timezone-aware acquisition time

The AIS candidate endpoint returns heuristic proximity/timing evidence, not proof
that a vessel caused a spill. The integrated image endpoint retrieves recent
hourly ocean-current data from the [Open-Meteo Marine API](https://open-meteo.com/en/docs/marine-weather-api)
and 10 m wind data from the [Open-Meteo Forecast API](https://open-meteo.com/en/docs),
then integrates current plus a configurable windage coefficient backward for 6,
12, 24, or 48 hours (`drift_hours`, default 12).
The integration treats current direction as flow-toward and reverses the
meteorological wind direction (which indicates where wind comes from).
`windage_coefficient` defaults to 0.03 and `drift_uncertainty_km` defaults to
5 km; the latter expands the AIS search radius and is an analyst buffer, not a
statistical confidence interval. Environmental vectors are sampled at each
slick centroid and held spatially constant along the backtracked path. If either
source lacks required hourly values or is unavailable, the response marks drift
as unavailable and searches around the observed slick instead of treating
missing environmental data as zero. The integrated image endpoint does not
infer an acquisition timestamp from GeoTIFF metadata; callers must provide
`sar_time`. Open-Meteo model output is environmental context, not a validated
oil-spill trajectory forecast.

## ML Detection Pipeline (UNet + DBSCAN)

The dashboard's **"Run ML Detection"** button runs a two-stage pipeline on SAR imagery:

1. **UNet segmentation** — a fully trainable U-Net classifies each pixel as oil / open water.
2. **DBSCAN clustering** — oil pixels are clustered into distinct spill objects, noise is discarded, and each cluster is emitted as a GeoJSON polygon rendered on the Leaflet map.

Cluster results report `score_pct` with a `score_type`: real inference uses the mean U-Net oil probability across the cluster (`mean_model_probability`), while demo mode reports overlap with its synthetic ground-truth mask (`synthetic_ground_truth_agreement`). These scores are not calibrated real-world confidence estimates.

### Demo mode (works immediately, zero heavy deps)

Without PyTorch or a trained checkpoint the API **synthesises a SAR-style scene**, simulates the segmentation mask, and still runs the **real DBSCAN** clustering + polygon extraction — so the whole flow works end-to-end as soon as you start the server.

### Analyze an image

The image endpoint accepts a binary GeoTIFF request body (`Content-Type: image/tiff`, `image/geotiff`, or `application/octet-stream`) up to 100 MB. The raster must contain exactly one band of analysis-ready calibrated backscatter in dB, a projected CRS with metre units, a valid geotransform, and nodata metadata where applicable. Select one calibrated polarization (VV or VH) before uploading; raw Sentinel-1 SAFE products, uncalibrated digital numbers, multi-band rasters, and geographic-coordinate rasters are not accepted. The default linear stretch maps -30 dB to 0 dB into the model's grayscale 0–255 input; tune the query bounds to the prepared scene. Images are resampled to at most 256 pixels on their longest side for inference.

Example:

```powershell
curl.exe -X POST "http://127.0.0.1:8000/api/detect/image?backscatter_min_db=-30&backscatter_max_db=0" `
  -H "Content-Type: image/tiff" `
  --data-binary "@analysis-ready-vv.tif"
```

The response retains the detection/GeoJSON structure and adds the input source. Pixel coordinates are transformed using the raster geotransform and CRS. Model output scores are not calibrated, and this checkpoint has not been validated on real Sentinel-1 oil-spill data; treat detections as exploratory only.

### Preliminary real-data evaluation

The current checkpoint was evaluated at threshold `0.5` on the held-out
22-tile test split of the [Oil Spill Segmentation Dataset (800x600), Zenodo
10.5281/zenodo.22728926](https://zenodo.org/records/22728926) (CC BY 4.0).
The dataset card describes 173 Sentinel-1-derived Cantarell-region tiles,
binary masks (`0 = SEA`, `1 = SLICK`, with oil spill and seepage combined), and
source-scene-grouped train/validation/test splits. The 22 test tiles span four
source-scene groups.

For this preliminary comparison, each paired single-band 16-bit TIFF and mask
was reprojected from EPSG:4326 to EPSG:32615, using bilinear resampling for
backscatter and nearest-neighbour resampling for labels. Both were reduced to
the detector's 256-pixel maximum dimension (20 tiles at 256x203 and 2 at
256x202). Backscatter used the API's default -30 to 0 dB linear stretch and
the model's default 0.5 threshold. Pixel-level counts were aggregated over
valid pixels:

| Metric | Result |
|---|---:|
| TP / FP / FN / TN | 11,202 / 497,598 / 1,119 / 632,865 |
| Micro IoU | 0.0220 |
| Precision | 0.0220 |
| Recall | 0.9092 |
| Pixel accuracy | 0.5636 |
| Mean per-tile IoU | 0.0970 |
| Median per-tile IoU | 0.0052 |

At this threshold, the model found most labeled slick pixels but also marked a
large amount of background as slick. The result is **poor segmentation
performance for this tested input preparation**; it does not support
operational use of the resulting vessel-candidate rankings.

### Validation-only normalization and threshold diagnosis

The checkpoint was also diagnosed on the dataset's 43-tile validation split.
Each paired raster and mask was reprojected and reduced using the same spatial
procedure described above. Three input encodings were compared: the API's
16-bit dB raster stretched from -30 to 0 dB, the provided 8-bit TIFF divided
by 255, and the provided RGB PNG converted to grayscale and divided by 255
(closest to the training loader's preprocessing). Thresholds were selected
only from validation predictions; the held-out test split was not used for
this sweep.

At the API's default threshold of 0.5, all three inputs produced poor results:

| Input encoding | Precision | Recall | Micro IoU | False positives | False negatives | Pixels predicted slick |
|---|---:|---:|---:|---:|---:|---:|
| 16-bit dB, -30 to 0 dB stretch | 0.0305 | 0.9891 | 0.0305 | 1,847,786 | 638 | 85.97% |
| 8-bit TIFF / 255 | 0.0285 | 0.9985 | 0.0285 | 1,997,555 | 86 | 92.75% |
| RGB PNG grayscale / 255 | 0.0297 | 0.9989 | 0.0297 | 1,915,527 | 66 | 89.05% |

The normalized input means were 0.301 (16-bit dB), 0.222 (8-bit TIFF), and
0.278 (PNG grayscale). The 16-bit dB input produced highly saturated output
probabilities on background pixels (median 0.9988). Sweeping the validation
threshold substantially changed the 16-bit result: the best tested threshold
for micro IoU was 0.99995, with precision 0.6420, recall 0.5339, IoU 0.4114,
17,489 false positives, and 27,387 false negatives. This is a validation-set
operating point, not a calibrated or recommended production threshold.

Normalization alone therefore does not explain or solve the detector's
failures. Threshold choice has a large effect because this checkpoint's
probabilities are saturated, but even the validation-selected result remains
limited and may not generalize. The checkpoint does not record its training
data or preprocessing provenance, so the input-distribution difference from
the synthetic training generator is evidence of a possible mismatch, not
proof of how this checkpoint was trained.

The benchmark's `LABELS-1D` masks use small integer class values (positive
pixels are `> 0`, with some files also containing value `2` despite the card's
binary 0/1 description). The training loader previously used `> 127`, which
silently removed these positive labels. It now binarizes all nonzero labels,
matching the benchmark's positive-class convention; a regression test covers
0/1 masks. This fixes dataset ingestion but does not by itself establish
detector accuracy.

After selecting 0.99995 on validation, the existing checkpoint was evaluated
once at that fixed threshold on the 22-tile test split. (That split had
previously been reported above at threshold 0.5; it was not used to select
0.99995.) The result was TP / FP / FN / TN = 548 / 0 / 11,777 / 1,121,149,
precision 1.0000, recall 0.0445, micro IoU 0.0445, and mean per-tile IoU
0.0219. The validation-selected threshold therefore did not transfer: it
nearly eliminated false positives but missed most labeled slick pixels.
Threshold 0.99995 must not be adopted as a production setting.

A separate training-only experiment used the 108 training pairs and an
isolated checkpoint. An 11-epoch candidate reached validation micro IoU 0.3893
at threshold 0.99, below the existing checkpoint's 0.4114 at its separately
selected threshold. It was not evaluated on the test split or adopted. A
separate 30-epoch CPU run was stopped after five epochs due to runtime and was
not evaluated. No checkpoint or API threshold was changed. The current
evidence does not justify relying on either model for vessel attribution;
retraining needs a controlled, sufficiently long run and independent
validation before any candidate is considered.

This is a preliminary, not definitive, benchmark. Although the dataset is
described as Sentinel-1-derived and provides georeferenced 8-bit and 16-bit
rasters, its card does not specify the source product level, polarization,
calibration procedure, or how the TIFF values should be normalized. The
provided test split has no empty masks (all 22 tiles contain positive labels),
and does not provide a dedicated lookalike/no-oil test subset, so it cannot
measure false alarms on those scene types. Checkpoint training-data provenance
and possible overlap with this dataset are also not recorded. Therefore the
numbers above measure this exact checkpoint/preprocessing combination, not
generalization to all Sentinel-1 data.

A stronger documented follow-up is [Sentinel-1 SAR Oil Spill image dataset,
Part III, Zenodo 10.5281/zenodo.13761290](https://zenodo.org/records/13761290)
(CC BY 4.0): 450 test scenes (150 oil, 150 lookalike, 150 no-oil) with
2048x2048 two-polarization VV/VH Sigma0-in-dB imagery and masks. Its test
archive is about 9.86 GB, and masks are not georeferenced. A future benchmark
should explicitly select a polarization, preserve its calibrated dB values,
align masks through any reprojection, and report results separately for oil,
lookalike, and no-oil cases before vessel-candidate rankings are treated as
meaningful evidence.

### Train the real model (from scratch)

Real-data training requires separate training and validation directories, each
with `images/` and `masks/` subdirectories. Use a source-scene-grouped split
when multiple patches come from the same acquisition; do not put related
patches in both directories. Synthetic runs create a deterministic 80/20
held-out split automatically.

The trainer reads grayscale PNG/JPEG images and matching masks, scales image
values from 8-bit 0–255 to 0–1, and treats every nonzero mask value as slick.
Prepare training and validation images with the same calibrated-backscatter
conversion used for inference (the GeoTIFF API defaults to a -30 to 0 dB
stretch); raw 16-bit rasters are not directly consumed by this trainer.

```bash
# heavy ML/raster dependencies
pip install -r requirements-ml.txt

# Option A: train on auto-generated synthetic scenes
python server/train_unet.py --synthetic --samples 600 --epochs 30

# Option B: train on labeled pairs with an independent validation set
python server/train_unet.py --data path/to/train --validation-data path/to/validation --epochs 40
```

Each epoch reports training metrics and validation metrics separately. The
candidate checkpoint is selected by validation micro-IoU at threshold 0.5 and
is written by default to `server/checkpoints/unet_oil_spill_candidate.pth`
(with `_best` and `_last` companion files). Training will not overwrite the
production checkpoint at `server/checkpoints/unet_oil_spill.pth`; evaluate the
candidate on an independent test set before any deliberate promotion.

### How it fits together

```
SAR patch (server/ml_detector.py synthesizes one in demo mode)
      │
      ▼
UNet ──► binary oil mask (pure-python fallback when torch absent)
      │
      ▼
DBSCAN ──► clusters  (scikit-learn; 4-connectivity fallback if missing)
      │
      ▼
convex-hull ──► GeoJSON polygons ──► Leaflet "ML Detections" layer
```

## Notes

All outputs are intended as investigation support, not final proof.