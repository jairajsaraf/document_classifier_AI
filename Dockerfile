# One image for eval, tests and deploy (PLAN Phase 1, call 4; Phase 5 adds the UI build stage).

# Stage 1: build the static export (`frontend/out`). Node 24: react-pdf 11 needs 22.13 or newer
# (docs/UI_BUILD.md). `next/font/google` downloads Geist here, so this stage needs network access.
FROM node:24-slim AS ui
WORKDIR /ui
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# Stage 2: the API, which also serves the export at /.
# Needs OS packages the Python deps shell out to: tesseract (pytesseract),
# poppler (pdf2image), libmagic (python-magic).
FROM python:3.12-slim

RUN apt-get update \
 && apt-get install -y --no-install-recommends tesseract-ocr poppler-utils libmagic1 \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY backend/requirements.txt backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt

COPY . .
COPY --from=ui /ui/out frontend/out
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1

# Render sets PORT (default 10000, https://render.com/docs/web-services); 8000 elsewhere.
# The eval overrides the command.
CMD ["sh", "-c", "exec uvicorn backend.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
