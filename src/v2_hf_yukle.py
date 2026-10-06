"""
Hugging Face veri deposuna yükleme (kullanıcı çalıştırır; token yalnız .env'de HF_TOKEN olarak, asla koda/git'e girmez).

Ön koşul: huggingface.co hesabı, "write" yetkili erişim token'ı (.env: HF_TOKEN), config.yaml → v2.veri_deposu.repo_id
("<kullanici>/hibrit-fizibilite-veri"). Yükleme sonunda depoya "v1" etiketi konur.

Çalıştırma: uv pip install huggingface_hub --python .venv/bin/python && .venv/bin/python src/v2_hf_yukle.py [--kuru]
"""

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dotenv import load_dotenv

from src.ayarlar import KOK, config_oku, deger


def plan() -> list[tuple[Path, str]]:
    p = []
    for f in sorted((KOK / "data" / "grid" / "era5_tr" / "v1").glob("*.npz")):
        if not f.name.endswith(".tmp.npz"):
            p.append((f, f"era5_tr/v1/noktalar/{f.name}"))
    p.append((KOK / "data" / "grid" / "era5_tr" / "v1" / "manifest.json", "era5_tr/v1/manifest.json"))
    for f in sorted((KOK / "data" / "grid" / "gwa_tr" / "v1" / "karolar").glob("*.npz")):
        p.append((f, f"gwa_tr/v1/karolar/{f.name}"))
    p.append((KOK / "data" / "grid" / "gwa_tr" / "v1" / "gwa_tr_250m_ws100_cog.tif", "gwa_tr/v1/gwa_tr_250m_ws100_cog.tif"))
    p.append((KOK / "hf" / "README.md", "README.md"))
    return p


def main() -> None:
    d = deger(config_oku()["v2"]["veri_deposu"])
    dosyalar = plan()
    eksik = [str(a) for a, _ in dosyalar if not a.exists()]
    print(
        f"Depo: {d['repo_id']} | {len(dosyalar)} dosya, {sum(a.stat().st_size for a, _ in dosyalar if a.exists()) / 1e6:.0f} MB | eksik: {len(eksik)}"
    )
    if "--kuru" in sys.argv or eksik:
        if eksik:
            print("Önce eksik dosyaları üretin (ERA5 indirmesi bitmeli):", eksik[:5])
        return
    load_dotenv(KOK / ".env")
    token = os.getenv("HF_TOKEN")
    if not token:
        sys.exit(".env içinde HF_TOKEN yok.")
    from huggingface_hub import CommitOperationAdd, HfApi

    api = HfApi(token=token)
    api.create_repo(d["repo_id"], repo_type="dataset", exist_ok=True, private=False)
    for i in range(0, len(dosyalar), 400):  # büyük commit'leri parçala
        ops = [CommitOperationAdd(path_in_repo=hedef, path_or_fileobj=str(kaynak)) for kaynak, hedef in dosyalar[i : i + 400]]
        api.create_commit(d["repo_id"], repo_type="dataset", operations=ops, commit_message=f"Veri yükleme {i // 400 + 1}")
        print(f"  {min(i + 400, len(dosyalar))}/{len(dosyalar)}")
    api.create_tag(d["repo_id"], repo_type="dataset", tag=d["revizyon"], exist_ok=True)
    print("Tamam. Uygulama artık", f"https://huggingface.co/datasets/{d['repo_id']}", "adresinden okuyabilir.")


if __name__ == "__main__":
    main()
