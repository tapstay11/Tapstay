#!/usr/bin/env python3
"""
Image optimization script for TapStay.
Converts images to high-efficiency WebP and optimized progressive JPEG.
"""
import os
import io
from PIL import Image

IMAGES_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "images")

def optimize_images():
    print(f"Optimizing images in: {IMAGES_DIR}")
    files = [f for f in sorted(os.listdir(IMAGES_DIR)) if f.lower().endswith(('.jpg', '.jpeg', '.png'))]
    
    total_before = 0
    total_after_jpg = 0
    total_webp = 0

    for filename in files:
        src_path = os.path.join(IMAGES_DIR, filename)
        orig_size = os.path.getsize(src_path)
        total_before += orig_size
        
        base_name, _ = os.path.splitext(filename)
        webp_path = os.path.join(IMAGES_DIR, f"{base_name}.webp")

        with Image.open(src_path) as img:
            rgb_img = img.convert("RGB")
            
            # 1. Save optimized WebP
            rgb_img.save(webp_path, "WEBP", quality=82, method=6)
            webp_size = os.path.getsize(webp_path)
            total_webp += webp_size

            # 2. Overwrite JPEG with progressive, optimized JPEG (stripped EXIF)
            temp_buf = io.BytesIO()
            rgb_img.save(temp_buf, "JPEG", quality=82, optimize=True, progressive=True)
            temp_size = temp_buf.tell()
            
            # If optimized JPEG is smaller, write it back
            if temp_size < orig_size:
                with open(src_path, "wb") as f:
                    f.write(temp_buf.getvalue())
                new_jpg_size = temp_size
            else:
                new_jpg_size = orig_size
            total_after_jpg += new_jpg_size

        saved_pct = (1 - webp_size / orig_size) * 100
        print(f"  ✓ {filename:<25}: {orig_size/1024:>6.1f} KB -> JPG: {new_jpg_size/1024:>6.1f} KB | WebP: {webp_size/1024:>6.1f} KB (-{saved_pct:.1f}%)")

    print("=" * 60)
    print(f"Total Original:       {total_before / (1024*1024):.2f} MB")
    print(f"Total Optimized JPEG: {total_after_jpg / (1024*1024):.2f} MB (-{(1 - total_after_jpg/total_before)*100:.1f}%)")
    print(f"Total WebP:           {total_webp / (1024*1024):.2f} MB (-{(1 - total_webp/total_before)*100:.1f}%)")

if __name__ == "__main__":
    optimize_images()
