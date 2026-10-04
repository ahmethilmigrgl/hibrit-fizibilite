"""
Aşama 0 — Kurulum testi / ısınma optimizasyon modeli (LP)

Soru: 50 MW şebeke bağlantısı, 45 milyon $ bütçe ve en fazla 40 MW GES kurulabilecek
arazi varken, yıllık geliri en yüksek yapan GES ve RES kapasitesi nedir?

Not: Bu bir ısınma örneğidir; veriler bilerek kod içindedir. Gerçek modellerde
tüm varsayımlar config.yaml'dan okunacak.

Matematiksel formülasyon ve yorum: docs/00_isinma_modeli.md
Çalıştırma: .venv/bin/python src/00_kurulum_testi.py
"""

import pyomo.environ as pyo

# ---------------------------------------------------------------------------
# 1) KÜMELER
# ---------------------------------------------------------------------------
# Teknolojiler kümesi T = {GES, RES}. Modeli küme üzerinden yazmak, ileride
# BESS gibi yeni teknoloji eklemeyi tek satırlık bir iş haline getirir.
TEKNOLOJILER = ["GES", "RES"]

# ---------------------------------------------------------------------------
# 2) PARAMETRELER (modelin girdisi olan sabit sayılar)
# ---------------------------------------------------------------------------
capex = {"GES": 0.6, "RES": 1.2}  # yatırım maliyeti [milyon $/MW]
gelir = {"GES": 0.096, "RES": 0.180}  # yıllık gelir [milyon $/MW/yıl]
SEBEKE_KAPASITESI = 50.0  # şebeke bağlantı limiti [MW]
BUTCE = 45.0  # toplam yatırım bütçesi [milyon $]
GES_ARAZI_LIMITI = 40.0  # arazinin izin verdiği en fazla GES [MW]

model = pyo.ConcreteModel(name="Isinma_GES_RES")
model.T = pyo.Set(initialize=TEKNOLOJILER, doc="Teknolojiler")
model.capex = pyo.Param(model.T, initialize=capex, doc="CAPEX [milyon $/MW]")
model.gelir = pyo.Param(model.T, initialize=gelir, doc="Yıllık gelir [milyon $/MW]")

# ---------------------------------------------------------------------------
# 3) KARAR DEĞİŞKENLERİ (çözücünün bizim için seçeceği sayılar)
# ---------------------------------------------------------------------------
# x[t]: t teknolojisinden kurulacak kapasite [MW]. Negatif olamaz.
# Sürekli (kesirli) değişken → bu bir LP (doğrusal programlama) modelidir.
model.x = pyo.Var(model.T, domain=pyo.NonNegativeReals, doc="Kurulu kapasite [MW]")

# ---------------------------------------------------------------------------
# 4) AMAÇ FONKSİYONU
# ---------------------------------------------------------------------------
# Toplam yıllık geliri maksimize et:  max  Σ_t gelir[t] * x[t]
model.amac = pyo.Objective(
    expr=sum(model.gelir[t] * model.x[t] for t in model.T),
    sense=pyo.maximize,
)

# ---------------------------------------------------------------------------
# 5) KISITLAR
# ---------------------------------------------------------------------------
# (K1) Şebeke: toplam kurulu güç bağlantı kapasitesini aşamaz.
model.k_sebeke = pyo.Constraint(expr=sum(model.x[t] for t in model.T) <= SEBEKE_KAPASITESI)

# (K2) Bütçe: toplam yatırım bütçeyi aşamaz.
model.k_butce = pyo.Constraint(expr=sum(model.capex[t] * model.x[t] for t in model.T) <= BUTCE)

# (K3) Arazi: GES kapasitesi arazinin izin verdiği değeri aşamaz.
model.k_arazi = pyo.Constraint(expr=model.x["GES"] <= GES_ARAZI_LIMITI)

# ---------------------------------------------------------------------------
# 6) ÇÖZÜM VE RAPOR
# ---------------------------------------------------------------------------
# Dual (gölge fiyat) değerlerini almak için bir "suffix" tanımlıyoruz.
model.dual = pyo.Suffix(direction=pyo.Suffix.IMPORT)

cozucu = pyo.SolverFactory("appsi_highs")
sonuc = cozucu.solve(model)

durum = sonuc.solver.termination_condition
print(f"Çözücü durumu: {durum}")
if durum != pyo.TerminationCondition.optimal:
    raise SystemExit("Optimal çözüm bulunamadı!")

print("\n=== Optimal kapasiteler ===")
for t in model.T:
    print(f"  {t}: {pyo.value(model.x[t]):6.2f} MW")
print(f"  Toplam yıllık gelir: {pyo.value(model.amac):.2f} milyon $")

print("\n=== Kısıtların durumu ===")
print(f"  {'Kısıt':<10}{'Kullanım':>10}{'Limit':>8}{'Boşluk':>9}{'Gölge fiyat':>14}  Bağlayıcı?")
for ad, kisit in [("Şebeke", model.k_sebeke), ("Bütçe", model.k_butce), ("Arazi", model.k_arazi)]:
    kullanim = pyo.value(kisit.body)
    limit = pyo.value(kisit.upper)  # .upper bir Pyomo ifadesi döner; sayıya çeviriyoruz
    bosluk = limit - kullanim
    golge = model.dual.get(kisit, float("nan"))
    baglayici = "EVET" if abs(bosluk) < 1e-6 else "hayır"
    print(f"  {ad:<10}{kullanim:>10.2f}{limit:>8.1f}{bosluk:>9.2f}{golge:>14.4f}  {baglayici}")

print("\nGölge fiyat: ilgili limit 1 birim artarsa yıllık gelirin kaç milyon $ artacağı.")
print("  Şebeke → milyon $/MW,  Bütçe → $ başına $ getiri,  Arazi → milyon $/MW")
