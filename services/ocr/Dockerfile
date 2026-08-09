# GPU build: needs an NVIDIA driver supporting CUDA 12.6 and the
# nvidia-container-toolkit on the host.
FROM nvidia/cuda:12.6.3-cudnn-runtime-ubuntu22.04

ENV DEBIAN_FRONTEND=noninteractive \
    PIP_NO_CACHE_DIR=1 \
    PYTHONUNBUFFERED=1

RUN apt-get update && apt-get install -y --no-install-recommends \
        python3 \
        python3-pip \
        python3-venv \
        libgl1 \
        libglib2.0-0 \
        libgomp1 \
        curl \
    && rm -rf /var/lib/apt/lists/*

RUN python3 -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
RUN pip install --no-cache-dir --upgrade pip setuptools wheel

# The CUDA 12.6 build of PaddlePaddle lives in PaddlePaddle's own index. The
# wheel is close to 2 GB, so give the download room to retry.
RUN pip install --no-cache-dir --retries 10 --timeout 120 paddlepaddle-gpu==3.2.0 \
        -i https://www.paddlepaddle.org.cn/packages/stable/cu126/

COPY requirements.txt /srv/requirements.txt
RUN pip install --no-cache-dir -r /srv/requirements.txt

COPY app.py /srv/app.py
WORKDIR /srv

# Model weights are downloaded on first use into $HOME/.paddlex, which the
# compose file backs with a named volume so they survive container restarts.
ENV HOME=/models

EXPOSE 8001
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8001"]
