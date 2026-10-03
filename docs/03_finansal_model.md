# Aşama 3 — Finansal Model

**Amaç:** Ezine'de GES, RES ve (Aşama 4'te) BESS kapasiteleri için proje değerini (NPV, IRR, LCOE,
borç kapasitesi) hesaplayan, hızlı ve vektörize bir değerleme çekirdeği kurmak. Dört referans
bataryasız konfigürasyonu üç fiyat seviyesi ve iki kanibalizasyon varyantı altında karşılaştırmak.

| | |
|---|---|
| Kodlar | `src/finans/veri.py` (profiller, fiyat şekli), `src/finans/fiyat_senaryosu.py`, `src/finans/model.py` (`proje_degerle`), `src/finans/borc.py` |
| Çalıştırma | `.venv/bin/python src/03_finansal_model.py` (~3 s) |
| Çıktılar | `outputs/03_finans/*.png`, `*.csv`, `nakit_akisi_b.xlsx` |
| Varsayımlar | `config.yaml` → `proje`, `finans`, `borc`, `teknoloji`, `fiyat_senaryolari` |

---

## 1. Çerçeve: neden reel USD?

- **TL'de model kurmak pratik değil.** Türkiye'de TL enflasyonu 2022'de %70'in üstüne çıktı ve son 10 yılda çoğu yıl çift hanelerdeydi. 30 yıllık TL projeksiyonu, enflasyon ve kur tahminine boğulur.
- **USD'de kurmak sektör pratiğiyle uyumlu.** Türkiye'de yenilenebilir yatırımların CAPEX'i (türbin, panel, batarya) dolar/avro bazlı, proje finansmanı da çoğunlukla USD/EUR ile yapılıyor. Elektrik fiyatı (PTF) ise uzun vadede yakıt maliyetleri (ithal gaz, kömür) üzerinden döviz bazlı fiyatlanıyor; Aşama 2'de PTF'nin USD karşılığı 2017–2025 arasında (kriz yılı 2022 hariç) 40–70 $/MWh bandında kaldı.
- **Model bu yüzden reel USD'de (2026 fiyatları) kuruldu:**
  - Gelir = satılan MWh × PTF'nin USD karşılığı.
  - Maliyetler reel USD'de sabit (TEİAŞ tarifeleri dahil; 2026 TL değerleri ~45 TL/USD ile çevrildi).
  - İskonto oranı **reel WACC**.
  - Nominal USD kalemler (borç faizi, borç servisi) ABD enflasyonuyla (%2,5) reele çevriliyor.
- **Kur riski bu varsayımın içinde gizli.** USD bazlı gelir varsayımı, TL'deki PTF'nin kur değişimini zamanla fiyatlara yansıttığını (tam geçiş) kabul eder. Gerçekte bu geçiş gecikmeli ve kısmi olabilir:
  - **2021 örneği:** Azami fiyat formülü geçmiş TL ortalamalarına bağlıydı ve TL hızla değer kaybederken geride kaldı. PTF'nin USD karşılığı bastırıldı (Aşama 2, bölüm 3).
  - **Uyumsuzluk:** Borç USD, gelir TL ödeniyor. Kurun ani sıçradığı ve fiyatın gecikmeyle uyum sağladığı dönemlerde nakit akışı açığı oluşur.
  - **Ne yapıldı?** Bu risk Aşama 5'te Monte Carlo'da "kur geçiş oranı" şokuyla modellenecek; burada fiyat seviyesi senaryoları kısmen bu riski temsil ediyor.

## 2. Formüller

**Zaman çizelgesi:**
- t = 0 → FID yılı (2026) başı.
- İnşaat yılları y = 0, 1 (CAPEX %40 / %60).
- İşletme yılları y = 2 … 31 (k = 1 … 30; COD 2028).
- Nakit akışları yıl sonunda gerçekleşir.

**Üretim ve satış (her yıl k, hava yılı w, fiyat şekli yılı s, saat t):**
- `G_t = GES_MW · kf^GES_t · (1 − δ_GES)^(k−1)`
- `R_t = RES_MW · kf^RES_t · (1 − δ_RES)^(k−1)`
- `Satılan_t = min(G_t + R_t + B_t, Şebeke_MW)`, burada `B_t` batarya net enjeksiyonu (Aşama 4 kancası).
- `Kesilen_t = G_t + R_t + B_t − Satılan_t`. Kesinti teknolojilere üretim payıyla (pro-rata) dağıtılır.
- Yıllık değerler **10 hava yılı × 2 fiyat şekli yılının ortalaması**dır, yani beklenen değer (P50).

