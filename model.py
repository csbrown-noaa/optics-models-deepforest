"""
model.py - The Biologist's Sandbox

Welcome! If you are integrating a new model into the NOAA/NMFS ecosystem, 
THIS IS THE ONLY PYTHON FILE YOU NEED TO EDIT.

The surrounding infrastructure (app.py, inference_runner.py) handles downloading 
files from Google Cloud Storage (GCS), setting up the web server, and uploading 
the final results back to GCS. 

Your goal:
1. Read the input images/videos from `input_dir`.
2. Load any custom weights or configurations from `config`.
3. Run your specific computer vision framework.
4. Save your output to `output_file_path` (we highly encourage KWCOCO format).
"""

import os
import json
import glob
import cv2
import torch
import pandas as pd
from deepforest import main

def run_inference(input_dir: str, output_file_path: str, config: dict):
    """
    Core inference logic for DeepForest Marine Biodiversity.
    
    Parameters
    ----------
    input_dir : str
        Local directory where all your input images have ALREADY been downloaded.
    output_file_path : str
        The exact local file path where you MUST save your final JSON/KWCOCO results.
    config : dict
        The "config" dictionary passed from the Airflow payload.
    """
    
    print("[MODEL] Starting inference...")
    print("[MODEL] Loading DeepForest marine biodiversity model...")
    
    # 1. Dynamically locate the baked-in Hugging Face checkpoint
    weights_dir = "/workspace/weights"
    checkpoint_files = glob.glob(os.path.join(weights_dir, "*.ckpt")) + glob.glob(os.path.join(weights_dir, "*.pt"))
    
    if not checkpoint_files:
        raise FileNotFoundError(f"Could not find any .ckpt or .pt files in {weights_dir}")
        
    model_path = checkpoint_files[0]
    print(f"[MODEL] Found weights at {model_path}, loading...")
    
    # 2. Load the model 
    # DeepForest uses PyTorch Lightning checkpoints. If this fails, we gracefully 
    # fall back to attempting a standard state_dict load.
    try:
        model = main.deepforest.load_from_checkpoint(model_path)
    except Exception as e:
        print(f"[MODEL] Failed to load as Lightning checkpoint: {e}. Trying state_dict...")
        model = main.deepforest()
        model.model.load_state_dict(torch.load(model_path))
    
    model.eval() # Ensure we are in evaluation mode

    # 3. Extract configurations (hyperparameters, thresholds, etc.)
    conf_thresh = config.get("options", {}).get("conf_thresh", 0.5)
    print(f"[MODEL] Using confidence threshold: {conf_thresh}")
    
    # 4. Setup our output structure (KWCOCO format)
    kwcoco_output = {
        "info": {"description": "DeepForest Marine Biodiversity Output"},
        "categories": [],
        "images": [],
        "annotations": []
    }
    
    print(f"[MODEL] Scanning {input_dir} for input images...")
    input_files = [f for f in os.listdir(input_dir) if os.path.isfile(os.path.join(input_dir, f))]
    
    if not input_files:
        print("[MODEL] WARNING: No input files found in directory!")

    # 5. Run inference on each image
    category_map = {}
    annotation_id = 1
    
    for image_id, filename in enumerate(input_files, start=1):
        filepath = os.path.join(input_dir, filename)
        
        # Verify it's an image and get dimensions for KWCOCO
        try:
            img = cv2.imread(filepath)
            if img is None:
                print(f"[MODEL] Warning: Could not read {filename} as an image. Skipping.")
                continue
            height, width = img.shape[:2]
        except Exception as e:
            print(f"[MODEL] Warning: Error reading {filename}: {e}")
            continue

        kwcoco_output["images"].append({
            "id": image_id,
            "file_name": filename,
            "width": width,
            "height": height 
        })
        
        # Predict using DeepForest
        try:
            # predict_image returns a pandas DataFrame with [xmin, ymin, xmax, ymax, label, score]
            df = model.predict_image(path=filepath)
            
            if df is not None and not df.empty:
                # Filter by our provided confidence threshold
                if 'score' in df.columns:
                    df = df[df['score'] >= conf_thresh]
                
                # Convert the remaining DataFrame rows into KWCOCO annotations
                for _, row in df.iterrows():
                    xmin = float(row['xmin'])
                    ymin = float(row['ymin'])
                    xmax = float(row['xmax'])
                    ymax = float(row['ymax'])
                    score = float(row.get('score', 1.0))
                    label = row['label']
                    
                    # Dynamically build our categories list as we encounter new labels
                    if label not in category_map:
                        cat_id = len(category_map) + 1
                        category_map[label] = cat_id
                        kwcoco_output["categories"].append({
                            "id": cat_id,
                            "name": str(label)
                        })
                    
                    cat_id = category_map[label]
                    
                    # KWCOCO format: [x, y, width, height]
                    bbox = [xmin, ymin, xmax - xmin, ymax - ymin]
                    
                    kwcoco_output["annotations"].append({
                        "id": annotation_id,
                        "image_id": image_id,
                        "category_id": cat_id,
                        "bbox": bbox,
                        "score": round(score, 3)
                    })
                    annotation_id += 1
                    
            found_count = len(df) if df is not None else 0
            print(f"[MODEL] Processed {filename} - Found {found_count} objects.")
            
        except Exception as e:
            print(f"[MODEL] Error during inference on {filename}: {e}")
            
    # 6. Save the output
    print(f"[MODEL] Writing KWCOCO results to {output_file_path}")
    with open(output_file_path, 'w') as f:
        json.dump(kwcoco_output, f, indent=4)
        
    print("[MODEL] Inference complete!")
