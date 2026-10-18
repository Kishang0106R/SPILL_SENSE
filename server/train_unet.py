"""
Spill Sense UNet Training Script
===============================

Train the oil-spill segmentation U-Net **from scratch** on labeled SAR
image/mask pairs, or on auto-generated synthetic scenes for development.

Usage
-----
    # 1) Train on your own labeled SAR data (dir with images/ and masks/)
    python server/train_unet.py --data path/to/dataset --epochs 40

    # 2) Train on synthetic scenes (no data required) -- great for a first run
    python server/train_unet.py --synthetic --samples 600 --epochs 30

    # 3) Resume / fine-tune from an existing checkpoint
    python server/train_unet.py --synthetic --resume server/checkpoints/unet_oil_spill.pth

Checkpoint is saved to ``server/checkpoints/unet_oil_spill.pth`` where
``server/ml_detector.py`` will pick it up automatically (the web API then
switches from demo mode to *real* inference).

Dataset layout
--------------
    dataset/
      images/  sar_001.png      # grayscale SAR patches (0..255)
      masks/   sar_001.png      # binary 0/1 or 0/255 segmentation masks
"""

from __future__ import annotations

import argparse
import random
import sys
from pathlib import Path

# Allow the script to be run as ``python server/train_unet.py`` from repo root
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402
import torch  # noqa: E402
import torch.nn as nn  # noqa: E402
import torch.optim as optim  # noqa: E402
from torch.utils.data import DataLoader, Dataset  # noqa: E402

from server.ml_detector import (  # noqa: E402
    CHECKPOINT_DIR,
    CHECKPOINT_PATH,
    DoubleConv,  # reused below in-channel expansion not needed; harmless import
    UNet,
    synthesize_sar_patch,
)

# ---------------------------------------------------------------------------
# Dataset helpers
# ---------------------------------------------------------------------------
class PairedSAROODataset(Dataset):
    """Reads grayscale images and matching binary masks from two folders."""

    def __init__(self, images_dir: Path, masks_dir: Path, patch: int = 256):
        self.files = sorted(images_dir.glob("*.png")) + sorted(images_dir.glob("*.jpg"))
        if not self.files:
            raise RuntimeError(f"No images found in {images_dir}")
        self.masks_dir = masks_dir

        import cv2

        self.cv2 = cv2
        self.patch = patch

    def __len__(self) -> int:
        return len(self.files)

    def __getitem__(self, idx: int):
        img_path = self.files[idx]
        mask_path = self.masks_dir / img_path.name
        if not mask_path.exists():
            mask_path = self.masks_dir / (img_path.stem + ".png")

        img = self.cv2.imread(str(img_path), self.cv2.IMREAD_GRAYSCALE)
        msk = self.cv2.imread(str(mask_path), self.cv2.IMREAD_GRAYSCALE)
        if img is None:
            raise RuntimeError(f"Could not read image {img_path}")

        if msk is not None:
            msk = (msk > 127).astype(np.uint8)
        else:
            msk = np.zeros_like(img)

        # Random crop to patch size (keeps some augmentation)
        h, w = img.shape
        if h >= self.patch and w >= self.patch:
            y0 = random.randint(0, h - self.patch)
            x0 = random.randint(0, w - self.patch)
            img = img[y0:y0 + self.patch, x0:x0 + self.patch]
            msk = msk[y0:y0 + self.patch, x0:x0 + self.patch]
        else:
            img = self.cv2.resize(img, (self.patch, self.patch))
            msk = self.cv2.resize(msk, (self.patch, self.patch))

        t_img = torch.from_numpy(img.astype(np.float32) / 255.0).unsqueeze(0)
        t_msk = torch.from_numpy(msk.astype(np.float32)).unsqueeze(0)
        return t_img, t_msk


class SyntheticOODataset(Dataset):
    """Generates infinite synthetic SAR-ish scenes (dev mode, no labels needed)."""

    def __init__(self, size: int = 256, samples: int = 500, seed: int = 0):
        self.size = size
        self.samples = samples
        self.seed = seed

    def __len__(self) -> int:
        return self.samples

    def __getitem__(self, idx: int):
        img, mask = synthesize_sar_patch(self.size, seed=int(idx) + self.seed)
        t_img = torch.from_numpy(img.astype(np.float32) / 255.0).unsqueeze(0)
        t_msk = torch.from_numpy(mask.astype(np.float32)).unsqueeze(0)
        return t_img, t_msk


def iou_score(pred: torch.Tensor, target: torch.Tensor, eps: float = 1e-6) -> float:
    pred_b = (torch.sigmoid(pred) > 0.5).float()
    inter = (pred_b * target).sum().item()
    union = (pred_b + target).clamp(max=1).sum().item()
    return inter / (union + eps)


