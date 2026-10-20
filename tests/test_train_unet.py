import tempfile
import unittest
from pathlib import Path

import cv2
import numpy as np
import torch
from torch import nn
from torch.utils.data import DataLoader, TensorDataset

from server.train_unet import PairedSAROODataset, evaluate


class PairedSAROODatasetTests(unittest.TestCase):
    def test_nonzero_mask_labels_preserve_spill_pixels(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            images_dir = root / "images"
            masks_dir = root / "masks"
            images_dir.mkdir()
            masks_dir.mkdir()
            image = np.zeros((16, 16), dtype=np.uint8)
            mask = np.zeros((16, 16), dtype=np.uint8)
            mask[4:8, 5:9] = 1
            mask[10:12, 10:12] = 2
            cv2.imwrite(str(images_dir / "scene.png"), image)
            cv2.imwrite(str(masks_dir / "scene.png"), mask)
            dataset = PairedSAROODataset(images_dir, masks_dir, patch=16)

            _, target = dataset[0]

            self.assertEqual(float(target.sum()), 20.0)
            self.assertEqual(set(np.unique(target.numpy())), {0.0, 1.0})

    def test_missing_mask_fails_with_clear_error(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            images_dir = root / "images"
            masks_dir = root / "masks"
            images_dir.mkdir()
            masks_dir.mkdir()
            cv2.imwrite(str(images_dir / "scene.png"), np.zeros((16, 16), dtype=np.uint8))
            dataset = PairedSAROODataset(images_dir, masks_dir, patch=16)

            with self.assertRaisesRegex(FileNotFoundError, "Required segmentation mask"):
                dataset[0]

    def test_unreadable_mask_fails_with_clear_error(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            images_dir = root / "images"
            masks_dir = root / "masks"
            images_dir.mkdir()
            masks_dir.mkdir()
            cv2.imwrite(str(images_dir / "scene.png"), np.zeros((16, 16), dtype=np.uint8))
            (masks_dir / "scene.png").write_text("not an image", encoding="utf-8")
            dataset = PairedSAROODataset(images_dir, masks_dir, patch=16)

            with self.assertRaisesRegex(RuntimeError, "Could not read required segmentation mask"):
                dataset[0]

    def test_validation_iou_is_aggregated_over_all_pixels(self):
        logits = torch.tensor([[[[1.0, -1.0]]], [[[1.0, 1.0]]]])
        masks = torch.tensor([[[[1.0, 0.0]]], [[[1.0, 0.0]]]])
        loader = DataLoader(TensorDataset(logits, masks), batch_size=1)

        _, micro_iou = evaluate(
            nn.Identity(),
            loader,
            torch.device("cpu"),
            nn.BCEWithLogitsLoss(),
        )

        self.assertAlmostEqual(micro_iou, 2 / 3, places=5)


if __name__ == "__main__":
    unittest.main()
