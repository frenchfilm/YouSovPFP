import functions_framework
import requests
import json
import sys
import os
import io
from PIL import Image
from google.cloud import storage
from io import BytesIO
import time
import uuid as guid
import threading
import random
import yaml

yaml_path = ".env.yaml"
if os.path.exists(yaml_path):
     print("Loading environment variables from .env.yaml")
     env_vars = yaml.safe_load(open(yaml_path))
     os.environ.update(env_vars)
else:
     print("No .env.yaml file found")
PUBLIC_IMAGES_BUCKET = os.environ.get("PUBLIC_IMAGES_BUCKET")
SDAPI_KEY = os.environ.get("SDAPI_KEY")
CLIPDROP_KEY = os.environ.get("CLIPDROP_KEY")
AUTH_KEY = os.environ.get("AUTH_KEY")
# print(f"PUBLIC_IMAGES_BUCKET: {PUBLIC_IMAGES_BUCKET}")
# print(f"SDAPI_KEY: {SDAPI_KEY}")
# print(f"CLIPDROP_KEY: {CLIPDROP_KEY}")

def initData():

    original_sp = ["https://storage.googleapis.com/esov-sdapi-args-images/original_sp.jpg"]
    final_sp = ["https://storage.googleapis.com/esov-sdapi-args-images/final_sp.png"]
    l1_chin = ["https://storage.googleapis.com/esov-sdapi-args-images/l1_chin.png"]
    l3 = [
        "https://storage.googleapis.com/esov-sdapi-args-images/l3_george.png",
        "https://storage.googleapis.com/esov-sdapi-args-images/l3_luke.png",
        "https://storage.googleapis.com/esov-sdapi-args-images/l3_satoshi.png",
        "https://storage.googleapis.com/esov-sdapi-args-images/l3_spart.png",
        "https://storage.googleapis.com/esov-sdapi-args-images/l3_sun.png",
        "https://storage.googleapis.com/esov-sdapi-args-images/l3_will.png",
    ]
    l4_bg = [
        "https://storage.googleapis.com/esov-sdapi-args-images/l4_bg_01.jpg",
        "https://storage.googleapis.com/esov-sdapi-args-images/l4_bg_02.jpg",
        "https://storage.googleapis.com/esov-sdapi-args-images/l4_bg_03.jpg",
        "https://storage.googleapis.com/esov-sdapi-args-images/l4_bg_04.jpg",
        "https://storage.googleapis.com/esov-sdapi-args-images/l4_bg_05.jpg",
        "https://storage.googleapis.com/esov-sdapi-args-images/l4_bg_06.jpg",
    ]

    all_arrays = [original_sp, final_sp, l1_chin, l3, l4_bg]
    for arr in all_arrays:
        for i in range(len(arr)):
            url = arr[i]
            imageBytes = requests.get(url).content
            pilImage = Image.open(BytesIO(imageBytes))
            arr[i] = pilImage
    return all_arrays

[original_sp, final_sp, l1_chin, l3, l4_bg] = initData()


def auth(request):
    apikey_header = request.headers.get("x-api-key")
    return apikey_header == AUTH_KEY
    
