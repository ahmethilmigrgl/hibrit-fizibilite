"""
EPİAŞ'tan saatlik PTF ve gerçek zamanlı üretim verisinin çekilmesi ve UTC'ye çevrilmesi.

Zaman dönüşümü (önemli):
    EPİAŞ zaman damgaları Türkiye yerel saatindedir ve ofset içerir (ör. 2015-03-29T04:00:00+03:00).
    Türkiye 7 Eylül 2016'ya kadar yaz saati uyguluyordu (kış UTC+2, yaz UTC+3); sonrasında sabit UTC+3.
    EPİAŞ her gün için 24 satır verir. Bu yüzden geçiş günlerinde:
      • İlkbahar (saat ileri, 23 saatlik gün): yaşanmamış saat için fiyatı/üretimi 0 olan bir
        YER TUTUCU satır vardır; 'date' alanı bir sonraki saatle çakışır, 'hour' etiketi ise
        yerel saatle uyuşmaz → bu satır atılır.
      • Sonbahar (saat geri, 25 saatlik gün): iki kez yaşanan saatin ilki verilmez → UTC'de bir
        saat eksik kalır → komşu saatlerden doğrusal enterpolasyonla doldurulur ve
        'dolduruldu' sütununda işaretlenir.
    Tüm çıktılar UTC, saat başı indekslidir.

API limitleri (deneyerek doğrulandı, 2026-10-03):
    • PTF (/v1/markets/dam/data/mcp): 1 yıllık istek sorunsuz → yıllık parçalar
    • Gerçek zamanlı üretim (/v1/generation/data/realtime-generation): en fazla 3 ay → çeyreklik parçalar
"""

from __future__ import annotations

import pandas as pd

from src.piyasa.epias import EpiasIstemcisi, tarih_metni

PTF_YOLU = "/v1/markets/dam/data/mcp"
URETIM_YOLU = "/v1/generation/data/realtime-generation"
SANTRAL_LISTESI_YOLU = "/v1/generation/data/powerplant-list"


def _parcalar(bas: pd.Timestamp, son: pd.Timestamp, frekans: str):
    """[bas, son] aralığını takvim parçalarına böler (ör. 'YS' yıllık, 'QS' çeyreklik)."""
    sinirlar = list(pd.date_range(bas, son, freq=frekans))
    if not sinirlar or sinirlar[0] != bas:
        sinirlar = [bas] + sinirlar
    for i, b in enumerate(sinirlar):
        s = sinirlar[i + 1] - pd.Timedelta(hours=1) if i + 1 < len(sinirlar) else son
        if b <= s:
            yield b, s


def _utc_cevir(kayitlar: list[dict], deger_sutunlari: list[str]) -> pd.DataFrame:
    """EPİAŞ kayıtlarını UTC saatlik tabloya çevirir (yaz saati kuralları için modül notuna bakın)."""
    df = pd.DataFrame(kayitlar)
    if df.empty:
        return df
    # Her kaydın kendi ofseti var → doğrudan UTC'ye çevrilebilir
    df["zaman_utc"] = pd.to_datetime(df["date"], utc=True)
    # Yerel saat etiketi ile 'date' alanının yerel saati (metindeki THH) uyuşmayan satırlar
    # ilkbahar yer tutucularıdır
    yerel_saat = df["date"].str.slice(11, 13).astype(int)
    etiket_saat = df["hour"].str.slice(0, 2).astype(int)
    yer_tutucu = yerel_saat != etiket_saat
    df = df.loc[~yer_tutucu]
    df = df.drop_duplicates("zaman_utc", keep="last").set_index("zaman_utc").sort_index()
    return df[deger_sutunlari]


def _tam_saatlik(df: pd.DataFrame, bas_utc: pd.Timestamp, son_utc: pd.Timestamp) -> pd.DataFrame:
    """Eksik UTC saatlerini ekler, doğrusal enterpolasyonla doldurur ve işaretler."""
    tam = pd.date_range(bas_utc, son_utc, freq="h", tz="UTC", name="zaman_utc")
    df = df.reindex(tam)
    df["dolduruldu"] = df.isna().any(axis=1)
    sayisal = df.columns.drop("dolduruldu")
    df[sayisal] = df[sayisal].interpolate(limit=3, limit_direction="both")
    return df


