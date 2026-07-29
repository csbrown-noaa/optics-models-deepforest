# NOAA NMFS Optics Model Deployment Template ("Hello World")

Welcome! This repository is a starting template for deploying your custom Computer Vision models into the Optics SI Airflow ecosystem. If you have an Ultralytics-family model or a VIAME-family model 🛑 **STOP!**, there are existing frameworks for that - please use those - it's easier that way. :)

Our infrastructure requires models to run inside isolated Docker containers, expose an HTTP endpoint, and communicate with Google Cloud Storage (GCS). We have pre-written most of this infrastructure for you, so you can just focus on importing your model and getting predictions into the expected shape.

---

# 🟢 Phase 1: Deploying the "Hello World" Baseline

Before writing any custom computer vision code, we are going to deploy this repository exactly as it is. It currently contains a "dummy" model that draws random bounding boxes. 

By deploying this dummy model first, you will verify that your local Docker setup, Google Cloud permissions, and Airflow configurations are working perfectly.

## 🏁 Step 1: Fork and Clone

Before changing any code, fork this repository and clone it to your local machine (or Google Cloud Workstation). All subsequent commands assume you are running them from the root of this cloned directory.

```bash
git clone https://github.com/csbrown-noaa/optics-models-hello-world.git
cd optics-models-hello-world
```

## 💻 Step 2: Test the Dummy Locally

Before deploying to the cloud, verify the dummy code works on your laptop/workstation.  We recommend using the Google Cloud workstations for this.  They already have `docker` and `gcloud` and other useful utilities installed.

**1. Authenticate with Google Cloud**
Ensure you have Google Cloud credentials available locally so the container can download the test files:
```bash
gcloud auth application-default login
```

**2. Build the Docker Container**

```bash
docker build -t optics-hello-world:latest .
```

**3. Run the Container**
*(This maps your local GCP credentials into the container so it can access buckets)*

For macOS/Linux (or Cloud Workstations):

```bash
docker run -p 8080:8080 \
  -v ~/.config/gcloud:/tmp/.config/gcloud \
  -e GOOGLE_APPLICATION_CREDENTIALS=/tmp/.config/gcloud/application_default_credentials.json \
  -e GOOGLE_CLOUD_PROJECT=ggn-nmfs-osi-dev-1 \
  optics-hello-world:latest
```

For Windows (using PowerShell):
```bash
docker run -p 8080:8080 -v ${env:APPDATA}\gcloud:/tmp/.config/gcloud -e GOOGLE_APPLICATION_CREDENTIALS=/tmp/.config/gcloud/application_default_credentials.json optics-hello-world:latest

docker run -p 8080:8080 `
  -v ${env:APPDATA}\gcloud:/tmp/.config/gcloud `
  -e GOOGLE_APPLICATION_CREDENTIALS=/tmp/.config/gcloud/application_default_credentials.json `
  -e GOOGLE_CLOUD_PROJECT=ggn-nmfs-osi-dev-1 `
  optics-hello-world:latest
```

**4. Prepare Your Test Payloads**
We have provided template JSON payloads in the local `test_payloads/` directory along with some sample media. 

First, open the JSON files locally on your machine. Replace all the `<TODO_YOUR_FOLDER>` placeholders with a unique folder name you control (e.g., your username).

Next, you must upload the local test images, the test video, and your newly modified `input_manifest.json` up to that exact Google Cloud Storage location (e.g., `gs://ggn-nmfs-osi-dev-1-data/scott/test-images/`). *Without this step, your local Docker container won't have anything to download during the test!*

**5. Send Test Requests**
In a new terminal (while your Docker container is still running), test the different data ingestion methods:

```bash
# Test 1: Single Video
curl -X POST http://localhost:8080/predict \
     -H "Content-Type: application/json" \
     -d @test_payloads/test_payload_video.json

# Test 2: Multiple Images
curl -X POST http://localhost:8080/predict \
     -H "Content-Type: application/json" \
     -d @test_payloads/test_payload_images.json

# Test 3: Using a Manifest
curl -X POST http://localhost:8080/predict \
     -H "Content-Type: application/json" \
     -d @test_payloads/test_payload_manifest.json
```

If successful, your terminal will log the processing steps, and new KWCOCO files will appear in your GCS bucket!

## ☁️ Step 3: Deploy to Cloud

Once you are happy with local testing, we will push this container to the Google Artifact Registry.

***!!!!NB!!!!*** The Artifact Registry is where everyone's models lives.  By pushing your docker image to the registry, there is a risk that you may overwrite existing docker images.  Please be careful here.

**1. Authenticate with Google Cloud**
Didn't we just do this??!!  Yes, but we used this to get application credentials for the docker image.  Since the docker image is doing work **on your behalf**, it needs its own set of credentials.  This login is so that you can interact directly with gcloud, which is what we're doing now.
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

You should see optics-hello-world in here.  By deploying the image you just built, you are going to "cover up" the old image.  The old image will still be there somewhere, buried in the history, but the `optics-hello-world:latest` image that you just built will be the new image that everyone has access to in the Optics SI.  This is fine - that's what this image is for.  However, it is important to note that in general, this deployment process **replaces** existing images in the repo.

Now that we've been thoroughly warned, let's move along.

```bash
# Tag your image for the registry
docker tag optics-hello-world:latest us-central1-docker.pkg.dev/ggn-nmfs-osi-dev-1/nmfs-dev-uc1-docker-repository/optics-hello-world:latest

# Push it
docker push us-central1-docker.pkg.dev/ggn-nmfs-osi-dev-1/nmfs-dev-uc1-docker-repository/optics-hello-world:latest
```

