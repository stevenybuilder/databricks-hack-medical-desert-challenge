# Public Streamlit deploy of the CareGap app on Google Cloud Run.
# Runs fully standalone from the bundled cleaned CSVs (DATA_BACKEND=csv) — no
# Databricks credentials and no warehouse needed. Sensitive key/PII CSVs are
# excluded from the build context via .dockerignore / .gcloudignore.
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    DATA_BACKEND=csv \
    STREAMLIT_SERVER_HEADLESS=true \
    STREAMLIT_SERVER_ENABLE_CORS=false \
    STREAMLIT_SERVER_ENABLE_XSRF_PROTECTION=false \
    STREAMLIT_BROWSER_GATHER_USAGE_STATS=false

WORKDIR /srv

# Install deps first for layer caching.
COPY app/requirements.txt /srv/app/requirements.txt
RUN pip install -r /srv/app/requirements.txt

# App code + the (non-sensitive) cleaned data the app reads in csv mode.
COPY app/ /srv/app/
COPY .streamlit/ /srv/app/.streamlit/
COPY output/data/ /srv/output/data/

# Cloud Run injects $PORT (default 8080). Streamlit must bind it on 0.0.0.0.
ENV PORT=8080
EXPOSE 8080
WORKDIR /srv/app
CMD ["sh", "-c", "streamlit run app.py --server.port ${PORT} --server.address 0.0.0.0 --server.headless true"]
