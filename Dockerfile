FROM node:22-slim AS web
WORKDIR /app/web
COPY web/package*.json ./
RUN npm install --no-audit --no-fund
COPY web/ ./
RUN npm run build

FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY agrisat_core/ agrisat_core/
COPY api/ api/
COPY data/ data/
COPY --from=web /app/web/dist web/dist
RUN [ -f data/processed/meta.json ] || python -m agrisat_core.pipeline
EXPOSE 8000
CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
