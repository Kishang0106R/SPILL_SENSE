"""
Spill Sense UNet Training Script
===============================

Train the oil-spill segmentation U-Net **from scratch** on labeled SAR
image/mask pairs, or on auto-generated synthetic scenes for development.

Usage
-----
    # 1) Train on your own labeled SAR data (dir with images/ and masks/)
    python server/train_unet.py --data path/to/train --validation-data path/to/validation --epochs 40

    # 2) Train on synthetic scenes (no data required) -- great for a first run
    python server/train_unet.py --synthetic --samples 600 --epochs 30

    # 3) Resume / fine-tune from an existing checkpoint
    python server/train_unet.py --synthetic --resume server/checkpoints/unet_oil_spill.pth

The default candidate checkpoint is saved separately from the production
checkpoint used by ``server/ml_detector.py``.

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
    UNet,
    synthesize_sar_patch,
)

# ---------------------------------------------------------------------------
# Dataset helpers
# ---------------------------------------------------------------------------
class PairedSAROODataset(Dataset):
    """Reads grayscale images and matching binary masks from two folders."""

    def __init__(
        self,
        images_dir: Path,
        masks_dir: Path,
        patch: int = 256,
        random_crop: bool = True,
    ):
        self.files = sorted(images_dir.glob("*.png")) + sorted(images_dir.glob("*.jpg"))
        if not self.files:
            raise RuntimeError(f"No images found in {images_dir}")
        self.masks_dir = masks_dir

        import cv2

        self.cv2 = cv2
        self.patch = patch
        self.random_crop = random_crop

    def __len__(self) -> int:
        return len(self.files)

    def __getitem__(self, idx: int):
        img_path = self.files[idx]
        mask_path = self.masks_dir / img_path.name
        if not mask_path.exists():
            mask_path = self.masks_dir / (img_path.stem + ".png")
        if not mask_path.is_file():
            raise FileNotFoundError(
                f"Required segmentation mask for {img_path.name} not found "
                f"in {self.masks_dir}."
            )

        img = self.cv2.imread(str(img_path), self.cv2.IMREAD_GRAYSCALE)
        msk = self.cv2.imread(str(mask_path), self.cv2.IMREAD_GRAYSCALE)
        if img is None:
            raise RuntimeError(f"Could not read image {img_path}")
        if msk is None:
            raise RuntimeError(f"Could not read required segmentation mask {mask_path}")
        msk = (msk > 0).astype(np.uint8)

        # Random crop to patch size (keeps some augmentation)
        h, w = img.shape
        if h >= self.patch and w >= self.patch:
            if self.random_crop:
                y0 = random.randint(0, h - self.patch)
                x0 = random.randint(0, w - self.patch)
            else:
                y0 = (h - self.patch) // 2
                x0 = (w - self.patch) // 2
            img = img[y0:y0 + self.patch, x0:x0 + self.patch]
            msk = msk[y0:y0 + self.patch, x0:x0 + self.patch]
        else:
            img = self.cv2.resize(img, (self.patch, self.patch))
            msk = self.cv2.resize(
                msk, (self.patch, self.patch), interpolation=self.cv2.INTER_NEAREST
            )

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


def evaluate(
    model: nn.Module,
    loader: DataLoader,
    device: torch.device,
    loss_fn: nn.Module,
) -> tuple[float, float]:
    model.eval()
    total_loss = 0.0
    total_intersection = 0.0
    total_union = 0.0
    batches = 0

    with torch.no_grad():
        for images, masks in loader:
            images = images.to(device)
            masks = masks.to(device)
            logits = model(images)
            total_loss += (loss_fn(logits, masks) + dice_loss(logits, masks)).item()
            predictions = (logits > 0).float()
            total_intersection += (predictions * masks).sum().item()
            total_union += (predictions + masks).clamp(max=1).sum().item()
            batches += 1

    avg_loss = total_loss / max(batches, 1)
    micro_iou = total_intersection / (total_union + 1e-6)
    return avg_loss, micro_iou


# ---------------------------------------------------------------------------
# Training loop
# ---------------------------------------------------------------------------
def main() -> None:
    parser = argparse.ArgumentParser(description="Train Spill Sense UNet from scratch")
    parser.add_argument("--data", type=Path, default=None, help="dir containing images/ and masks/")
    parser.add_argument(
        "--validation-data",
        type=Path,
        default=None,
        help="separate validation dir containing images/ and masks/ (required with --data)",
    )
    parser.add_argument("--synthetic", action="store_true", help="train on generated synthetic scenes")
    parser.add_argument("--samples", type=int, default=500, help="synthetic samples")
    parser.add_argument("--patch", type=int, default=256, help="patch size")
    parser.add_argument("--epochs", type=int, default=30)
    parser.add_argument("--batch-size", type=int, default=8)
    parser.add_argument("--lr", type=float, default=1e-3)
    parser.add_argument("--base", type=int, default=32, help="UNet base channels")
    parser.add_argument(
        "--save",
        type=Path,
        default=CHECKPOINT_DIR / "unet_oil_spill_candidate.pth",
        help="candidate checkpoint output path (production checkpoint is never overwritten)",
    )
    parser.add_argument("--resume", type=Path, default=None, help="checkpoint to resume from")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--no-cuda", action="store_true")
    args = parser.parse_args()

    if (args.data is None and not args.synthetic) or (args.data is not None and args.synthetic):
        parser.error("provide either --data <dir> or --synthetic")
    if args.data and not args.validation_data:
        parser.error("--validation-data is required when training on labeled data")
    if args.synthetic and args.validation_data:
        parser.error("--validation-data cannot be used with --synthetic")
    if args.data and args.validation_data:
        if args.data.resolve() == args.validation_data.resolve():
            parser.error("training and validation directories must be separate")
    if args.save.resolve() == CHECKPOINT_PATH.resolve():
        parser.error("--save cannot target the production checkpoint")

    random.seed(args.seed)
    np.random.seed(args.seed)
    torch.manual_seed(args.seed)

    device = torch.device("cpu" if args.no_cuda or not torch.cuda.is_available() else "cuda")
    print(f"device: {device}")

    if args.synthetic:
        dataset = SyntheticOODataset(size=args.patch, samples=args.samples, seed=args.seed)
        if args.samples < 2:
            parser.error("--samples must be at least 2 to create a validation split")
        val_count = max(1, round(args.samples * 0.2))
        train_count = args.samples - val_count
        train_dataset, val_dataset = torch.utils.data.random_split(
            dataset,
            (train_count, val_count),
            generator=torch.Generator().manual_seed(args.seed),
        )
        print(
            f"training on {train_count} synthetic scenes; "
            f"validating on {val_count} held-out scenes"
        )
    else:
        assert args.data is not None and args.validation_data is not None
        images_dir = args.data / "images"
        masks_dir = args.data / "masks"
        train_dataset = PairedSAROODataset(images_dir, masks_dir, patch=args.patch)
        val_images_dir = args.validation_data / "images"
        val_masks_dir = args.validation_data / "masks"
        val_dataset = PairedSAROODataset(
            val_images_dir, val_masks_dir, patch=args.patch, random_crop=False
        )
        print(
            f"training on {len(train_dataset)} labeled pairs from {args.data}; "
            f"validating on {len(val_dataset)} pairs from {args.validation_data}"
        )

    loader = DataLoader(train_dataset, batch_size=args.batch_size, shuffle=True, num_workers=0)
    val_loader = DataLoader(val_dataset, batch_size=args.batch_size, shuffle=False, num_workers=0)

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

    best_iou = -1.0
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
        val_loss, val_iou = evaluate(model, val_loader, device, bce)

        checkpoint_state = {
            "epoch": epoch + 1,
            "model": "unet",
            "state_dict": model.state_dict(),
            "optimizer": optimizer.state_dict(),
            "iou": val_iou,
            "train_iou": avg_iou,
            "val_iou": val_iou,
            "loss": val_loss,
            "train_loss": avg_loss,
            "val_loss": val_loss,
            "config": {
                "input_channels": 1,
                "output_channels": 1,
                "base": args.base,
                "patch": args.patch,
            },
        }

        if val_iou > best_iou:
            best_iou = val_iou
            torch.save(checkpoint_state, str(args.save))
            best_path = args.save.with_name(f"{args.save.stem}_best{args.save.suffix}")
            torch.save(checkpoint_state, str(best_path))

        last_path = args.save.with_name(f"{args.save.stem}_last{args.save.suffix}")
        torch.save(checkpoint_state, str(last_path))
        print(
            f"epoch {epoch + 1}/{args.epochs}  train_loss={avg_loss:.4f}  "
            f"train_iou={avg_iou:.4f}  val_loss={val_loss:.4f}  "
            f"val_iou={val_iou:.4f}  best_val_iou={best_iou:.4f}"
        )

    print(f"\nDone. Checkpoint saved to {args.save}")
    print("Evaluate the candidate checkpoint before promoting it for API inference.")


if __name__ == "__main__":
    main()