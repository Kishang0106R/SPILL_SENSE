import unittest
from io import BytesIO
from pathlib import Path
import tempfile
from unittest.mock import patch

import numpy as np
import rasterio
from rasterio.io import MemoryFile
from rasterio.transform import from_origin

import server.ml_detector as ml_detector
from server.ml_detector import (
    model_status,
    run_detection_on_geotiff,
    synthesize_sar_patch,
    cluster_oil_pixels,
    run_detection,
)


class MLDetectorTests(unittest.TestCase):
    def test_model_status_returns_valid_structure(self):
        status = model_status()
        self.assertIn("torch_available", status)
        self.assertIn("sklearn_available", status)
        self.assertIn("checkpoint_exists", status)
        self.assertIn("mode", status)

    def test_synthesize_sar_patch_shapes(self):
        patch, mask = synthesize_sar_patch(size=64, seed=42)
        self.assertEqual(patch.shape, (64, 64))
        self.assertEqual(mask.shape, (64, 64))

    @unittest.skipUnless(ml_detector.HAS_TORCH, "PyTorch is not installed")
    def test_checkpoint_config_selects_inference_architecture(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            checkpoint = Path(temp_dir) / "candidate.pth"
            model = ml_detector.UNet(base=8)
            ml_detector.torch.save(
                {
                    "config": {"input_channels": 1, "base": 8},
                    "state_dict": model.state_dict(),
                },
                checkpoint,
            )

            probabilities = ml_detector.run_unet_probabilities(
                np.zeros((32, 32), dtype=np.uint8), checkpoint
            )

        assert probabilities is not None
        self.assertEqual(probabilities.shape, (32, 32))

    def test_cluster_oil_pixels_with_synthetic_points(self):
        coords = [(10.0, 10.0), (10.0, 11.0), (11.0, 10.0), (50.0, 50.0)]
        labels, method = cluster_oil_pixels(coords, eps_px=3, min_samples=2)
        self.assertEqual(len(labels), len(coords))
        self.assertEqual(labels[0], labels[1])
        self.assertEqual(labels[0], labels[2])

    def test_run_detection_pipeline_end_to_end(self):
        result = run_detection(center_lat=2.3812, center_lon=101.9124, patch_size=64)
        self.assertEqual(result["status"], "ok")
        self.assertIn("clusters", result)
        self.assertIn("polygons", result)
        self.assertIn("preview_png_b64", result)
        self.assertIn("dbscan_engine", result)

    def test_real_cluster_score_uses_mean_model_probability(self):
        probabilities = np.zeros((16, 16), dtype=np.float32)
        probabilities[:5, :5] = 0.6
        probabilities[0, 0] = 0.8

        with (
            patch(
                "server.ml_detector.synthesize_sar_patch",
                return_value=(np.zeros((16, 16), dtype=np.uint8), np.zeros((16, 16), dtype=np.uint8)),
            ),
            patch(
                "server.ml_detector.run_unet_probabilities",
                return_value=probabilities,
            ),
            patch(
                "server.ml_detector.cluster_oil_pixels",
                return_value=([0] * 25, "test clusterer"),
            ),
        ):
            result = run_detection(patch_size=16, min_pixels=1)

        cluster = result["clusters"][0]
        self.assertEqual("mean_model_probability", cluster["score_type"])
        self.assertEqual(60.8, cluster["score_pct"])
        self.assertNotIn("confidence_pct", cluster)
        self.assertEqual(cluster["score_pct"], result["polygons"]["features"][0]["properties"]["score_pct"])

    def test_geotiff_is_normalized_georeferenced_and_nodata_is_excluded(self):
        backscatter = np.full((16, 32), -15.0, dtype=np.float32)
        backscatter[:6, :5] = -15.0
        backscatter[0, 0] = -9999.0
        output = BytesIO()
        with MemoryFile() as memory_file:
            with memory_file.open(
                driver="GTiff",
                width=32,
                height=16,
                count=1,
                dtype="float32",
                crs="EPSG:32631",
                transform=from_origin(500000, 5100000, 10, 10),
                nodata=-9999.0,
            ) as dataset:
                dataset.write(backscatter, 1)
            output.write(memory_file.read())

        probabilities = np.zeros((16, 32), dtype=np.float32)
        probabilities[:6, :5] = 0.75
        inference_inputs = []

        def fake_inference(image, checkpoint):
            inference_inputs.append(image.copy())
            return probabilities

        with (
            patch("server.ml_detector.run_unet_probabilities", side_effect=fake_inference),
            patch(
                "server.ml_detector.cluster_oil_pixels",
                side_effect=lambda coords, **kwargs: ([0] * len(coords), "test clusterer"),
            ),
        ):
            result = run_detection_on_geotiff(output.getvalue())

        self.assertEqual("sentinel1_geotiff", result["input"]["source"])
        self.assertEqual(-30.0, result["input"]["backscatter_min_db"])
        self.assertEqual(0.0, result["input"]["backscatter_max_db"])
        self.assertEqual((16, 32), inference_inputs[0].shape)
        self.assertEqual(128, int(inference_inputs[0][10, 10]))
        self.assertEqual(29, result["clusters"][0]["oil_pixels"])
        self.assertAlmostEqual(0.0029, result["clusters"][0]["area_km2"], places=4)
        self.assertAlmostEqual(3.0002, result["clusters"][0]["centroid"][1], places=3)
        self.assertEqual("mean_model_probability", result["clusters"][0]["score_type"])
        self.assertTrue(result["preview_png_b64"].startswith("data:image/png;base64,"))

    def test_geotiff_rejects_multiple_bands(self):
        output = BytesIO()
        with MemoryFile() as memory_file:
            with memory_file.open(
                driver="GTiff",
                width=16,
                height=16,
                count=2,
                dtype="uint8",
                crs="EPSG:32631",
                transform=from_origin(500000, 5100000, 10, 10),
            ) as dataset:
                dataset.write(np.zeros((2, 16, 16), dtype=np.uint8))
            output.write(memory_file.read())

        with self.assertRaisesRegex(ValueError, "exactly one band"):
            run_detection_on_geotiff(output.getvalue())

    def test_geotiff_rejects_invalid_backscatter_range(self):
        with self.assertRaisesRegex(ValueError, "must be less than"):
            run_detection_on_geotiff(b"not-read", backscatter_min_db=0, backscatter_max_db=-30)


if __name__ == "__main__":
    unittest.main()
