# ── Stage 1: Builder ──
FROM python:3.11-slim AS builder

WORKDIR /app

# Install build dependencies for compiling any native extensions and system libraries for pre-downloading models
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libgl1 \
    libglib2.0-0 \
    libgomp1 \
    libxcb1 \
    && rm -rf /var/lib/apt/lists/*

# Create virtual environment to isolate runtime dependencies
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

COPY requirements.txt .

# 1. Install CPU-only PyTorch (~200MB) instead of default CUDA PyTorch (~2-4.5GB)
# 2. Install application dependencies from requirements.txt
RUN pip install --no-cache-dir \
    torch torchvision --index-url https://download.pytorch.org/whl/cpu \
 && pip install --no-cache-dir -r requirements.txt

COPY . .

# Pre-download RapidOCR & IBM Docling models during build stage
RUN python -c "from rapidocr import RapidOCR; RapidOCR(); from src.extractor import get_docling_converter; get_docling_converter()"

# ── Stage 2: Minimal Runtime ──
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    STREAMLIT_SERVER_PORT=8501 \
    STREAMLIT_SERVER_ADDRESS=0.0.0.0 \
    NNPACK_DISABLE=1 \
    GLOG_minloglevel=2 \
    TORCH_CPP_LOG_LEVEL=ERROR \
    OMP_NUM_THREADS=4 \
    MKL_NUM_THREADS=4 \
    OPENBLAS_NUM_THREADS=4

WORKDIR /app

# Install only essential runtime system libraries (no build-essential compiler)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    libgl1 \
    libglib2.0-0 \
    libgomp1 \
    libxcb1 \
    && rm -rf /var/lib/apt/lists/*

# Copy virtual environment and pre-downloaded model cache from builder
COPY --from=builder /opt/venv /opt/venv
COPY --from=builder /root/.cache /root/.cache
ENV PATH="/opt/venv/bin:$PATH"

# Copy application source code
COPY . .

EXPOSE 8501

HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
  CMD curl -f http://localhost:8501/_stcore/health || exit 1

CMD ["streamlit", "run", "app.py"]
