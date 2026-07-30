# NOAA NMFS Optics Model Deployment: DeepForest Marine Biodiversity

Welcome! This repository contains the deployment code for the **DeepForest Marine Biodiversity** computer vision model (originally developed via BOEM). This repository packages the model into an isolated Docker container that exposes an HTTP endpoint, communicates with Google Cloud Storage (GCS), and formats predictions into KWCOCO JSON for the Optics SI Airflow ecosystem.

The weights are automatically pulled from the `weecology/deepforest-marine-biodiversity` HuggingFace repository during the Docker build process to ensure zero "cold start" latency in production.

---

# 🟢 Deploying the DeepForest Model

By deploying this model from your local machine (or cloud workstation) first, you will verify that your local Docker setup, Google Cloud permissions, and Airflow configurations are working perfectly before unleashing it on the cloud.

## 🏁 Step 1: Clone the Repository

Clone this repository to your local machine (or Google Cloud Workstation). All subsequent commands assume you are running them from the root of this cloned directory.

```bash
git clone <URL_TO_THIS_REPO>
cd <REPO_DIRECTORY>
```

## 💻 Step 2: Test the Model Locally

Before deploying to the cloud, verify the model works on your laptop/workstation. We recommend using the Google Cloud workstations for this, as they already have `docker`, `gcloud`, and other utilities installed.

**1. Authenticate with Google Cloud**
Ensure you have Google Cloud credentials available locally so the container can download the test files:
```bash
gcloud auth application-default login
```

**2. Build the Docker Container**
*Note: This step may take a few minutes! The Dockerfile will download the PyTorch weights from HuggingFace so they are permanently baked into the image.*
```bash
docker build -t optics-deepforest:latest .
```

**3. Run the Container**
*(This maps your local GCP credentials into the container so it can access buckets)*
```bash
docker run -p 8080:8080 \
  -v ~/.config/gcloud:/tmp/.config/gcloud \
  -e GOOGLE_APPLICATION_CREDENTIALS=/tmp/.config/gcloud/application_default_credentials.json \
  optics-deepforest:latest
```

**4. Prepare Your Test Payloads**
We have provided template JSON payloads in the local `test_payloads/` directory along with some sample media. 

First, open the JSON files locally on your machine. Replace all the `<TODO_YOUR_FOLDER>` placeholders with a unique folder name you control (e.g., your username).

Next, you must upload the local test images and your newly modified `input_manifest.json` up to that exact Google Cloud Storage location (e.g., `gs://ggn-nmfs-osi-dev-1-data/scott/test-images/`). *Without this step, your local Docker container won't have anything to download during the test!*

**5. Send Test Requests**
In a new terminal (while your Docker container is still running), test the data ingestion methods:

```bash
# Test 1: Multiple Images
curl -X POST http://localhost:8080/predict \
     -H "Content-Type: application/json" \
     -d @test_payloads/test_payload_images.json

# Test 2: Using a Manifest
curl -X POST http://localhost:8080/predict \
     -H "Content-Type: application/json" \
     -d @test_payloads/test_payload_manifest.json
```

If successful, your terminal will log the processing steps, and new KWCOCO files containing your DeepForest predictions will appear in your GCS bucket!

## ☁️ Step 3: Deploy to Cloud

Once you are happy with local testing, we will push this container to the Google Artifact Registry.

***!!!!NB!!!!*** The Artifact Registry is where everyone's models live. By pushing your docker image to the registry, there is a risk that you may overwrite existing docker images. Please be careful here.

**1. Authenticate with Google Cloud**
This login is so that you can interact directly with gcloud to push to the registry.
```bash
gcloud auth login
```

Let's list the existing images in the registry first:

```bash
gcloud artifacts packages list \
  --project=ggn-nmfs-osi-dev-1 \
  --location=us-central1 \
  --repository=nmfs-dev-uc1-docker-repository
```

You should see `optics-deepforest` in here (if it has been deployed before). By deploying the image you just built, you are going to "cover up" the old image. This deployment process **replaces** existing tags in the repo.

```bash
# Tag your image for the registry
docker tag optics-deepforest:latest us-central1-docker.pkg.dev/ggn-nmfs-osi-dev-1/nmfs-dev-uc1-docker-repository/optics-deepforest:latest

# Push it
docker push us-central1-docker.pkg.dev/ggn-nmfs-osi-dev-1/nmfs-dev-uc1-docker-repository/optics-deepforest:latest
```

## ⚙️ Step 4: Hook it into Airflow

To make your model available in the system, you must register it in the Airflow DAG. 

The DAGs are just python files stored in a bucket [here](https://console.cloud.google.com/storage/browser/us-central1-composer-env1-73848881-bucket/dags). Open up the optics batch processing DAG to view the contents.

Locate the `MODEL_JOB_MAP` dictionary in the DAG file and ensure there is an entry for the DeepForest model. It should look something like this:

```python
    "optics-deepforest": {
        "region": "us-central1",
        "image": "us-central1-docker.pkg.dev/ggn-nmfs-osi-dev-1/nmfs-dev-uc1-docker-repository/optics-deepforest:latest",
        "cpu": 4,
        "memory": "16Gi",
        "gpu": 1,                   # DeepForest benefits heavily from a GPU
        "gpu_type": "nvidia-l4",    
        "machine_type": "g2-standard-4", 
        "timeout": 360000,
        "command": ["python"],
        "args": ["/workspace/inference_runner.py"] # <--- DO NOT CHANGE THIS
    }
```

Note the "image" field. This is precisely the image that you just built and pushed into the registry! 

## 🚀 Step 5: Triggering in Airflow

When you run a job in Google Cloud Batch, the container boots up on an isolated, headless Virtual Machine.

Because of this, **Airflow requires your JSON trigger payload to be uploaded to GCS first**. Airflow will pass the GCS URI of your JSON file to the headless VM, which will then download it and start the processing loop you just tested. 

1. Upload your finalized JSON configuration to GCS (e.g., `gs://ggn-nmfs-osi-dev-1-data/my-folder/trigger_payload.json`).
2. Go to the Airflow UI and click **Trigger DAG w/ config**.
3. Set the `model_type` to `optics-deepforest`.
4. Set the `input_file` parameter to the GCS URI of your uploaded JSON payload.
5. Hit **Trigger** and monitor your job's progress in the logs!