def ptf_cek(istemci: EpiasIstemcisi, bas: str, son: str) -> pd.DataFrame:
    """
    Saatlik PTF (TL, USD, EUR / MWh), UTC indeksli.
    bas, son: yerel tarih metni ('2014-01-01', '2026-09-30'); son günün 23:00'ı dahildir.
    USD/EUR karşılıkları EPİAŞ'ın kendisinden gelir (TCMB gösterge döviz alış kuru).
    """
    bas_y = pd.Timestamp(bas).tz_localize("Europe/Istanbul")
    son_y = (pd.Timestamp(son) + pd.Timedelta(hours=23)).tz_localize("Europe/Istanbul")
    kayitlar = []
    for b, s in _parcalar(bas_y.tz_localize(None), son_y.tz_localize(None), "YS"):
        govde = {"startDate": tarih_metni(b), "endDate": tarih_metni(s)}
        kayitlar += istemci.onbellekli_istek("ptf", PTF_YOLU, govde)["items"]
    df = _utc_cevir(kayitlar, ["price", "priceUsd", "priceEur"])
    df = df.rename(columns={"price": "ptf_tl", "priceUsd": "ptf_usd", "priceEur": "ptf_eur"})
    return _tam_saatlik(df, bas_y.tz_convert("UTC"), son_y.tz_convert("UTC"))


URETIM_SUTUNLARI = {
    "total": "toplam", "wind": "ruzgar", "sun": "gunes", "naturalGas": "dogalgaz",
    "importCoal": "ithal_komur", "lignite": "linyit", "dammedHydro": "barajli",
    "river": "akarsu", "geothermal": "jeotermal", "biomass": "biyokutle",
}


def uretim_cek(istemci: EpiasIstemcisi, bas: str, son: str,
               santral_id: int | None = None) -> pd.DataFrame:
    """
    Saatlik gerçek zamanlı üretim [MWh], UTC indeksli. santral_id verilirse tek santral,
    verilmezse Türkiye geneli kaynak bazında. API sınırı 3 ay olduğu için çeyreklik parçalarla çekilir.
    """
    bas_y = pd.Timestamp(bas).tz_localize("Europe/Istanbul")
    son_y = (pd.Timestamp(son) + pd.Timedelta(hours=23)).tz_localize("Europe/Istanbul")
    servis = f"uretim_santral_{santral_id}" if santral_id else "uretim_turkiye"
    kayitlar = []
    for b, s in _parcalar(bas_y.tz_localize(None), son_y.tz_localize(None), "QS"):
        govde = {"startDate": tarih_metni(b), "endDate": tarih_metni(s)}
        if santral_id:
            govde["powerPlantId"] = santral_id   # dikkat: 'powerplantId' yazılırsa filtre sessizce yok sayılır
        kayitlar += istemci.onbellekli_istek(servis, URETIM_YOLU, govde)["items"]
    sutunlar = ["total", "wind"] if santral_id else list(URETIM_SUTUNLARI)
    df = _utc_cevir(kayitlar, sutunlar).rename(columns=URETIM_SUTUNLARI)
    return _tam_saatlik(df, bas_y.tz_convert("UTC"), son_y.tz_convert("UTC"))


def santral_listesi(istemci: EpiasIstemcisi) -> pd.DataFrame:
    """EPİAŞ/TEİAŞ santral listesi (id, ad, EIC, kısa ad)."""
    return pd.DataFrame(istemci.onbellekli_istek("santral_listesi", SANTRAL_LISTESI_YOLU, yontem="GET")["items"])


def auf_cek(istemci: EpiasIstemcisi, bas: str = "2022-04-01", son: str = "2023-09-30") -> pd.DataFrame:
    """
    Azami Uzlaştırma Fiyatı (AUF), aylık, kaynak bazında [TL/MWh] (1 Nisan 2022 – 30 Eylül 2023).
    'other' = diğer kaynaklar (yenilenebilir dahil); 'gopMaxPrice' = GÖP azami fiyat limiti.
    API sınırı 3 ay → çeyreklik parçalar. Bir ay içinde GÖP limiti değişirse birden fazla satır gelir.
    """
    satirlar = []
    for b, s in _parcalar(pd.Timestamp(bas), pd.Timestamp(son) + pd.Timedelta(hours=23), "QS"):
        govde = {"startDate": tarih_metni(b), "endDate": tarih_metni(s)}
        satirlar += istemci.onbellekli_istek("auf", "/v1/markets/data/maximum-settlement-price", govde)["items"]
    df = pd.DataFrame(satirlar).drop_duplicates()
    df["ay"] = df["period"].str.slice(0, 7)
    return (df.groupby("ay")
              .agg(auf_yenilenebilir=("other", "first"), auf_dogalgaz=("naturalGas", "first"),
                   auf_ithal_komur=("importedCoal", "first"), auf_yerli_komur=("localCoal", "first"),
                   gop_azami_fiyat=("gopMaxPrice", "max"))
              .sort_index())


