"""
Streamlit Community Cloud giriş noktası.

Cloud, bağımlılık dosyasını önce giriş betiğinin klasöründe arar; bu klasördeki hafif requirements.txt
(requirements-app.txt ile aynı) sayesinde pyomo/pvlib gibi hat bağımlılıkları kurulmaz. Uygulamanın kendisi kökteki app.py.
"""

import runpy
from pathlib import Path

runpy.run_path(str(Path(__file__).resolve().parents[1] / "app.py"), run_name="__main__")
