"""
v4 yayın: GitHub reposu, Hugging Face veri deposu (gridler) ve Hugging Face Space (canlı uygulama).

Token'lar yalnız .env'den okunur (GITHUB_TOKEN, HF_TOKEN) ve hiçbir yere yazılmaz/yazdırılmaz; git'e kimlik bilgisi bir
kerelik credential helper ile ortam değişkeninden verilir (git config'e kaydedilmez).

Alt komutlar:
    yer-tutucu --github <kullanıcı> --repo <ad> --hf <kullanıcı>   README, Space kartı, Vaka sayfası ve config'deki yer tutucular
    github                                                          origin ekle; main, dallar ve etiketleri it
    veri [--kuru]                                                   data/grid → HF dataset <hf>/hibrit-fizibilite-veri (+ README, "v1" etiketi)
    space [--kuru]                                                  git HEAD + space/Dockerfile + space/README.md → HF Space <hf>/hibrit-fizibilite
Çalıştırma: .venv/bin/python src/v4_yayin.py <alt komut> ...
"""

import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dotenv import load_dotenv

from src.ayarlar import KOK, config_oku, deger

SPACE_ADI = "hibrit-fizibilite"
VERI_DESEN = ["grid/*/v1/**/*.npz", "grid/*/v1/*.npz", "grid/*/v1/manifest.json", "grid/*/v1/*.tif"]


def _token(ad: str) -> str:
    load_dotenv(KOK / ".env")
    t = os.getenv(ad)
    if not t:
        sys.exit(f".env içinde {ad} yok (bkz. .env.example).")
    return t


def _degistir(yol: Path, eslesmeler: list[tuple[str, str]]) -> None:
    s = yol.read_text(encoding="utf-8")
    y = s
    for a, b in eslesmeler:
        y = y.replace(a, b)
    if y != s:
        yol.write_text(y, encoding="utf-8")
        print(f"  güncellendi: {yol.relative_to(KOK)}")


def yer_tutucu(gh: str, repo: str, hf: str) -> None:
    gh_url = f"https://github.com/{gh}/{repo}"
    e = [("https://github.com/KULLANICI/hibrit-fizibilite", gh_url), ("HFKULLANICI", hf), ("GHKULLANICI/GHREPO", f"{gh}/{repo}")]
    for p in ("README.md", "README.tr.md", "space/README.md", "uygulama/sayfa_vaka.py", "hf/README.md", "docs/PROJE_OZETI.md"):
        if (KOK / p).exists():
            _degistir(KOK / p, e)
    _degistir(KOK / "config.yaml", [('repo_id: "KULLANICI/hibrit-fizibilite-veri"', f'repo_id: "{hf}/hibrit-fizibilite-veri"')])


def _gh_bilgisi() -> tuple[str, str]:
    s = (KOK / "uygulama" / "sayfa_vaka.py").read_text(encoding="utf-8")
    m = re.search(r'REPO_URL = "https://github.com/([^/"]+)/([^/"]+)"', s)
    if not m or m.group(1) == "KULLANICI":
        sys.exit("Önce: yer-tutucu --github ... --repo ... --hf ...")
    return m.group(1), m.group(2)


def github() -> None:
    gh, repo = _gh_bilgisi()
    tok = _token("GITHUB_TOKEN")
    url = f"https://github.com/{gh}/{repo}.git"
    uzak = subprocess.run(["git", "remote"], cwd=KOK, capture_output=True, text=True).stdout.split()
    if "origin" not in uzak:
        subprocess.run(["git", "remote", "add", "origin", url], cwd=KOK, check=True)
    yardimci = '!f() { echo username=x-access-token; echo "password=$GH_YAYIN_TOKEN"; }; f'
    env = {**os.environ, "GH_YAYIN_TOKEN": tok, "GIT_TERMINAL_PROMPT": "0"}
    for arg in (["--all"], ["--tags"]):
        r = subprocess.run(["git", "-c", "credential.helper=", "-c", f"credential.helper={yardimci}", "push", "origin", *arg], cwd=KOK, env=env,
                           capture_output=True, text=True)  # fmt: skip
        print(("✓ " if r.returncode == 0 else "✗ ") + " ".join(arg), (r.stderr or r.stdout).replace(tok, "***")[-600:])
        if r.returncode:
            sys.exit(1)


