# syntax=docker/dockerfile:1.7
#
# Netra Translate: web app + REST API with every model weight baked in (runs offline).
#
#   docker build -f docker/Dockerfile -t netra-translate .
#   docker run -p 8000:8000 netra-translate
#   then open http://localhost:8000
#
# CPU only, like the Netra OCR image: the OCR recognizer, the YOLO detectors and the
# NMT model are small enough for an ordinary CPU, and leaving out CUDA keeps the image
# several gigabytes smaller.

ARG PYTHON_VERSION=3.12

# ── base: system libraries shared by the build and runtime stages ────────────
# No libgl1: only the headless OpenCV build is installed (see the prune step).
FROM python:${PYTHON_VERSION}-slim AS base
RUN apt-get update && apt-get install -y --no-install-recommends libglib2.0-0 && \
    rm -rf /var/lib/apt/lists/*

# ── build: virtualenv with CPU torch + netra-translate[all], pruned ─────────
FROM base AS build
# git: netra-nmt is installed from GitHub (PyPI's 0.1.0 does not match the weights).
RUN apt-get update && apt-get install -y --no-install-recommends git && \
    rm -rf /var/lib/apt/lists/*
ENV PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1
RUN python -m venv /opt/venv
ENV PATH=/opt/venv/bin:$PATH

# CPU torch first, so nothing later pulls the CUDA build from PyPI.
RUN pip install --index-url https://download.pytorch.org/whl/cpu "torch==2.14.*" "torchvision==0.29.*"

WORKDIR /src
COPY pyproject.toml README.md LICENSE ./
COPY src ./src
RUN pip install ".[all]"

# Prune what inference never imports (checked by docker/smoke_test.py below), as in
# the Netra OCR image:
# - opencv-python (GUI build, needs libgl1) -> the same version, headless;
# - training/analysis-only deps of ultralytics / doclayout-yolo / netra-ocr:
#   polars, seaborn, albumentations, transformers, tokenizers;
# - torch's C++ headers, test libraries and protoc; bundled test suites; pip.
# Unlike the Netra OCR image, safetensors and sentencepiece stay: Netra-NMT loads
# model.safetensors and tokenizes with SentencePiece.
# matplotlib and pandas stay: doclayout-yolo imports them at startup.
RUN SP=$(python -c "import sysconfig; print(sysconfig.get_paths()['purelib'])") && \
    OCV=$(pip show opencv-python | awk '/^Version/{print $2}') && \
    pip uninstall -y opencv-python opencv-python-headless \
        polars polars-runtime-32 seaborn albumentations albucore \
        transformers tokenizers && \
    pip install --no-deps "opencv-python-headless==${OCV}" && \
    rm -rf "$SP"/torch/include "$SP"/torch/bin/protoc* "$SP"/torch/bin/test_* \
           "$SP"/torch/lib/libjitbackend_test.so "$SP"/torch/lib/libtorchbind_test.so \
           "$SP"/torch/lib/libbackend_with_compiler.so "$SP"/torch/lib/libaoti_custom_ops.so && \
    find "$SP" -depth -type d \( -name tests -o -name testing_data \) -path "*/scipy/*" -exec rm -rf {} + && \
    find "$SP" -depth -type d -name tests -path "*/pandas/*" -exec rm -rf {} + && \
    find /opt/venv -depth -name __pycache__ -type d -exec rm -rf {} + && \
    pip uninstall -y pip

# ── weights: everything the app loads, fetched once at build time ────────────
# Then run the whole pipeline once against the pruned environment: a prune that
# removed something needed fails here, not on the first upload.
FROM build AS weights
ENV HF_HOME=/models YOLO_CONFIG_DIR=/tmp/ultralytics MPLCONFIGDIR=/tmp/matplotlib
COPY docker/fetch_weights.py docker/smoke_test.py /tmp/
RUN python /tmp/fetch_weights.py && rm -rf /models/xet /models/hub/.locks && \
    cd /tmp && HF_HUB_OFFLINE=1 python /tmp/smoke_test.py && \
    chmod -R a+rX /models

# ── runtime ──────────────────────────────────────────────────────────────────
FROM base AS runtime
LABEL org.opencontainers.image.title="Netra Translate" \
      org.opencontainers.image.description="Khmer <-> English document translation: OCR, layout, machine translation, DOCX/HTML/Markdown export" \
      org.opencontainers.image.source="https://github.com/netra-ai-lab/netra-translate" \
      org.opencontainers.image.licenses="MIT AND AGPL-3.0-only"

RUN useradd --create-home --uid 10001 netra && \
    mkdir -p /data && chmod 1777 /data
COPY --from=build /opt/venv /opt/venv
COPY --from=weights /models /models

# Config/cache dirs live in /tmp and jobs in a world-writable /data, so the image
# also runs under another uid (Hugging Face Spaces runs containers as uid 1000).
ENV PATH=/opt/venv/bin:$PATH \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    HF_HOME=/models \
    HF_HUB_OFFLINE=1 \
    NETRA_HOST=0.0.0.0 \
    NETRA_PORT=8000 \
    NETRA_DEVICE=cpu \
    NETRA_DATA_DIR=/data \
    YOLO_CONFIG_DIR=/tmp/ultralytics \
    YOLO_OFFLINE=1 \
    MPLCONFIGDIR=/tmp/matplotlib

USER netra
# Jobs (uploads are deleted after OCR; page images, documents, translations).
# Mount a volume to keep them across container restarts.
VOLUME /data
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=60s --retries=3 \
    CMD python -c "import urllib.request,os; urllib.request.urlopen('http://127.0.0.1:%s/health' % os.environ.get('NETRA_PORT','8000'), timeout=4)"
CMD ["netra-translate", "serve"]
