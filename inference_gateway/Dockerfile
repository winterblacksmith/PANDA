FROM python:3.13-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY inference_gateway/requirements.txt ./requirements.txt
RUN python -m pip install --no-cache-dir --upgrade pip \
    && python -m pip install --no-cache-dir -r requirements.txt \
    && useradd --create-home --uid 10001 panda

COPY --chown=panda:panda inference_gateway /app/inference_gateway
RUN chmod -R u=rwX,go=rX /app/inference_gateway
USER panda

EXPOSE 8000
CMD ["python", "-m", "uvicorn", "inference_gateway.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips", "*"]
