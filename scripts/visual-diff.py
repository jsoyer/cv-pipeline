#!/usr/bin/env python3
"""
PDF Visual Regression — Pixel-level comparison of two PDF versions.

Converts PDF pages to images, then highlights visual differences.
Requires: ImageMagick (convert + compare commands).

Usage:
    scripts/visual-diff.py <application-dir>
    scripts/visual-diff.py <pdf1> <pdf2>
"""

import argparse
import os
import subprocess
import sys
from pathlib import Path


def check_imagemagick():
    """Check if ImageMagick is installed."""
    try:
        result = subprocess.run(
            ["magick", "-version"],
            capture_output=True, text=True, timeout=5
        )
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass
    # Try legacy command
    try:
        result = subprocess.run(
            ["convert", "-version"],
            capture_output=True, text=True, timeout=5
        )
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def pdf_to_images(pdf_path, output_dir, prefix, density=150):
    """Convert PDF pages to PNG images."""
    output_pattern = output_dir / f"{prefix}-%d.png"
    try:
        subprocess.run(
            ["magick", "-density", str(density), str(pdf_path),
             "-background", "white", "-alpha", "remove",
             str(output_pattern)],
            capture_output=True, text=True, timeout=120, check=True
        )
    except FileNotFoundError:
        # Try legacy convert command
        subprocess.run(
            ["convert", "-density", str(density), str(pdf_path),
             "-background", "white", "-alpha", "remove",
             str(output_pattern)],
            capture_output=True, text=True, timeout=120, check=True
        )
    # List generated images
    return sorted(output_dir.glob(f"{prefix}-*.png"))


def compare_images(img1, img2, diff_output):
    """Compare two images and generate a diff image."""
    # Get dimensions and resize if needed
    def get_size(img):
        try:
            r = subprocess.run(
                ["magick", "identify", "-format", "%wx%h", str(img)],
                capture_output=True, text=True, timeout=10
            )
        except FileNotFoundError:
            r = subprocess.run(
                ["identify", "-format", "%wx%h", str(img)],
                capture_output=True, text=True, timeout=10
            )
        return r.stdout.strip()

    size1 = get_size(img1)
    size2 = get_size(img2)

    # If different sizes, resize img2 to match img1
    actual_img2 = img2
    if size1 != size2:
        resized = img2.parent / f"resized-{img2.name}"
        try:
            subprocess.run(
                ["magick", str(img2), "-resize", f"{size1}!", str(resized)],
                capture_output=True, text=True, timeout=30, check=True
            )
        except FileNotFoundError:
            subprocess.run(
                ["convert", str(img2), "-resize", f"{size1}!", str(resized)],
                capture_output=True, text=True, timeout=30, check=True
            )
        actual_img2 = resized

    try:
        result = subprocess.run(
            ["magick", "compare", "-metric", "AE",
             str(img1), str(actual_img2), str(diff_output)],
            capture_output=True, text=True, timeout=30
        )
    except FileNotFoundError:
        result = subprocess.run(
            ["compare", "-metric", "AE",
             str(img1), str(actual_img2), str(diff_output)],
            capture_output=True, text=True, timeout=30
        )
    # AE metric outputs "N (pct)" to stderr, e.g. "48 (2.20694e-05)"
    try:
        raw = result.stderr.strip().split()[0]
        diff_pixels = int(float(raw))
    except (ValueError, IndexError):
        diff_pixels = -1
    return diff_pixels


def main():
    parser = argparse.ArgumentParser(
        description="PDF Visual Regression — Pixel-level comparison of two PDF versions. "
                    "Converts PDF pages to images, then highlights visual differences. "
                    "Requires: ImageMagick (convert + compare commands).",
        epilog=(
            "Modes:\n"
            "  One argument:   compare master CV.pdf against the application's CV PDF\n"
            "  Two arguments:  compare pdf1 directly against pdf2"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "path1",
        metavar="application-dir|pdf1",
        help="Application directory (single-arg mode) or first PDF path (two-arg mode)",
    )
    parser.add_argument(
        "pdf2",
        metavar="pdf2",
        nargs="?",
        default=None,
        help="Second PDF path (two-arg mode only)",
    )
    args = parser.parse_args()

    if not check_imagemagick():
        print("❌ ImageMagick not found.")
        print("   Install: brew install imagemagick")
        sys.exit(1)

    # Determine mode: app dir or two PDFs
    if args.pdf2 is None:
        app_dir = Path(args.path1)
        if not app_dir.is_dir():
            print(f"❌ Not a directory: {app_dir}")
            sys.exit(1)

        # Find application CV PDF and compare to master
        app_cv = list(app_dir.glob("CV - *.pdf"))
        master_cv = Path("CV.pdf")

        if not app_cv:
            print(f"❌ No CV PDF found in {app_dir}/")
            print("   Build first: make app NAME=...")
            sys.exit(1)
        if not master_cv.exists():
            print("❌ Master CV.pdf not found. Build first: make")
            sys.exit(1)

        pdf1 = master_cv
        pdf2 = app_cv[0]
    else:
        pdf1 = Path(args.path1)
        pdf2 = Path(args.pdf2)
        if not pdf1.exists() or not pdf2.exists():
            print(f"❌ File not found: {pdf1 if not pdf1.exists() else pdf2}")
            sys.exit(1)

    print(f"🔍 Visual diff:")
    print(f"   A: {pdf1}")
    print(f"   B: {pdf2}")
    print()

    # Create temp directory for images
    diff_dir = Path(".visual-diff")
    diff_dir.mkdir(exist_ok=True)

    try:
        print("📄 Converting PDFs to images...")
        imgs_a = pdf_to_images(pdf1, diff_dir, "a")
        imgs_b = pdf_to_images(pdf2, diff_dir, "b")

        max_pages = max(len(imgs_a), len(imgs_b))

        if max_pages == 0:
            print("❌ No pages found in PDFs")
            return 1

        print(f"   A: {len(imgs_a)} page(s), B: {len(imgs_b)} page(s)")
        print()

        total_diff = 0
        has_diff = False

        for i in range(max_pages):
            page_num = i + 1

            if i >= len(imgs_a):
                print(f"   Page {page_num}: 🆕 New page in B (not in A)")
                has_diff = True
                continue
            if i >= len(imgs_b):
                print(f"   Page {page_num}: 🗑️  Page removed in B")
                has_diff = True
                continue

            diff_path = diff_dir / f"diff-{i}.png"
            diff_pixels = compare_images(imgs_a[i], imgs_b[i], diff_path)

            if diff_pixels == 0:
                print(f"   Page {page_num}: ✅ Identical")
            elif diff_pixels > 0:
                has_diff = True
                total_diff += diff_pixels
                print(f"   Page {page_num}: 📝 {diff_pixels:,} pixels changed → {diff_path}")
            else:
                print(f"   Page {page_num}: ⚠️  Could not compare (different dimensions?)")
                has_diff = True

        print()
        if has_diff:
            print(f"📊 Total: {total_diff:,} pixels changed across {max_pages} page(s)")
            print(f"   Diff images saved in: {diff_dir}/")
            print()
            print("   Open diff images:")
            for f in sorted(diff_dir.glob("diff-*.png")):
                print(f"     open {f}")
        else:
            print("✅ PDFs are visually identical")

    except subprocess.CalledProcessError as e:
        print(f"❌ ImageMagick error: {e.stderr}")
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
