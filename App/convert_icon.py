from PIL import Image
import os

png_path = "assets/icon.png"
ico_path = "assets/icon.ico"

if os.path.exists(png_path):
    img = Image.open(png_path)
    # Sizes standard for Windows icon
    sizes = [(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
    img.save(ico_path, sizes=sizes)
    print(f"Icon converted: {ico_path}")
else:
    print(f"Source PNG not found: {png_path}")