## ⚙️ Step 4: Hook it into Airflow

To make your model available in the system, you normally must register it in the Airflow DAG.

The DAGs are just python files stored in a bucket [here](https://console.cloud.google.com/storage/browser/us-central1-composer-env1-73848881-bucket/dags).  You can see the existing ones in there.  Open up [the optics batch processing DAG](https://storage.googleapis.com/us-central1-composer-env1-73848881-bucket/dags/scott_test_dag.py) to view the contents.

Locate the `MODEL_JOB_MAP` dictionary in the DAG file and see the entries for the various models. It's just a dictionary containing a hard-coded list of all of the available models and the relevant configuration for that model. See `ultralytics` as an example. Add yours to `MODEL_JOB_MAP`:

```python
    "optics-hello-world": {
        "region": REGION,
        "image": "us-central1-docker.pkg.dev/ggn-nmfs-osi-dev-1/nmfs-dev-uc1-docker-repository/optics-hello-world:latest",
        "cpu": 4,
        "memory": "16Gi",
        "gpu": 1,                   # Change to 0 if CPU only
        "gpu_type": "nvidia-l4",    # Set to None if CPU only
        "machine_type": "g2-standard-4", 
        "timeout": BATCH_JOB_TIMEOUT,
        "command": ["python"],
        "args": ["/workspace/inference_runner.py"] # <--- DO NOT CHANGE THIS
    }
```

Note the "image" field.  This is precisely the image that you just built and pushed into the registry!  That tells the DAG which image to delegate to when you select the "optics-hello-world" model in the dropdown.

Locate the `with DAG`, around line 640, to add your model name to the enum 

```python
 enum=[
          "ultralytics",
          "viame-gpu",
          "sefsc-class-fish",
          "optics-hello-world"  # <----- your model
     ]
```


## 🚀 Step 5: Triggering in Airflow

When you run a job in Google Cloud Batch, the container boots up on an isolated, headless Virtual Machine. It doesn't have a user interface to accept manual inputs or local curl commands.

Because of this, **Airflow requires your JSON trigger payload to be uploaded to GCS first**. Airflow will pass the GCS URI of your JSON file to the headless VM, which will then download it and start the processing loop you just tested.  So, go back to find your favorite test payload that you created in Step 2.4, we are going to upload that to GCS.

1. Upload your finalized JSON configuration to GCS (e.g., `gs://ggn-nmfs-osi-dev-1-data/my-folder/test_payload_images.json`).
2. Go to Google Cloud console, on search bar `Airflow`, select `Managed Airflow` ->  `composer-env1` -> `Open Airflow UI` tab
3. Locate the dag file that you added your model in Step 4. click **Trigger DAG w/ config**.
4. Set the `model_type` to `optics-hello-world`.
5. Set the `input_file` parameter to the GCS URI of your uploaded JSON payload.
6. Hit **Trigger** and monitor your job's progress in the logs!
7. To monitor the DAG progress, select `Managed Airflow` ->  `composer-env1` -> `DAGs`. Click you DAG file, see the list All DAG runs.
8. To view the detailed log statements in your model, go to Google Cloud console, search `Batch`. When the job is actually scheduled to run, your job will appear on the Job list, select the job, click Logs tab

---

# 🔬 Phase 2: Bring Your Own Model (BYOM)

Congratulations! You have successfully executed a full end-to-end pipeline. Now it is time to replace the "dummy" code with your actual science.

You will likely need to edit only the `model.py`, which is where your prediction code lives, and the `Dockerfile`, which handles the dependencies of your code and the other base dependencies of the project. The rest of the files (`app.py`, `inference_runner.py`) are abstract plumbing that handle the annoying parts: downloading videos from the cloud, starting web servers, managing memory, and uploading your final results back to the cloud.


## 🧠 Step 6: Write Your Logic

Open `model.py`. You will see the "Hello World" logic that assigns random bounding boxes. 

Replace this logic with your actual framework. 
*   Read the input images/videos from the provided `input_dir`.
*   Load custom weights or thresholds from the `config` dictionary.
*   Run your specific computer vision framework.
*   Save your output to the `output_file_path` in an appropriate serialization format.  We recommend using the [KWCOCO (Kitware COCO)](https://kwcoco.readthedocs.io/en/latest/) JSON specification, as shown in the example code.  KWCOCO supports both images and video, and supports a wide range of annotation types such as classification, detection, and segmentation.  If we all stick to KWCOCO, then we can build interoperable pipelines that we only have to write once, and can share between groups.

## 📦 Step 7: Update Dependencies

If your model requires specific libraries (like `torch`, `tensorflow`, or `ultralytics`), you must add them to the `requirements.txt` file. We have already included OpenCV (`opencv-python-headless`) for you.

If you need heavy system-level packages (like custom NVIDIA drivers or specific `apt-get` binaries), you can add those to the `Dockerfile`.

## 🔄 Step 8: Re-build and Re-deploy

Now that your custom code is in place, simply repeat Phase 1!
1. Test it locally using `curl` (Step 2).
2. Pick a different name for your docker image (not optics-hello-world).  Feel free to continue using optics-hello-world to test on.  Try not to clutter up the artifact registry with a bunch of `test_pipeline-model_v8` sort of thing.  We all have to share this space.
3. Build and push a new version to the Artifact Registry (Step 3). Note: **Increment your version tag** (e.g., `v1.1`) so you don't overwrite your previous work!  We recommend pushing your latest image with the :latest tag that always points to the latest model.  This makes it so that you don't have to repeatedly update the DAG.
4. Update the Airflow DAG `MODEL_JOB_MAP` to point to your `:latest` image (Step 3).
5. Trigger the DAG!
