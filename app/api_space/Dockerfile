FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV SYNTHGUARD_MODEL_DIR=/app/models/synthguard_kmer

RUN apt-get update && apt-get install -y libgomp1 && rm -rf /var/lib/apt/lists/*

RUN useradd -m -u 1000 user
USER user
ENV PATH="/home/user/.local/bin:$PATH"

WORKDIR /app

COPY --chown=user requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY --chown=user . /app

EXPOSE 7860

# Download latest models at startup so Space always uses the current HF version
CMD ["sh", "-c", "python -c \"from huggingface_hub import snapshot_download; snapshot_download('Seyomi/synthguard-kmer', repo_type='model', local_dir='models/synthguard_kmer')\" && uvicorn api:app --host 0.0.0.0 --port 7860"]
