"""Convert assets/icons/icon_*.png to multi-size .ico files."""
from pathlib import Path

from PIL import Image

DEST = Path(__file__).resolve().parents[1] / "assets" / "icons"
SIZES = [(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]


def main() -> None:
    for png in sorted(DEST.glob("icon_*.png")):
        im = Image.open(png).convert("RGBA")
        w, h = im.size
        side = max(w, h)
        canvas = Image.new("RGBA", (side, side), (0, 0, 0, 0))
        canvas.paste(im, ((side - w) // 2, (side - h) // 2))
        base = canvas.resize((256, 256), Image.Resampling.LANCZOS)
        ico_path = png.with_suffix(".ico")
        base.save(ico_path, format="ICO", sizes=SIZES)
        print(f"Wrote {ico_path.name} ({ico_path.stat().st_size} bytes) from {png.name} {im.size}")


if __name__ == "__main__":
    main()
