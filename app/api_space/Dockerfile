FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV SYNTHGUARD_MODEL_DIR=/app/models/synthguard_kmer

RUN useradd -m -u 1000 user
USER user
ENV PATH="/home/user/.local/bin:$PATH"

WORKDIR /app

COPY --chown=user requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY --chown=user . /app

# Download k-mer models from HF Hub at build time
RUN python -c "from huggingface_hub import snapshot_download; snapshot_download('Seyomi/synthguard-kmer', repo_type='model', local_dir='models/synthguard_kmer')"

EXPOSE 7860

CMD ["uvicorn", "api:app", "--host", "0.0.0.0", "--port", "7860"]
