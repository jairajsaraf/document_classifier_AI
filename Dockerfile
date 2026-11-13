# One image for eval, tests and deploy (PLAN Phase 1, call 4).
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
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1

# Not exercised in Phase 1 (eval overrides the command); revisit at deploy.
CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
