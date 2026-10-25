# Hugging Face Space (Docker SDK): Eşik — Türkiye hibrit saha analizi
FROM python:3.11-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 \
    VERI_ERISIM=uzak MOTOR_CEKIRDEK=2 OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MPLBACKEND=Agg
RUN useradd -m -u 1000 user
WORKDIR /app
COPY --chown=user requirements-app.txt .
RUN pip install --no-cache-dir -r requirements-app.txt
COPY --chown=user . .
RUN mkdir -p data/onbellek data/raw data/processed && chown -R user:user /app
USER user
EXPOSE 7860
CMD ["streamlit", "run", "app.py", "--server.port=7860", "--server.address=0.0.0.0", "--server.headless=true", \
     "--server.enableXsrfProtection=false", "--server.enableCORS=false", "--browser.gatherUsageStats=false"]