**Gelir:**
- `Gelir_k = Σ_t Satılan_t · p_t − Δ_RES · p̄_k · E^RES_satılan,k`
- **Dengesizlik:** GES gelirinin %2'si, RES gelirinin %4'ü (gelir oranı olarak).

**FAVÖK:**
- `FAVÖK = Gelir − Dengesizlik − İşletme-bakım − Arazi − Sigorta − TEİAŞ bedelleri`
- `TEİAŞ = 3.470 $/MW-bağlantı/yıl + 3,8 $/MWh satılan`

**Vergi (kaldıraçsız):**
- `Vergi_k = %25 × max(0, FAVÖK_k − Amortisman_k − Augmentation_k − Söküm_k − devreden zarar)`
- Zarar 5 yıl ileri taşınır. Amortisman doğrusal, 10 yıl.

**Serbest nakit akışı (SNA):**
- İşletme yıllarında: `SNA = FAVÖK − Vergi − Augmentation − Söküm`
- İnşaat yıllarında: `SNA = −CAPEX`

**Değerleme:**
- `NPV = Σ_y SNA_y / (1 + WACC)^(y+1)`
- `IRR` = NPV'yi sıfır yapan oran (proje IRR'ı: kaldıraçsız, vergi sonrası, reel).

**LCOE (vergi öncesi, reel):**
- `LCOE = Σ_y (CAPEX + OPEX + Augmentation + Söküm)_y · DF_y / Σ_y Enerji_y · DF_y`, burada `DF_y = (1 + WACC)^−(y+1)`.
- **Teknoloji LCOE'si:** Teknolojinin kendi CAPEX/OPEX'i ve kurulu güç oranında şebeke payı, teknolojinin **kesinti öncesi** üretimine bölünür (IRENA ile karşılaştırılabilir tanım).
- **Satılan enerji LCOE'si:** Toplam maliyet / satılan enerji. Kesintinin maliyetini de içerir.

**Borç (heykelsi geri ödeme):**
- `CFADS_y = FAVÖK − Vergi − Augmentation − Söküm` (reel). Nominal CFADS = reel × (1 + π)^(y+1), π = %2,5.
- `Borç servisi_y = CFADS^nom_y(P90) / DSCR_hedef` (ilk 15 işletme yılı)
- `Borç = Σ Borç servisi_y / (1 + i)^(y − COD)`, en fazla CAPEX'in %75'i.
- **DSCR** = CFADS / borç servisi. Hedef 1,30 olarak P90 üretimiyle boyutlandırılır.
- **P90 üretim:** Konfigürasyonun satılan enerjisinin 10 hava yılı dağılımından `P90 = P50 × (1 − 1,282 × CV)`. Kesinti iyi yılları kırptığı için oran konfigürasyona bağlı: RES 0,927, (b) 0,941, (c) 0,952, GES 0,966.
- **Öz kaynak IRR:** P50 nakit akışı − borç servisi + faiz vergi kalkanı. Borç inşaat süresince CAPEX'le orantılı çekilir; inşaat dönemi faizi ihmal edildi.

## 3. Varsayımlar ve kaynakları

### 3.1 CAPEX (reel 2026 USD)

