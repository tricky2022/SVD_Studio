"""Render the application icon to PNG/ICO for packaging."""
import sys

sys.path.insert(0, ".")

from PySide6.QtGui import QColor, QImage, QPainter
from PySide6.QtWidgets import QApplication

from svdstudio.ui.app_icon import make_app_icon

app = QApplication([])
for size in (16, 32, 48, 64, 128, 256):
    pixmap = make_app_icon().pixmap(size, size)
    image = pixmap.toImage().convertToFormat(QImage.Format.Format_ARGB32)
    # paint over transparent with rounded backdrop already in icon; just save
    image.save(f"resources/icons/svd-studio-{size}.png")
print("png done")
try:
    from PIL import Image
    img = Image.open("resources/icons/svd-studio-256.png")
    img.save("resources/icons/svd-studio.ico", sizes=[(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    print("ico done")
except ImportError:
    print("Pillow missing: pip install pillow to generate .ico")