def dice_loss(pred: torch.Tensor, target: torch.Tensor, eps: float = 1e-6) -> torch.Tensor:
    p = torch.sigmoid(pred)
    inter = (p * target).sum()
    return 1.0 - (2.0 * inter + eps) / (p.sum() + target.sum() + eps)


# ---------------------------------------------------------------------------
# Training loop
# ---------------------------------------------------------------------------
def main() -> None:
    parser = argparse.ArgumentParser(description="Train Spill Sense UNet from scratch")
    parser.add_argument("--data", type=Path, default=None, help="dir containing images/ and masks/")
    parser.add_argument("--synthetic", action="store_true", help="train on generated synthetic scenes")
    parser.add_argument("--samples", type=int, default=500, help="synthetic samples")
    parser.add_argument("--patch", type=int, default=256, help="patch size")
    parser.add_argument("--epochs", type=int, default=30)
    parser.add_argument("--batch-size", type=int, default=8)
    parser.add_argument("--lr", type=float, default=1e-3)
    parser.add_argument("--base", type=int, default=32, help="UNet base channels")
    parser.add_argument("--save", type=Path, default=CHECKPOINT_PATH, help="checkpoint output path")
    parser.add_argument("--resume", type=Path, default=None, help="checkpoint to resume from")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--no-cuda", action="store_true")
    args = parser.parse_args()

    if not args.data and not args.synthetic:
        parser.error("provide --data <dir> or --synthetic")

    random.seed(args.seed)
    np.random.seed(args.seed)
    torch.manual_seed(args.seed)

    device = torch.device("cpu" if args.no_cuda or not torch.cuda.is_available() else "cuda")
    print(f"device: {device}")

    if args.synthetic:
        dataset = SyntheticOODataset(size=args.patch, samples=args.samples, seed=args.seed)
        print(f"training on {args.samples} synthetic scenes")
    else:
        images_dir = args.data / "images"
        masks_dir = args.data / "masks"
        dataset = PairedSAROODataset(images_dir, masks_dir, patch=args.patch)
        print(f"training on {len(dataset)} labeled pairs from {args.data}")

    loader = DataLoader(dataset, batch_size=args.batch_size, shuffle=True, num_workers=0)

    model = UNet(in_channels=1, base=args.base).to(device)
    start_epoch = 0
    if args.resume and Path(args.resume).is_file():
        state = torch.load(str(args.resume), map_location=device, weights_only=False)
        if isinstance(state, dict) and "state_dict" in state:
            model.load_state_dict(state["state_dict"])
            start_epoch = int(state.get("epoch", 0))
        else:
            model.load_state_dict(state)
        print(f"resumed from {args.resume} (epoch {start_epoch})")

    optimizer = optim.AdamW(model.parameters(), lr=args.lr, weight_decay=1e-4)
    scheduler = optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=args.epochs)
    bce = nn.BCEWithLogitsLoss()

    args.save.parent.mkdir(parents=True, exist_ok=True)

    best_iou = 0.0
    for epoch in range(start_epoch, args.epochs):
        model.train()
        total_loss, total_iou, n = 0.0, 0.0, 0
        for images, masks in loader:
            images = images.to(device)
            masks = masks.to(device)

            optimizer.zero_grad()
            logits = model(images)
            loss = bce(logits, masks) + dice_loss(logits, masks)
            loss.backward()
            optimizer.step()

            total_loss += loss.item()
            total_iou += iou_score(logits, masks)
            n += 1

        scheduler.step()
        avg_loss = total_loss / max(n, 1)
        avg_iou = total_iou / max(n, 1)

        checkpoint_state = {
            "epoch": epoch + 1,
            "model": "unet",
            "state_dict": model.state_dict(),
            "optimizer": optimizer.state_dict(),
            "iou": avg_iou,
            "loss": avg_loss,
            "config": {
                "input_channels": 1,
                "output_channels": 1,
                "base": args.base,
                "patch": args.patch,
            },
        }

        if avg_iou >= best_iou:
            best_iou = avg_iou
            torch.save(checkpoint_state, str(args.save))
            torch.save(checkpoint_state, str(args.save).replace(".pth", "_best.pth"))

        torch.save(checkpoint_state, str(args.save).replace(".pth", "_last.pth"))
        print(f"epoch {epoch + 1}/{args.epochs}  loss={avg_loss:.4f}  iou={avg_iou:.4f}  best_iou={best_iou:.4f}")

    print(f"\nDone. Checkpoint saved to {args.save}")
    print("Serve the app and the API will switch to real UNet inference automatically.")


if __name__ == "__main__":
    main()