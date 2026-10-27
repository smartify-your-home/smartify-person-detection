# Stage 1: YOLO11n nach ONNX exportieren
FROM python:3.12-slim-bookworm AS export
ENV PIP_NO_CACHE_DIR=1
RUN apt-get update && apt-get install -y --no-install-recommends libgl1 libglib2.0-0 \
 && rm -rf /var/lib/apt/lists/*
RUN pip install --index-url https://download.pytorch.org/whl/cpu torch torchvision \
 && pip install "ultralytics>=8.3,<9" onnx onnxslim
WORKDIR /export
RUN yolo export model=yolo11n.pt format=onnx imgsz=640 opset=12 simplify=True

# Stage 2: schlankes Laufzeit-Image
FROM python:3.12-slim-bookworm
ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
RUN apt-get update && apt-get install -y --no-install-recommends libglib2.0-0 ca-certificates \
 && rm -rf /var/lib/apt/lists/*
RUN pip install onnxruntime "numpy<3" opencv-python-headless "paho-mqtt>=2.1,<3"
WORKDIR /app
COPY --from=export /export/yolo11n.onnx /app/yolo11n.onnx
COPY run.sh /run.sh
RUN chmod +x /run.sh
COPY rtsp_source.py /app/rtsp_source.py
COPY app.py /app/app.py
COPY slideshow_persondetection.html /app/slideshow_persondetection.html
LABEL io.hass.version="1.6.7" io.hass.type="addon" io.hass.arch="amd64"
CMD ["/run.sh"]