| Kalem | Değer | Kaynak / gerekçe |
|---|---|---|
| GES | **620.000 $/MWac** (DC/AC 1,2 dahil) | [IRENA RPGC 2025](https://www.irena.org/-/media/Files/IRENA/Agency/Publication/2026/Jul/IRENA_TEC_RPGC_2025_Executive_summary_2026.pdf): küresel ort. 667 $/kW (2025); Türkiye anahtar teslim ~500–600 bin $/MWp ([Enerji Ajansı](https://enerjiajansi.com.tr/ges-kurulum-maliyeti-ne-kadar/)) × 1,2 |
| RES | **1.150.000 $/MW** | Türkiye 2025 Q1: 300 MW için 300–350 M$ → 1,0–1,17 M$/MW ([Dünya](https://www.dunya.com/ekonomi/turkiye-ruzgar-gibi-ilk-ceyrekte-300-milyon-dolarlik-yatirim-haberi-823586)); IRENA 2025 küresel 976 $/kW (Çin ağırlıklı) |
| BESS enerji | **110.000 $/MWh** | [IRENA 2025](https://www.irena.org/-/media/Files/IRENA/Agency/Publication/2026/Jul/IRENA_TEC_RPGC_2025_Executive_summary_2026.pdf): 4 saatlik ~140 $/kWh; [BNEF 2025](https://www.energy-storage.news/battery-storage-system-prices-continue-to-fall-sharply-bnef-and-ember-reports-find/): ABD/Çin dışı 4 saatlik ~125 $/kWh (75 ekipman + 50 kurulum) |
| BESS güç | **90.000 $/MW** | Aynı kaynakların PCS, trafo ve şalt payı; 4 saatlikte toplam ≈ 132 $/kWh |
| Şebeke bağlantısı + trafo merkezi | **120.000 $/MW bağlantı** | Türkiye'de 100–300 bin $/MW ([maliyeti.com.tr](https://www.maliyeti.com.tr/ruzgar-santrali-maliyeti-2025/)); mesafeye bağlı |
| CAPEX takvimi | %40 / %60, 2 yıl inşaat | Sektör pratiği |

### 3.2 OPEX

| Kalem | Değer | Kaynak |
|---|---|---|
| GES sabit O&M | 12.000 $/MWac/yıl | [Lazard LCOE+ 2025](https://www.lazard.com/media/eijnqja3/lazards-lcoeplus-june-2025.pdf): 11–14 $/kW-yıl |
| RES sabit O&M | 35.000 $/MW/yıl | Lazard LCOE+ 2025: 24,5–40 $/kW-yıl |
| BESS O&M | CAPEX'in %2,5'i/yıl | Lazard LCOE+/LCOS 2025: 3–8 $/kWh-yıl |
| Arazi | GES 2.000, RES 1.500 $/MW/yıl | Tahmin (~1,6–2 ha/MWac GES; türbin parselleri) — sahaya göre geniş aralık |
| Sigorta | CAPEX'in %0,35'i/yıl | Sektör pratiği %0,3–0,5 |

### 3.3 Türkiye'ye özgü kalemler

| Kalem | Değer | Kaynak |
|---|---|---|
| TEİAŞ sistem kullanım (kapasite) | 3.470 $/MW-yıl | [EPDK 30/12/2025 – 14204 sayılı karar, 2026 iletim tarifeleri](https://www.teias.gov.tr/duyurular/2026-yili-sistem-kullanim-ve-sistem-isletim-tarifeleri): Çanakkale **2. bölge**, üretim 156.234,30 TL/MW-yıl |
| TEİAŞ kullanım + işletim (enerji) | 3,8 $/MWh | Aynı karar: 109,68 + 60,71 TL/MWh (~45 TL/USD) |
| Dengesizlik maliyeti | RES gelirin %4'ü, GES %2'si | [Algopoly RES maliyet raporu](https://algopoly.com/tr/res-maliyet-raporu-ekim-2024/): RES medyan birim maliyet 57 TL/MWh (Tem 2024) – 107 TL/MWh (Eki 2024) ≈ PTF'nin %2–5'i. Bazı kaynaklarda YEKDEM dışı portföylerde gelirin %19–26'sı gibi çok daha yüksek değerler var; tornado'da %8'e kadar test edildi |
| Kurumlar vergisi | %25 | [GİB 2026 oranlar](https://cdn.gib.gov.tr/api/gibportal-file/file/getFile?objectKey=DUYURU%2FUNIVERSAL%2F2026%2F2026_KurumlarVergisiOran.pdf); yatırım teşvik indirimleri dahil edilmedi (muhafazakâr) |
| Zarar mahsubu | 5 yıl | KVK md. 9 |
| Amortisman | 10 yıl doğrusal (GES, RES, BESS, şebeke) | [GİB amortisman listesi](https://cdn.gib.gov.tr/api/gibportal-file/file/getFileResources?objectKey=arsiv%2Fyardim-kaynaklar%2Fyararli-bilgiler%2FAmortismanOranlariTablosu.pdf): GES 45.1.9 ve RES 45.1.7 → 10 yıl, %10 |

### 3.4 Teknik

| Kalem | Değer | Kaynak |
|---|---|---|
| Proje ömrü / GES / RES | 30 / 30 / 30 yıl | IRENA, Lazard (25–35 yıl) |
| GES degradasyonu | %0,5/yıl | NREL (Jordan vd. 2016) medyan |
| RES performans düşüşü | %0,3/yıl | Staffell & Green (2014) eski İngiltere filosu %1,6; modern türbinlerde daha düşük |
| BESS | ömür 20 yıl, gidiş-dönüş verimi %87, yıpranma %2/yıl, augmentation 8. ve 16. yılda (ilk enerji CAPEX'inin %20'si × (1 − %3)^yıl) | Lazard/NREL ATB, sektör pratiği |
| Net söküm | GES 15.000 $/MW, RES 0 (hurda geliri söküm maliyetini karşılar), BESS 10.000 $/MWh | Sektör tahmini |
| Eşzamanlılık düzeltmesi | RES −0,048 yakalanma oranı | Aşama 2 (bkz. 4.3) |

### 3.5 Finansal

| Kalem | Değer | Gerekçe |
|---|---|---|
| **Reel WACC** | **%7,0** | Aşağıdan yukarı hesap (kalemler aşağıda), sonuç %6,8 → %7,0'a yuvarlandı |
| ABD enflasyonu | %2,5 | Yalnızca nominal borcun reele çevrilmesinde |
| Borç faizi | %8,0 nominal USD | SOFR ~%3,5–4 + Türkiye proje finansmanı marjı ~%4–4,5 (tahmin; [EBRD'nin Türkiye RES kredileri](https://www.aa.com.tr/en/energy/general/ebrd-backs-250-mw-wind-power-expansion-in-turkiye-with-200m-loan/53596) var ama koşulları kamuya açık değil) |
| Vade / hedef DSCR / azami borç oranı | 15 yıl / 1,30 / %75 | Merchant projelerde banka pratiği |

**WACC hesabının kalemleri:**
- **Reel risksiz faiz** ~%2,0 (ABD 10 yıllık TIPS).
- **Olgun piyasa hisse senedi risk primi** %4,23 (Damodaran, Ocak 2026).
- **Türkiye ülke risk primi** %4,66 ([Damodaran, Ocak 2026](https://pages.stern.nyu.edu/~adamodar/New_Home_Page/datafile/ctryprem.html)).
- **β = 1,0** (merchant proje).
- **Özkaynak maliyeti (reel)** = 2,0 + 1,0 × 4,23 + 4,66 ≈ **%10,9**.
- **Borç maliyeti (reel)** ≈ (1,08 / 1,025) − 1 ≈ %5,4; vergi sonrası ≈ **%4,1**.
- **Ağırlıklar:** %60 borç / %40 özkaynak → %6,8 → **%7,0**. Duyarlılık: %5,5–8,5.

## 4. Fiyat senaryoları (`src/finans/fiyat_senaryosu.py`)

### 4.1 Şekil ve seviye
- **Saatlik ŞEKİL** son dönemin PTF'sinden geliyor (USD, yıllık ortalamaya bölünmüş). İki "şekil yılı" var:
  - 2025 (Ocak–Aralık)
  - Son 12 ay: 2026 Ocak–Eylül + 2025 Ekim–Aralık, takvim sırasına dizilmiş
- **SEVİYE** = yıllık baz yük ortalaması, reel 2026 USD, proje ömrü boyunca sabit:

| Senaryo | USD/MWh | Gerekçe |
|---|---|---|
| Düşük | **45** | 2017–2021 ortalaması 46,8; son 12 ay (Ekim 2025 – Eylül 2026) 49,2. Bol hidroloji ve güneş fazlası kalıcı olursa |
| Baz | **58** | Son 12 ay (49) ile 2024–25 ortalaması (67) arasında |
| Yüksek | **72** | 2024–25 seviyesi + gaz/karbon baskısı. Gazın fiyatı belirlediği saatlerde marjinal maliyet: BOTAŞ elektrik üretim tarifesi 18 TL/Sm³ ([4 Nisan 2026](https://www.botas.gov.tr/Sayfa/4-nisan-2026-tarihinden-itibaren-gecerli-botas-dogal-gaz-toptan-satis-fiyat-tarifesi/812)) ≈ 11,5 $/MMBtu → kombine çevrim yakıt maliyeti ~75–80 $/MWh. Türkiye ETS'nin devreye girmesi yukarı yönlü risk |

### 4.2 Kanibalizasyon
- **Formül:** `p_y(t) = L × şekil(t) × [1 − d_y · g(t)] / ortalama(…)`
  - g(t) = Ezine GES üretim şekli (en büyüğü 1).
  - d_y her yıl, Ezine GES'in yakalanma oranı hedefe eşit olacak şekilde çözülür.
  - Payda yıllık ortalamayı L'de sabit tutar. Böylece **seviye ve şekil birbirinden bağımsız** değiştirilebilir.
- **Şekil dönemindeki Ezine GES yakalanma oranı: 0,769.**
- **"Durur":** Oran 0,769'da sabit kalır.
- **"Devam" (baz):** Oran 2033'e kadar doğrusal olarak **0,60**'a iner, sonra sabit kalır. Gerekçeler:
  - Aşama 2 Yol B trendi ~−0,04/yıl (Türkiye güneşi 2023 0,90 → 2025 0,83 → 2026 0,75).
  - Yüksek güneş paylı Avrupa pazarlarında (İspanya, Almanya) oranlar 0,6–0,7.
- **Sonuç:** Öğle çukuru derinleşiyor (`fiyat_senaryolari.png`, sağ panel). Ezine RES de öğleden sonra ürettiği için RES'in oranı da 1,009'dan 0,986'ya iniyor (eşzamanlılık düzeltmesi öncesi).

### 4.3 Hava yılları ve "rüzgâr–fiyat ilişkisinin kaybolması"
- **Kurgu:** Her işletme yılı, 10 hava yılı × 2 fiyat şekli yılının **tüm kombinasyonlarının ortalaması** ile değerlenir. Bu bir beklenen değer (P50).
- **Sorun:** Hava ve fiyat farklı yıllardan geldiği için gerçek eşzamanlılık kayboluyor. Türkiye geneli rüzgârlıyken fiyat düşer ve Ezine rüzgârı Türkiye rüzgârıyla birlikte eser.
- **Ölçüm:** Aşama 2'de 2021–2023'te "aynı yıl" ile "karışık yıl" eşleştirmesi karşılaştırıldı. Karıştırma RES yakalanma oranını **~0,048 fazla** gösteriyor (GES için fark ≈ 0, çünkü güneşin fiyat etkisi saatin kendisinde).
- **Çözüm:** Modelde RES'e düşen satılan enerjinin geliri, `Δ = 0,048 × yıllık ortalama fiyat` kadar azaltılıyor ("Eşzamanlılık düzeltmesi" satırı; konfigürasyon (b) için ömür boyu bugünkü değeri −4,7 M$).
- **Daha iyi yöntem (Aşama 5'e not):** Fiyatı Türkiye rüzgârına koşullu üreten bir model (ör. saatlik fiyat ~ ulusal rüzgâr + güneş regresyonu) kurmak.

### 4.4 Düzenleyici tavan (opsiyonel)
- **Örnek alınan dönem:** 2022–23 AUF. Yenilenebilir AUF / ortalama PTF oranı 2022'de ≈ 0,55, 2023'te ≈ 0,85 idi (Aşama 2).
- **Parametreler:** `duzenleyici_tavan` aktif edilirse belirtilen işletme yıllarında satış fiyatı `min(p, 0,70 × L)` olur. Varsayılan pasif; Aşama 5'te olasılıkla tetiklenecek.

## 5. Sonuçlar

### 5.1 Referans konfigürasyonlar — baz fiyat (58 $/MWh), kanibalizasyon devam

| | (a) RES 50 | (b) RES 50 + GES 25 | (c) RES 50 + GES 50 | (d) GES 50 |
|---|---|---|---|---|
| CAPEX [M$] | 63,5 | 79,0 | 94,5 | 37,0 |
| **NPV [M$]** | **−2,5** | −8,0 | −16,3 | −15,6 |
| **Proje IRR (reel, vergi sonrası)** | **6,5%** | 5,8% | 4,8% | 1,0% |
| Öz kaynak IRR reel / nominal | 7,6% / 10,3% | 6,2% / 8,9% | 4,8% / 7,4% | −0,2% / 2,3% |
| LCOE GES / RES [$/MWh] | — / 50,5 | 48,6 / 49,0 | 47,3 / 48,3 | 51,3 / — |
| LCOE satılan enerji [$/MWh] | 50,5 | 50,1 | 52,1 | 51,3 |
| Yakalanan fiyat (ömür ort.) [$/MWh] | 54,5 | 51,0 | 49,5 | 35,5 |
| — GES / RES yakalanan | — / 54,5 | 35,8 / 55,0 | 36,2 / 56,2 | 35,5 / — |
| Kesinti | 0% | 2,2% | 8,1% | 0% |
| Satılan enerji, yıl 1 [GWh] | 165 | 203 | 230 | 90 |
| P90 / P50 | 0,927 | 0,941 | 0,952 | 0,966 |
| **Borç kapasitesi P90 [M$] (borç/CAPEX)** | 37,9 (60%) | 44,9 (57%) | 49,8 (53%) | 13,3 (36%) |
| Borç kapasitesi P50 [M$] (borç/CAPEX) | 41,9 (66%) | 48,6 (61%) | 53,1 (56%) | 14,1 (38%) |

### 5.2 NPV [M$] — senaryolar (`konfigurasyon_senaryolar.csv` tüm metrikleri içerir)

| | Durur: düşük | Durur: baz | Durur: yüksek | **Devam: düşük** | **Devam: baz** | **Devam: yüksek** |
|---|---|---|---|---|---|---|
| (a) RES 50 | −18,7 | −1,0 | 16,2 | −19,9 | **−2,5** | 14,5 |
| (b) RES 50 + GES 25 | −25,0 | −3,8 | 17,1 | −28,3 | **−8,0** | 12,4 |
| (c) RES 50 + GES 50 | −34,2 | −10,4 | 13,8 | −39,1 | **−16,3** | 7,2 |
| (d) GES 50 | −17,2 | −9,1 | −0,7 | −22,6 | **−15,6** | −8,5 |

Proje IRR (reel), baz/devam → yüksek/devam: (a) 6,5% → 9,6%, (b) 5,8% → 8,8%, (c) 4,8% → 7,9%,
(d) 1,0% → 3,9%. Yüksek fiyatta (b) ve (c)'de borç %75 borç/CAPEX tavanına takılıyor.

**Yorum:**
- **Bataryasız hiçbir konfigürasyon baz senaryoda %7 reel getiriyi karşılamıyor.**
  - En iyisi yalnızca RES (a): IRR 6,5%, eşiğe çok yakın.
  - Öz kaynak IRR nominal USD'de %10,3. Bu, modeldeki reel özkaynak maliyetinin (%10,9 ≈ %13,6 nominal) altında; merchant bir RES baz fiyatta sınırda kalıyor.
  - Yüksek fiyat (72 $/MWh) senaryosunda RES ve hibritler pozitif NPV'ye dönüyor.
- **Bağımsız GES (d) her senaryoda negatif.** Kanibalizasyon devam ederse güneşin ömür boyu yakalanan fiyatı ortalama fiyatın yalnızca %61'i (35,5 / 58).
- **LCOE tek başına yetmiyor.** (b)'nin satılan enerji LCOE'si (a)'dan bile düşük (50,1 < 50,5): GES ucuz ve şebeke maliyeti paylaşılıyor. Ama ürettiği enerjinin piyasa değeri düşük. Yakalanan fiyat – LCOE grafiği bunu gösteriyor: (a) çizginin üstünde, (b) yaklaşık üstünde, (c) ve (d) altında. **"Ucuz enerji ≠ değerli enerji."**
- **Hibrit borç kapasitesini artırıyor.** RES + GES'te P90/P50 oranı daha yüksek (yıllar arası değişkenlik düşük) ve satılan enerji fazla; (b)'de borç kapasitesi (a)'dan 7 M$ yüksek. Bankalanabilirlik açısından GES'in katkısı var, ama değer açısından yok.

### 5.3 Duyarlılık — konfigürasyon (b), tornado (`tornado_b.png`)

| Değişken (olumsuz / olumlu) | NPV [M$] | Aralık |
|---|---|---|
| **Fiyat seviyesi (45 / 72 $/MWh)** | −28,3 / +12,4 | **40,7** |
| **CAPEX (+%20 / −%20)** | −21,9 / +5,4 | **27,4** |
| **WACC (%8,5 / %5,5)** | −15,5 / +1,9 | **17,4** |
| RES kapasite faktörü (−%10 / +%10) | −14,5 / −1,8 | 12,8 |
| Kanibalizasyon (taban 0,50 / durur) | −10,4 / −3,8 | 6,6 |
| Dengesizlik (RES %8, GES %4 / RES %2, GES %1) | −11,4 / −6,2 | 5,2 |

- **En etkili üç değişken:** Fiyat seviyesi, CAPEX ve WACC.
- **Ortak payda bunların hepsinin "piyasa" ya da "finansman" riski olması.** Tek başına tasarımla kontrol edilemiyorlar: fiyat PPA ile, CAPEX tedarik süreciyle, WACC DFI finansmanı veya YEKDEM/YEKA ile yönetilebilir.
- **Kanibalizasyonun etkisi neden küçük?** (b)'de GES payı küçük olduğu için etkisi görece sınırlı. Ama (c) ve (d)'de belirleyici: (d)'de durur ile devam arasındaki fark 6,5 M$.

### 5.4 Ek GES'in marjinal değeri (`marjinal_ges.png`)

RES 50 MW sabitken, 50 MW bağlantıya GES eklendikçe:

| Adım | Kanibalizasyon | ΔNPV / MW GES [M$/MW] | Eklenen GES enerjisinin kesilen payı | Bağımsız GES NPV / MW [M$/MW] |
|---|---|---|---|---|
| (a) → (b): 0 → 25 MW | durur | −0,11 | 14% | −0,18 |
| (b) → (c): 25 → 50 MW | durur | −0,26 | **40%** | −0,18 |
| (a) → (b) | devam | −0,22 | 14% | −0,31 |
| (b) → (c) | devam | −0,33 | **40%** | −0,31 |

**Yorum:**
1. **İlk 25 MW GES, bağımsız bir GES'ten daha iyi** (−0,22'ye karşı −0,31 M$/MW). Mevcut bağlantı ve TEİAŞ kapasite bedeli paylaşılıyor (~0,12 M$/MW CAPEX + yıllık 3.470 $/MW). Bu tasarruf, eklenen enerjinin %14'ünün kesilmesinin maliyetinden büyük.
2. **İkinci 25 MW, bağımsız bir GES'ten bile kötü** (−0,33). Eklenen enerjinin **%40'ı kesiliyor**, çünkü yaz öğleden sonraları rüzgâr (meltem) ve güneş aynı anda tepe yapıyor (Aşama 2 revizyonu).
3. **Kanibalizasyon her MW'ın değerini bir kat daha düşürüyor:** "durur"a göre −0,1 M$/MW.
4. **Bu yüzden Aşama 4'teki optimizasyon gerekli.** Doğru GES miktarı, batarya (kesilen enerjiyi akşama kaydırmak) ve belki şebeke bağlantısının boyutu birlikte seçilmeli. Bu eğri tek başına "GES ekleme" diyor. Ama batarya, kesilen ve öğle saatinde ucuzlayan enerjiyi 18–22 TSİ'deki pahalı saatlere taşıyabilirse bu sonuç tersine dönebilir (Aşama 2: akşam/öğle fiyat oranı 2025'te 1,6, 2026'da 2,3).

### 5.5 Nakit akışı köprüsü — konfigürasyon (b) (`nakit_akisi_selale_b.png`, `nakit_akisi_b.xlsx`)

Ömür boyu bugünkü değerler (M$, %7):

| Kalem | M$ |
|---|---|
| GES geliri | +16,4 |
| RES geliri (brüt) | +98,5 |
| Eşzamanlılık düzeltmesi | −4,7 |
| Dengesizlik | −4,1 |
| İşletme-bakım + arazi | −23,6 |
| Sigorta | −3,0 |
| TEİAŞ | −10,0 |
| Vergi | −6,4 |
| CAPEX | −70,9 |
| **NPV** | **−8,0** |

TEİAŞ bedelleri (10 M$) dengesizlikten de büyük. Türkiye'de üreticiye yansıyan iletim maliyeti
yatırım analizlerinde sık atlanıyor.

## 6. Doğrulama: LCOE'ler makul mü?

| | Modelimiz | IRENA 2025 küresel | IRENA 2025 aralığı (pazarlar) | Not |
|---|---|---|---|---|
| RES | 48–50 $/MWh | 33 | 27 (Çin) – 52 (Almanya) | Almanya'ya yakın |
| GES | 47–51 $/MWh | 44 | 35 (Hindistan) – 65 (Almanya) | Küresel ortalamanın biraz üstü |

**Neden IRENA küresel ortalamasının üstündeyiz?** Aynı modelle kapsamı değiştirerek ayrıştırdım:

| Hesap | RES | GES |
|---|---|---|
| Modelimiz, %7 reel WACC, tüm maliyetler | 50,5 | 51,3 |
| %7 WACC, TEİAŞ bedelleri + arazi + şebeke bağlantısı **hariç** | **41,9** | **38,3** |
| %5 WACC, tüm maliyetler | 44,1 | 44,5 |
| %5 WACC, TEİAŞ + arazi + şebeke hariç | 36,1 | 32,5 |

1. **Farkın büyük kısmı Türkiye'ye özgü maliyetlerden geliyor:** TEİAŞ iletim bedelleri, arazi ve şebeke bağlantısı. Bunlar çıkarılınca GES (38) küresel ortalamanın (44) altına, RES (42) ise küresel (33) ile Almanya (52) arasına düşüyor. TEİAŞ bedelleri tek başına ~4–5 $/MWh.
2. **IRENA'nın küresel RES ortalaması Çin ağırlıklı.** IRENA RES maliyeti 976 $/kW, bizim varsayımımız ~1.150 $/kW.
3. **WACC etkisi var ama belirleyici değil.** IRENA geçmişte OECD ve Çin için %5, diğer ülkeler için %7,5 **reel** WACC kullanıyordu; güncel raporlarda ülkeye özgü değerler var. Bizim %7 reel varsayımımız bu aralıkta.
4. **GES kapasite faktörü %20,6 (AC, kayıplar sonrası) orta düzey.** Ezine, Konya kadar güneşli değil.

**Sonuç:** Modelin teknoloji maliyetleri uluslararası kıyaslarla tutarlı; LCOE farkı açıklanabilir.

## 7. Sınırlamalar

1. **TEİAŞ kapasite tahsis bedeli (katkı payı) dahil değil.** Türkiye'de yeni bağlantı kapasitesi genellikle yarışmayla tahsis ediliyor ve katkı payı MW başına önemli bir tutar olabilir. Bu, (a)–(c)'nin NPV'sini düşürür ve şebeke bağlantısını paylaşmanın (hibrit) değerini artırır.
2. **Merchant varsayımı.** YEKDEM, YEKA veya PPA gibi gelir garantileri yok. Gerçek projelerde bunlar WACC'ı ve borç koşullarını iyileştirir (DSCR 1,20; daha uzun vade).
3. **Sabit reel fiyat seviyesi.** Fiyatın zaman içindeki trendi (talep artışı, gaz fiyatı, ETS) senaryo seviyeleriyle temsil ediliyor; yıllar içinde değişen bir yol yok.
4. **Kur geçişi** tam varsayıldı (bkz. bölüm 1).
5. **Eşzamanlılık düzeltmesi** tek bir ortalama farkla yapıldı. Yıllar ve konfigürasyonlar arasında değişebilir.
6. **Vergi amortismanı** reel USD bazında, enflasyon düzeltmesiyle korunduğu varsayıldı. Gerçekte TL bazlı ve düzeltme kuralları değişken.
7. **İnşaat dönemi faizi ve finansman masrafları** (taahhüt ücreti, DSRA) ihmal edildi. Öz kaynak IRR'ını biraz düşürür.
8. **Dengesizlik maliyeti** basit gelir oranı olarak alındı. Hibrit portföyde tahmin hatalarının kısmen birbirini götürmesi (portföy etkisi) dikkate alınmadı.
9. **Batarya geliri** Aşama 4'e kadar sıfır. Kanca hazır, maliyet tarafı tamam.
10. **Varsayımların bir kısmı tahmin:** arazi, söküm, borç marjı, RES degradasyonu. Kaynak bulunamayanlar config'te açıkça işaretli.

## 8. Çıktılar

| Dosya | İçerik |
|---|---|
| `konfigurasyon_karsilastirma.png` | NPV (3 fiyat × 2 kanibalizasyon) ve yakalanan fiyat – LCOE |
| `nakit_akisi_selale_b.png` | (b) için gelirden NPV'ye bugünkü değer köprüsü |
| `tornado_b.png` | (b) için tek değişkenli duyarlılık |
| `lcoe_karsilastirma.png` | Teknoloji ve satılan enerji LCOE'leri, IRENA referansları |
| `fiyat_senaryolari.png` | Seviye, kanibalizasyon varyantları, gün içi profil |
| `marjinal_ges.png` | GES 0–75 MW taraması ve MW başına marjinal NPV |
| `nakit_akisi_b.xlsx` | (b) için yıllık nakit akışı (Özet, Nakit akışı, Varsayımlar sayfaları) |
| `*.csv` | Tüm tablolar |

---

## Mülakat özeti

> Ezine için reel dolar bazında bir proje finansmanı modeli kurdum. Gelir tarafında 10 hava
> yılının saatlik üretimini, son dönemin saatlik fiyat şekliyle ve öğle saatlerindeki fiyat
> çukurunun derinleştiği bir kanibalizasyon senaryosuyla eşleştirdim. Maliyet tarafında IRENA,
> BNEF ve Lazard'ın güncel verilerini, Türkiye'ye özgü TEİAŞ iletim bedellerini, dengesizlik
> maliyetini ve vergiyi ekledim. Borcu P90 üretime göre 1,30 DSCR ile boyutlandırdım. Sonuç şu:
> 58 dolarlık baz fiyatta bataryasız hiçbir konfigürasyon %7 reel getiriyi aşamıyor. En iyisi
> yalnızca rüzgâr, %6,5 IRR ile eşiğe yakın. GES eklemek enerjiyi ucuzlatıyor ama değerini
> düşürüyor: ikinci 25 MW'ın üretiminin %40'ı kesiliyor ve güneş ömür boyunca ortalama fiyatın
> ancak %61'ini yakalıyor. Duyarlılıkta fiyat seviyesi, CAPEX ve WACC öne çıkıyor; yani projeyi
> asıl kurtaracak şeyler PPA ile fiyat güvencesi ve ucuz finansman. Bir sonraki adımda bataryayı
> ekleyip GES, RES ve batarya kapasitelerini birlikte optimize edeceğim; çünkü kesilen ve öğlen
> ucuzlayan enerjiyi akşamın pahalı saatlerine taşımak bu tabloyu değiştirebilir.
