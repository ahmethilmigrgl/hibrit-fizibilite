"""
Hugging Face veri deposuna yükleme — v4'te src/v4_yayin.py veri alt komutuna taşındı (depo düzeni data/ ile birebir aynı;
bkz. hf/README.md). Bu betik geriye dönük uyumluluk için o komutu çağırır.

Çalıştırma: .venv/bin/python src/v2_hf_yukle.py [--kuru]   ≡   .venv/bin/python src/v4_yayin.py veri [--kuru]
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.v4_yayin import veri

if __name__ == "__main__":
    veri("--kuru" in sys.argv)