YAN_HIZMET_YOLLARI = {
    "pfk_fiyat": ("/v1/markets/ancillary-services/data/primary-frequency-capacity-price", "price"),
    "sfk_fiyat": ("/v1/markets/ancillary-services/data/secondary-frequency-capacity-price", "price"),
    "pfk_miktar": ("/v1/markets/ancillary-services/data/primary-frequency-capacity-amount", "amount"),
    "sfk_miktar": ("/v1/markets/ancillary-services/data/secondary-frequency-capacity-amount", "amount"),
    "smf": ("/v1/markets/bpm/data/system-marginal-price", "systemMarginalPrice"),
}


def saatlik_seri_cek(istemci: EpiasIstemcisi, ad: str, bas: str, son: str, frekans: str = "QS") -> pd.Series:
    """
    Yan hizmet kapasite fiyat/miktarı ve SMF gibi saatlik tek değerli seriler (TSİ → UTC).
    Fiyatlar TL/MW-saat (PFK/SFK) veya TL/MWh (SMF), miktarlar MW. 'hour' alanı bazı servislerde tamsayı,
    bazılarında ISO tarih; UTC dönüşümü 'date' alanındaki ofsetten yapılır.
    """
    yol, alan = YAN_HIZMET_YOLLARI[ad]
    bas_y = pd.Timestamp(bas).tz_localize("Europe/Istanbul")
    son_y = (pd.Timestamp(son) + pd.Timedelta(hours=23)).tz_localize("Europe/Istanbul")
    kayit = []
    for b, s in _parcalar(bas_y.tz_localize(None), son_y.tz_localize(None), frekans):
        kayit += istemci.onbellekli_istek(ad, yol, {"startDate": tarih_metni(b), "endDate": tarih_metni(s)})["items"]
    df = pd.DataFrame(kayit)
    df["zaman_utc"] = pd.to_datetime(df["date"], utc=True)
    df = df.drop_duplicates("zaman_utc").set_index("zaman_utc").sort_index()
    return df[alan].astype(float).rename(ad)


def yekg_fiyat_cek(istemci: EpiasIstemcisi, bas: str, son: str) -> pd.DataFrame:
    """YEK-G (yenilenebilir enerji kaynak garanti) ağırlıklı ortalama fiyatı, kaynak türüne göre [TL, USD /MWh]."""
    kayit = []
    for b, s in _parcalar(pd.Timestamp(bas), pd.Timestamp(son) + pd.Timedelta(hours=23), "QS"):
        r = istemci.onbellekli_istek("yekg_fiyat", "/v1/markets/yek-g/data/weighted-average-price",
                                     {"startDate": tarih_metni(b), "endDate": tarih_metni(s)})
        kayit += r.get("items", [])
    return pd.DataFrame(kayit).drop_duplicates()


def talimat_ozeti_cek(istemci: EpiasIstemcisi, bas: str, son: str) -> pd.DataFrame:
    """
    Dengeleme Güç Piyasası saatlik YAL/YAT talimat özetleri [MWh] (sistem geneli; kaynak/santral kırılımı yayımlanmıyor).
    Kodlar: 0 = dengeleme, 1 = sistem kısıtı (iletim/güvenlik), 2 = yan hizmet. Pozitif değerlere çevrilir.
    """
    parcalar = []
    for yon, yol in [("yat", "/v1/markets/bpm/data/order-summary-down"), ("yal", "/v1/markets/bpm/data/order-summary-up")]:
        kayit = []
        for b, s in _parcalar(pd.Timestamp(bas), pd.Timestamp(son) + pd.Timedelta(hours=23), "MS"):
            kayit += istemci.onbellekli_istek(f"talimat_{yon}", yol, {"startDate": tarih_metni(b), "endDate": tarih_metni(s)})["items"]
        df = pd.DataFrame(kayit)
        df["zaman_utc"] = pd.to_datetime(df["date"], utc=True)
        df = df.drop_duplicates("zaman_utc").set_index("zaman_utc").sort_index()
        ad = "downRegulation" if yon == "yat" else "upRegulation"
        parcalar.append(pd.DataFrame({f"{yon}_0": df[f"{ad}ZeroCoded"].abs(), f"{yon}_1": df[f"{ad}OneCoded"].abs(),
                                      f"{yon}_2": df[f"{ad}TwoCoded"].abs()}).astype(float))
    return pd.concat(parcalar, axis=1)
