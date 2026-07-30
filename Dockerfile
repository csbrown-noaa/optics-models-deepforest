FROM python:3.10-slim

WORKDIR /workspace

# Install system dependencies (ffmpeg and libsm6 are heavily required by OpenCV and CV libs)
# We also add libglib2.0-0 which is commonly required by DeepForest/Albumentations
RUN apt-get update && \
    apt-get install -y ffmpeg libsm6 libxext6 libglib2.0-0 && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Install Python requirements
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Download HuggingFace weights at build time to prevent API cold-starts
RUN huggingface-cli download weecology/deepforest-marine-biodiversity --local-dir /workspace/weights

# Copy application files
COPY app.py .
COPY inference_runner.py .
COPY model.py .

ENV HOME=/workspace

# Setup directories and permissions for the non-root execution required by GCP
RUN chown -R 8080:8080 /workspace && \
    chmod -R 777 /tmp && \
    chmod -R 777 /workspace/weights

# Switch to the required non-root user
USER 8080
EXPOSE 8080

# Default command starts the HTTP server
CMD ["python", "app.py"]
