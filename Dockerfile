FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    AI_DOCTOR_ENV=production \
    AI_DOCTOR_DATABASE=/data/ai_doctor_preclinical.db

WORKDIR /app
COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install --no-cache-dir .

RUN useradd --create-home --uid 10001 appuser \
    && mkdir -p /data \
    && chown -R appuser:appuser /data
USER appuser

EXPOSE 8080
CMD ["uvicorn", "ai_doctor.main:app", "--host", "0.0.0.0", "--port", "8080"]
