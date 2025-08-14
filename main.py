#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Scanimation base generator (Pillow)
- Collect frames by extensions from a folder (optionally recursive)
- Natural-sorts by filename (1,2,10…)
- Interlaces frames into a single base image
- Optionally exports a periodic grille mask

Install once:
  pip install pillow natsort

Examples:
  python make_scanimation.py --slice 1 --out-base base.png --out-mask mask.png
  python make_scanimation.py --dir ./frames --recursive --direction horizontal --slice 2
"""

import argparse
from pathlib import Path
from typing import List, Tuple
from PIL import Image
from natsort import natsorted

DEFAULT_EXTS = "png,jpg,jpeg,webp,bmp,gif,tif,tiff,PNG,JPG,JPEG,WEBP,BMP,GIF,TIF,TIFF"

def parse_args():
    p = argparse.ArgumentParser(description="Generate scanimation base (and optional mask) from frames.")
    p.add_argument("--dir", default=".", help="Folder containing frames (default: current directory)")
    p.add_argument("--recursive", action="store_true", help="Recurse into subfolders")
    p.add_argument("--exts", default=DEFAULT_EXTS,
                   help=f"Comma-separated extensions to include (default: {DEFAULT_EXTS})")
    p.add_argument("--slice", type=int, default=1,
                   help="Stripe/visible slit size in pixels (default: 1)")
    p.add_argument("--direction", choices=["vertical", "horizontal"], default="vertical",
                   help="Stripe direction: vertical (left-right slide) or horizontal (up-down slide).")
    p.add_argument("--resize", choices=["first", "min"], default="first",
                   help="Resize strategy to unify all frames: "
                        "'first'=match first frame; 'min'=fit to smallest width/height.")
    p.add_argument("--out-base", default="scanimation_base.png",
                   help="Output filename for interlaced base")
    p.add_argument("--out-mask", default=None,
                   help="Also export periodic grille mask (PNG)")
    p.add_argument("--force-rgb", action="store_true",
                   help="Force RGB output (useful for some printers)")
    p.add_argument("--white-bg", action="store_true",
                   help="Composite onto solid white background (avoid transparent output).")
    return p.parse_args()

def collect_files(folder: Path, exts: List[str], recursive: bool) -> List[Path]:
    exts_lc = {e.lower().lstrip(".") for e in exts if e.strip()}
    if recursive:
        files = [p for p in folder.rglob("*") if p.is_file() and p.suffix.lower().lstrip(".") in exts_lc]
    else:
        files = [p for p in folder.glob("*") if p.is_file() and p.suffix.lower().lstrip(".") in exts_lc]
    # 自然排序：按“文件名”排序（不带路径），确保 1,2,10… 的顺序
    return natsorted(files, key=lambda p: p.name)

def load_frames(files: List[Path]) -> List[Image.Image]:
    imgs = []
    for f in files:
        try:
            im = Image.open(f).convert("RGBA")
        except Exception as e:
            raise SystemExit(f"[ERROR] Failed to open image: {f} ({e})")
        imgs.append(im)
    return imgs

def unify_sizes(imgs: List[Image.Image], mode: str) -> Tuple[List[Image.Image], int, int]:
    if mode == "first":
        W, H = imgs[0].width, imgs[0].height
    else:  # "min"
        W = min(im.width for im in imgs)
        H = min(im.height for im in imgs)
    out = []
    for im in imgs:
        if im.width != W or im.height != H:
            out.append(im.resize((W, H), Image.LANCZOS))
        else:
            out.append(im)
    return out, W, H

# === 稳妥的交错算法（关键点在这里） ===
def interlace_vertical(frames: List[Image.Image], W: int, H: int, slice_w: int) -> Image.Image:
    """每条竖条宽 slice_w：按帧轮换，从各帧的同一 x 区间裁切粘贴。"""
    N = len(frames)
    slice_w = max(1, min(slice_w, W))
    out = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    for x in range(0, W, slice_w):
        f_idx = (x // slice_w) % N                   # 当前条来自第几帧
        # 直接从该帧的同一列区间 x:x+slice_w 裁切
        x2 = min(x + slice_w, W)
        crop = frames[f_idx].crop((x, 0, x2, H))
        out.paste(crop, (x, 0))
    return out

def interlace_horizontal(frames: List[Image.Image], W: int, H: int, slice_h: int) -> Image.Image:
    """每条横条高 slice_h：按帧轮换，从各帧的同一 y 区间裁切粘贴。"""
    N = len(frames)
    slice_h = max(1, min(slice_h, H))
    out = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    for y in range(0, H, slice_h):
        f_idx = (y // slice_h) % N
        y2 = min(y + slice_h, H)
        crop = frames[f_idx].crop((0, y, W, y2))
        out.paste(crop, (0, y))
    return out

def make_mask(W: int, H: int, slice_px: int, N: int, direction: str) -> Image.Image:
    """周期遮罩：不透明黑 + 每 (slice_px * N) 像素开一条透明缝。"""
    slice_px = max(1, slice_px)
    period = slice_px * N
    mask = Image.new("RGBA", (W, H), (0, 0, 0, 255))
    if direction == "vertical":
        slit = Image.new("RGBA", (slice_px, H), (0, 0, 0, 0))
        for x in range(0, W, period):
            mask.paste(slit, (x, 0))
    else:
        slit = Image.new("RGBA", (W, slice_px), (0, 0, 0, 0))
        for y in range(0, H, period):
            mask.paste(slit, (0, y))
    return mask

def composite_on_white(img: Image.Image) -> Image.Image:
    """把 RGBA 合成到白底，避免查看器把透明当白或打印异常。"""
    if img.mode != "RGBA":
        return img.convert("RGB")
    bg = Image.new("RGB", img.size, (255, 255, 255))
    bg.paste(img, mask=img.split()[-1])  # 用 alpha 作为蒙版
    return bg

def main():
    args = parse_args()
    folder = Path(args.dir).expanduser().resolve()
    if not folder.exists():
        raise SystemExit(f"[ERROR] Folder not found: {folder}")

    exts = [e.strip() for e in args.exts.split(",") if e.strip()]
    files = collect_files(folder, exts, args.recursive)
    if len(files) < 2:
        raise SystemExit(f"[ERROR] Found {len(files)} image(s) in {folder} with exts {exts}. Need at least 2.")

    print(f"[INFO] Collected {len(files)} frame(s) from {folder}:")
    for p in files:
        print("  -", p.name)

    frames = load_frames(files)
    frames, W, H = unify_sizes(frames, args.resize)

    if args.direction == "vertical":
        base = interlace_vertical(frames, W, H, args.slice)
    else:
        base = interlace_horizontal(frames, W, H, args.slice)

    # 输出模式：可选强制 RGB / 白底合成
    out_img = base
    if args.white_bg:
        out_img = composite_on_white(base)
    elif args.force_rgb:
        out_img = base.convert("RGB")

    out_base = Path(args.out-base) if hasattr(args, "out-base") else Path(args.out_base)  # safety for hyphen confusion
    out_base.parent.mkdir(parents=True, exist_ok=True)
    out_img.save(out_base)
    print(f"[OK] Base saved -> {out_base}  (size: {W}x{H}, frames: {len(frames)}, slice: {args.slice}, dir: {args.direction})")

    if args.out_mask:
        mask = make_mask(W, H, args.slice, len(frames), args.direction)
        out_mask = Path(args.out_mask)
        out_mask.parent.mkdir(parents=True, exist_ok=True)
        # 遮罩通常需要保留透明 -> 用 RGBA
        mask.save(out_mask)
        print(f"[OK] Mask saved -> {out_mask}  (period: {args.slice * len(frames)} px)")

if __name__ == "__main__":
    main()
