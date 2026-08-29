#!/usr/bin/env python3
"""Generate deterministic product-label photos for local OCR/barcode smoke tests."""

from __future__ import annotations

import argparse
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

L = {
    "0": "0001101", "1": "0011001", "2": "0010011", "3": "0111101", "4": "0100011",
    "5": "0110001", "6": "0101111", "7": "0111011", "8": "0110111", "9": "0001011",
}
G = {
    "0": "0100111", "1": "0110011", "2": "0011011", "3": "0100001", "4": "0011101",
    "5": "0111001", "6": "0000101", "7": "0010001", "8": "0001001", "9": "0010111",
}
R = {
    "0": "1110010", "1": "1100110", "2": "1101100", "3": "1000010", "4": "1011100",
    "5": "1001110", "6": "1010000", "7": "1000100", "8": "1001000", "9": "1110100",
}
PARITY = {
    "0": "LLLLLL", "1": "LLGLGG", "2": "LLGGLG", "3": "LLGGGL", "4": "LGLLGG",
    "5": "LGGLLG", "6": "LGGGLL", "7": "LGLGLG", "8": "LGLGGL", "9": "LGGLGL",
}


def font(size: int):
    try:
        return ImageFont.truetype("DejaVuSans-Bold.ttf", size)
    except OSError:
        return ImageFont.load_default()


def check_digit(first12: str) -> str:
    total = 0
    for index, char in enumerate(first12):
        total += int(char) * (1 if index % 2 == 0 else 3)
    return str((10 - total % 10) % 10)


def ean13_bits(code: str) -> str:
    if len(code) != 13 or not code.isdigit():
        raise ValueError("EAN-13 code must contain 13 digits")
    parity = PARITY[code[0]]
    left = "".join((L if mode == "L" else G)[digit] for mode, digit in zip(parity, code[1:7]))
    right = "".join(R[digit] for digit in code[7:])
    return "101" + left + "01010" + right + "101"


def draw_ean13(draw: ImageDraw.ImageDraw, *, x: int, y: int, code: str, module: int = 4, height: int = 120) -> None:
    bits = ean13_bits(code)
    quiet = 12 * module
    x += quiet
    for index, bit in enumerate(bits):
        if bit == "1":
            draw.rectangle((x + index * module, y, x + (index + 1) * module - 1, y + height), fill="black")
    draw.text((x + 18 * module, y + height + 8), code, fill="black", font=font(22))


def generate(output: Path, count: int = 4) -> None:
    output = output.expanduser().resolve()
    output.mkdir(parents=True, exist_ok=True)
    for index in range(1, count + 1):
        sku = f"MOCK-{index:03d}"
        base = f"622000000{index:03d}"[:12]
        code = base + check_digit(base)
        image = Image.new("RGB", (900, 650), "white")
        draw = ImageDraw.Draw(image)
        draw.rectangle((0, 0, 900, 95), fill=(28, 33, 42))
        draw.text((38, 25), "PRODUCT LABEL EVIDENCE", fill="white", font=font(34))
        draw.text((55, 150), f"SKU: {sku}", fill="black", font=font(52))
        draw.text((55, 225), f"MODEL: TEST-M{index:03d}", fill="black", font=font(42))
        draw.text((55, 285), "LOCAL OCR BARCODE TEST", fill="black", font=font(28))
        draw_ean13(draw, x=180, y=360, code=code)
        image.save(output / f"LOCAL_EVIDENCE_{index:02d}.jpg", "JPEG", quality=96, subsampling=0)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--count", type=int, default=4)
    args = parser.parse_args()
    generate(args.output, max(1, args.count))
    print(f"Generated {max(1, args.count)} local-evidence fixture photos in {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
