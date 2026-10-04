"""pytest ayarı: proje kökünü içe aktarma yoluna ekler."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