def get_cn_image():
    url = "https://stablediffusionapi.com/api/v5/controlnet"
    pilImage = None
    payload = json.dumps({
        "key": SDAPI_KEY,
        "controlnet_model": "canny",
        "controlnet_type": "canny",
        "model_id": "juggernaut111",
        "auto_hint": "yes",
        "guess_mode": "no",
        "prompt": "a predator alien wearing a Roman Gladiator helmet with this shape",
        "negative_prompt": None,
        "init_image": "https://storage.googleapis.com/esov-sdapi-args-images/sp_512.jpg",
        "samples": "1",
        "scheduler": "UniPCMultistepScheduler",
        "num_inference_steps": "35",
        "safety_checker": "no",
        "enhance_prompt": "yes",
        "guidance_scale": 7.5,
        "strength": 0.55,
        "lora_model": None,
        "tomesd": "yes",
        "use_karras_sigmas": "yes",
        "vae": None,
        "lora_strength": None,
        "embeddings_model": None,
        "seed": None,
        "webhook": None,
        "track_id": None
    })

    headers = {
    'Content-Type': 'application/json'
    }

    response = requests.request("POST", url, headers=headers, data=payload)

    json_val = response.json()
    # print(json.dumps(json_val, indent=4))
    req_status = json_val['status']
    # print(req_status)
    if req_status != 'success' and req_status != 'processing':
        print("request failed")
    else:
        output_url = None
        if 'fetch_result' in json_val:
            print("fetch_result")
            result_url = json_val['fetch_result']
            print(f"fetch_result url: {result_url}")
            payload_fr = json.dumps({
                "key": SDAPI_KEY,
            })
            status = None
            timeStart = time.time()
            while status != 'success':
                # print("running fetch_result")
                result_fr = requests.request("POST", result_url, headers=headers, data=payload_fr)
                json_result = result_fr.json()
                # print(json.dumps(json_result, indent=4))
                status = json_result['status']
                # print(status)
                timeEnd = time.time()
                if timeEnd - timeStart > 120:
                    print("timeout")
                    break
            if status == 'success':
                output_url = json_result['output'][0]
            
        elif 'output' in json_val and len(json_val['output']) > 0:
            print("output")
            output_url = json_val['output'][0]

        if output_url is None:
            print("no output url")
        else:
            attempts = 0
            while attempts < 5:
                try:
                    print("getting output url")
                    imageBytes = requests.get(output_url).content
                    pilImage = Image.open(BytesIO(imageBytes))
                    break
                except:
                    print("error getting output url")
                    time.sleep(0.1)
                finally:
                    attempts += 1
    return pilImage

def remove_bg(pilImage):
    rembg_image = None
    image_file_object = io.BytesIO()
    pilImage.save(image_file_object, format='JPEG')
    image_file_object.seek(0)  # Go back to the start of the file object
    image_bytes = image_file_object.read()  # Read the bytes from the file object
    r = requests.post('https://clipdrop-api.co/remove-background/v1',
    files = {
        'image_file': ('car.jpg', image_bytes, 'image/jpeg'),
        },
    headers = { 'x-api-key': CLIPDROP_KEY }
    )
    if (r.ok):
        print("success")
        rembg_image = Image.open(io.BytesIO(r.content))
    else:
        print(r.status_code, r.text) # e.g. 400 "Invalid image file"
    return rembg_image

def compose_image(pilHelm):
    random_bg = l4_bg[random.randint(0, len(l4_bg) - 1)]
    random_bottom = l3[random.randint(0, len(l3) - 1)]
    base_image = Image.new('RGBA', random_bg.size, (0, 0, 0, 0))
    base_image.paste(random_bg, (0, 0))
    base_image.paste(random_bottom, (0, 0), random_bottom)
    base_image.paste(pilHelm, (0, 0), pilHelm)
    base_image.paste(l1_chin[0], (0, 0), l1_chin[0])
    return base_image

def save_image_to_bucket(pilImage):
    storage_client = storage.Client()
    bucket = storage_client.bucket(PUBLIC_IMAGES_BUCKET)
    randomGuid = guid.uuid4()
    blob = bucket.blob(f"{randomGuid}.png")
    image_file_object = io.BytesIO()
    pilImage.save(image_file_object, format='PNG')
    image_file_object.seek(0)  # Go back to the start of the file object
    image_bytes = image_file_object.read()  # Read the bytes from the file object
    blob.upload_from_string(image_bytes, content_type="image/png")
    return f"https://storage.googleapis.com/{PUBLIC_IMAGES_BUCKET}/{randomGuid}.png"

@functions_framework.http
def api(request):
    if not auth(request):
        return "Unauthorized", 401
    print("Request started")
    print("Creating helm")
    helm = get_cn_image()
    if helm is None:
        print("No helm")
        return "Internal server error", 500
    # quality drop here, upgrade to upscale
    print("Resizing helm")
    helm = helm.resize((800, 800))
    print("Removing bg")
    helm = remove_bg(helm)
    print("Composing image")
    pilImage = compose_image(helm)
    print("Saving image")
    imageUrl = save_image_to_bucket(pilImage)
    print("Request ended")
    return {
        "imageUrl": imageUrl
    }