def _hf_kullanici() -> str:
    rid = deger(config_oku()["v2"]["veri_deposu"])["repo_id"]
    if rid.startswith("KULLANICI/"):
        sys.exit("Önce: yer-tutucu --github ... --repo ... --hf ...")
    return rid.split("/")[0]


def veri(kuru: bool) -> None:
    from huggingface_hub import HfApi

    d = deger(config_oku()["v2"]["veri_deposu"])
    data = KOK / "data"
    dosyalar = [p for desen in VERI_DESEN for p in data.glob(desen)]
    dosyalar = sorted(set(dosyalar))
    print(f"Depo {d['repo_id']} (dataset): {len(dosyalar)} dosya, {sum(p.stat().st_size for p in dosyalar) / 1e6:.0f} MB")
    if kuru:
        return
    api = HfApi(token=_token("HF_TOKEN"))
    api.create_repo(d["repo_id"], repo_type="dataset", exist_ok=True, private=False)
    api.upload_file(path_or_fileobj=str(KOK / "hf" / "README.md"), path_in_repo="README.md", repo_id=d["repo_id"], repo_type="dataset")
    api.upload_large_folder(repo_id=d["repo_id"], repo_type="dataset", folder_path=str(data), allow_patterns=VERI_DESEN)
    try:
        api.create_tag(d["repo_id"], tag=d["revizyon"], repo_type="dataset")
    except Exception as ex:  # etiket zaten varsa
        print("  etiket:", type(ex).__name__)
    print("✓ veri deposu:", f"https://huggingface.co/datasets/{d['repo_id']}")


def space(kuru: bool) -> None:
    from huggingface_hub import HfApi

    hf = _hf_kullanici()
    rid = f"{hf}/{SPACE_ADI}"
    gecici = Path(tempfile.mkdtemp(prefix="space_"))
    try:
        arsiv = subprocess.run(["git", "archive", "HEAD"], cwd=KOK, capture_output=True, check=True).stdout
        subprocess.run(["tar", "-x", "-C", str(gecici)], input=arsiv, check=True)
        shutil.move(gecici / "README.md", gecici / "README_github.md")
        shutil.copy(KOK / "space" / "README.md", gecici / "README.md")
        shutil.copy(KOK / "space" / "Dockerfile", gecici / "Dockerfile")
        boyut = sum(p.stat().st_size for p in gecici.rglob("*") if p.is_file())
        print(f"Space {rid}: {sum(1 for p in gecici.rglob('*') if p.is_file())} dosya, {boyut / 1e6:.0f} MB")
        if kuru:
            return
        api = HfApi(token=_token("HF_TOKEN"))
        api.create_repo(rid, repo_type="space", space_sdk="docker", exist_ok=True, private=False)
        api.upload_folder(
            folder_path=str(gecici), repo_id=rid, repo_type="space", delete_patterns="*", commit_message="Uygulama güncellemesi"
        )
        print("✓ Space:", f"https://huggingface.co/spaces/{rid}")
    finally:
        shutil.rmtree(gecici, ignore_errors=True)


def main() -> None:
    a = sys.argv[1:]
    if not a:
        sys.exit(__doc__)
    if a[0] == "yer-tutucu":
        g = dict(zip(a[1::2], a[2::2], strict=False))
        yer_tutucu(g["--github"], g["--repo"], g["--hf"])
    elif a[0] == "github":
        github()
    elif a[0] == "veri":
        veri("--kuru" in a)
    elif a[0] == "space":
        space("--kuru" in a)
    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    main()
