# v3 Faz F — Portföy optimizasyonu ve performans izleme

Bu belge iki bölümden oluşur. §0 Faz F ön adımıdır (Ö1 v1 çift sayım etkisi, Ö2 bağlantı mesafesi belirsizliği). §1'den
itibaren Faz F gelir.

---

## 0. Ön adım

### 0.1 Ö1 — v1'de sigorta ve arazi kirası çift sayımı

Ayrıntı ve tüm tablolar: **[docs/v1_duzeltme_notu.md](v1_duzeltme_notu.md)**. Kod: `src/finans/model.py`
(`v1_cift_sayim_duzeltmesi`, `Varsayimlar.sigorta_res_haric`), `src/risk/degerleme.py`. Anahtar: config
`v1_duzeltme.cift_sayim` (varsayılan false) ya da `V1_CIFT_SAYIM=1`. Betikler `src/v3_O1_v1_duzeltme.py`,
`src/v3_O1_v2_kontrol.py` → `outputs/v3F/O1_*`, düzeltilmiş Monte Carlo `outputs/07/v1_cift_sayim/`.

| v1 nihai baz vaka (Ezine, YEKDEM opsiyonu + tüccar) | v1 | Düzeltilmiş |
|---|---|---|
| Beklenen NPV | −1,66 M$ | **+0,92 M$** |
| P(NPV > 0) | %42,4 | %48,7 |
| CVaR %5 | −28,0 M$ | −25,1 M$ |
| Azami edinim primi | 0 | 0,92 M$ |
| Durum tespiti bilgi değeri | 0 | 1,16 M$ |
| Karar (kural: E[NPV] > 0 ⇒ (a)) | (b) rafa kaldır | **(a) durum tespiti + ≤0,9 M$ teklif** |

- Excel modelinde düzeltilmiş senaryo seçilebilir. Senaryo sayısı 48'den 96'ya çıktı; 96/96 senaryo Python ile mutabık
  (azami fark 0), formül hatası yok.
- v2 motorunda aynı çift sayım var: Ezine, Gürün ve Susurluk'ta E[NPV] +2,4…+2,6 M$ iyileşiyor, karar değişmiyor. v3
  varsayılanında (FSA) çift sayım yok.

### 0.2 Ö2 — Bağlantı mesafesi belirsizliği

**Sorun.** Model en yakın uygun gerilimli trafo merkezine bağlanıldığını varsayıyor. TEİAŞ ise kapasitesi olan bir
merkezi ya da mevcut bir hatta girdi-çıktı bağlantısını atar. Lisanslı projeler için trafo merkezi kapasitesi
yayımlanmadığından atamayı önceden bilemeyiz; bu bir belirsizliktir.

**Veri.** YEKA RES-2025 (6) ve RES-2026 (8) bağlantı görüşleri: `data/atlas/teias_yeka_baglanti.csv`. Yarışma alanlarının
koordinatları yayımlanmadığı için "aynı yer" il düzeyinde yaklaşıklandı. Projenin ilindeki rüzgârlı ön tarama hücrelerinde
(il içi RES KF ≥ 75. yüzdelik) atanan gerilim sınıfına uygun en yakın trafo uzaklığının medyanı × güzergâh çarpanı 1,25
alındı (`src/v3_O2_baglanti_orani.py` → `data/atlas/baglanti_oranlari.csv`, `baglanti_orani.json`).

$$
r_i = \frac{\text{TEİAŞ'ın atadığı hat uzunluğu}_i}{1{,}25 \cdot \operatorname{medyan}_{c \in \text{il}_i} d_c^{\text{en yakın}}}
,\qquad \ln r \sim \mathcal{N}(\mu, \sigma^2)
$$

| | Değer |
|---|---|
| Gözlem | 14 santral alanı (4'ü mevcut hatta girdi-çıktı) |
| Medyan $e^{\mu}$ | 0,73 |
| Ortalama $e^{\mu + \sigma^2/2}$ | 1,14 |
| $\sigma$ (ln) | 0,94 (bootstrap %5–95: 0,61–1,14) |
| P10 / P90 | 0,22 / 2,45 |
| Gözlenen aralık | 0,13 (Sivas R26, girdi-çıktı) – 3,29 (Sivas R25, 210 km) |
| Girdi-çıktı hariç medyan | 1,10 |

**Yorum.** Atamalar ortalamada en yakın trafoya göre biraz daha uzun (×1,14) ama asıl özellik dağınıklık. TEİAŞ bazen çok
yakın bir hatta girdi-çıktı veriyor, bazen 200 km'lik yeni hat istiyor. Faz E'deki "2–12 kat uzun" yorumu, 400 kV
atamaları 154 kV'luk en yakın trafoyla kıyasladığı için yanlıştı; düzeltildi.

**Modele bağlantı** (`src/cbs/baglanti.belirsizlik`, `carpan_ornekle`; config `v3.baglanti.belirsizlik.aktif`):

$$
C(r) = C^{TM}_V + C^{fid}_V + r \cdot g\, d\, c^{hat}_V + C^{yol}, \qquad
\text{CAPEX}_{şebeke} = \mathbb{E}[C(r)] = C(e^{\mu + \sigma^2/2})
$$

- Deterministik kısımlar (MILP, hızlı tarama, başabaş) beklenen değeri kullanır.
- Monte Carlo'da her senaryoda $r_s$ çekilir ve şebeke CAPEX'i $C(r_s)/\mathbb{E}[C]$ ile çarpılır
  (`girdi["capex_sebeke"]`, `degerleme.nakit_akislari`). Çarpanın ortalaması 1.
- Hızlı taramada saha kartı beklenen değeri ve P10–P90 aralığını gösterir.
- Varsayım: oran 400 kV atamalarından ölçüldü (14'ün 12'si) ve 154 kV'luk 50 MW sahalara aktarıldı (iki 154 kV
  gözlemi 1,01 ve 1,23).

**Etki** (tam analiz, 2 çekirdek; `outputs/v3F/O2_once_sonra.csv`):

| Saha | Bağlantı, öncesi (M$) | Bağlantı, beklenen (P10–P90) | E[NPV] öncesi → sonrası | CVaR %5 öncesi → sonrası | Başabaş | Karar |
|---|---|---|---|---|---|---|
| Ezine | 5,59 | 5,64 (5,36–6,02) | −1,63 → −1,67 | −19,1 → −19,3 | 60,5 → 60,6 | rafa kaldır |
| Gürün | 10,30 | 10,76 (7,73–15,06) | −6,98 → −7,36 | −27,0 → −30,4 | 67,4 → 67,9 | rafa kaldır |
| Susurluk | 7,43 | 7,73 (5,76–10,51) | −3,34 → −3,58 | −28,4 → −29,7 | 61,3 → 61,5 | rafa kaldır |

Beklenen değerdeki etki küçük (−0,04…−0,37 M$), kuyruktaki etki büyük (CVaR −0,1…−3,3 M$). Trafoya yakın sahada
(Ezine 1,6 km) hat kalemi küçük olduğu için belirsizlik neredeyse önemsiz. Uzak sahada (Gürün 17,5 km) bağlantı tek
başına ±4 M$'lık bir risk kalemi.
