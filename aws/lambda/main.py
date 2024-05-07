import json
import requests
import sys
import os
import io
from PIL import Image
from io import BytesIO
import time
import uuid as guid
import threading
import random
import boto3
import yaml
import numpy as np
import redis

s3 = boto3.client('s3')
yaml_path = ".env.yaml"
additional_yaml_path = ".env.additional.yaml"
if os.path.exists(yaml_path):
     print("Loading environment variables from .env.yaml")
     env_vars = yaml.safe_load(open(yaml_path))
     os.environ.update(env_vars)
else:
     print("No .env.yaml file found")

if os.path.exists(additional_yaml_path):
    print("Loading additional environment variables from .env.additional.yaml")
    env_vars = yaml.safe_load(open(additional_yaml_path))
    os.environ.update(env_vars)

PUBLIC_IMAGES_BUCKET = os.environ.get("PUBLIC_IMAGES_BUCKET")
ARGS_IMAGES_BUCKET = os.environ.get("ARGS_IMAGES_BUCKET")
SDAPI_KEY = os.environ.get("SDAPI_KEY")
CLIPDROP_KEY = os.environ.get("CLIPDROP_KEY")
AUTH_KEY = os.environ.get("AUTH_KEY")
REDIS_HOST = os.environ.get("REDIS_HOST")
NFT_API_KEY = os.environ.get("NFTSTORAGE_KEY")
LAYERS_META_FOLD = "layers_meta"

print(f"ARGS_IMAGES_BUCKET: {ARGS_IMAGES_BUCKET}")
print(f"PUBLIC_IMAGES_BUCKET: {PUBLIC_IMAGES_BUCKET}")
print(f"REDIS_HOST: {REDIS_HOST}")
# print(f"SDAPI_KEY: {SDAPI_KEY}")
# print(f"CLIPDROP_KEY: {CLIPDROP_KEY}")


with open('randombag_value.lua', 'r') as file:
    randombag_value_lua = file.read()

redis_client = redis.StrictRedis(host=REDIS_HOST, port=6379, db=0)

print("Loaded")

get_s3_pub_url = lambda bucket, key: f"https://{bucket}.s3.amazonaws.com/{key}"
nft_api_upload_url = "https://api.nft.storage/upload"

def save_image_to_bucket(pilImage):
    s3 = boto3.resource('s3')
    randomGuid = guid.uuid4()
    image_file_object = io.BytesIO()
    pilImage.save(image_file_object, format='PNG')
    image_file_object.seek(0)  
    image_bytes = image_file_object.read()
    s3.Bucket(PUBLIC_IMAGES_BUCKET).put_object(Key=f"{randomGuid}.png", Body=image_bytes, ContentType="image/png")
    return f"https://{PUBLIC_IMAGES_BUCKET}.s3.amazonaws.com/{randomGuid}.png"

def save_metadata_to_bucket(metadata):
    s3 = boto3.resource('s3')
    randomGuid = guid.uuid4()
    metadata_file_object = io.BytesIO()
    metadata_file_object.write(json.dumps(metadata).encode('utf-8'))
    metadata_file_object.seek(0)  
    metadata_bytes = metadata_file_object.read()
    s3.Bucket(PUBLIC_IMAGES_BUCKET).put_object(Key=f"{randomGuid}.json", Body=metadata_bytes, ContentType="application/json")
    return f"https://{PUBLIC_IMAGES_BUCKET}.s3.amazonaws.com/{randomGuid}.json"

def upload_to_nft(byte_stream):
    byte_stream.seek(0)
    buffer = byte_stream.read()
    files = {
        'file': buffer
    }
    headers = {
        'Authorization': f'Bearer {NFT_API_KEY}'
    }
    response = requests.post(nft_api_upload_url, files=files, headers=headers)
    cid = response.json()['value']['cid']
    return cid


def load_prob_map(meta):
    # order meta by probability
    print("===Loading prob map")
    meta_sorted = sorted(meta, key=lambda x: x["probability"], reverse=False)
    buckets = {}
    buckets_count = 0
    min_prob = meta_sorted[0]["probability"]
    max_prob = meta_sorted[-1]["probability"]
    sum_prob = 0
    for i, p in enumerate(meta_sorted):
        prob = p["probability"]
        p["idx"] = i
        if not prob in buckets:
            buckets_count += 1
            buckets[prob] = {
                "probability": 0,
                "item_probability": prob,
                "idx": buckets_count,
                "items": {}
            }
        bucket = buckets[prob]
        sum_prob += prob
        bucket["probability"] += prob
        bucket["lower_bound"] = meta_sorted[i]["probability"]
        bucket["upper_bound"] = meta_sorted[i+1]["probability"] if i < len(meta_sorted)-1 else meta_sorted[i]["probability"]
        bucket["items"][i] = p

    print(f"Total buckets: {buckets_count}")
    print(f"Sum of probabilities: {sum_prob}")
    print(f"Min prob: {min_prob}, max prob: {max_prob}")
    print("===Prob map loaded")
    return buckets

def get_random_item(meta):
    buckets = meta["buckets"]
    probabilities = [p["probability"] for p in buckets.values()]
    bucket_rolled = np.random.choice(list(buckets.values()), p=probabilities)
    random_item = np.random.choice(list(bucket_rolled["items"].values()))
    print(f"Random item: {random_item['name']}")
    return random_item

def loadMeta(name):
    print(f"Loading meta for {name}")
    json_str = s3.get_object(Bucket=ARGS_IMAGES_BUCKET, Key=f"{LAYERS_META_FOLD}/{name}.json")['Body'].read().decode('utf-8')
    meta_body = json.loads(json_str)
    prob_map = load_prob_map(meta_body["data"])
    meta_body["buckets"] = prob_map
    return meta_body

def get_img(meta_record):
    image_path = meta_record["img_path"]

    if image_path:
        if not "img" in meta_record:
            meta_record["img"] = Image.open(BytesIO(s3.get_object(Bucket=ARGS_IMAGES_BUCKET, Key=f"{LAYERS_META_FOLD}/{image_path}")['Body'].read()))
        return meta_record["img"]
    
    # no image in record
    return None

def initData():
    
    L1 = loadMeta("L1")
    L2 = loadMeta("L2")
    L3 = loadMeta("L3")
    L4 = loadMeta("L4")

    return [L1, L2, L3, L4]
        
print("Loading images")
[L1, L2, L3, L4] = initData()
print("Images loaded")


def auth(request):
    apikey_header = request['headers']["x-api-key"]
    return apikey_header == AUTH_KEY
    
def get_cn_image(prompt_part, randint_seed):
    url = "https://stablediffusionapi.com/api/v5/controlnet"
    pilImage = None
    payload = json.dumps({
        "key": SDAPI_KEY,
        "controlnet_model": "canny",
        "controlnet_type": "canny",
        "model_id": "juggernaut111",
        "auto_hint": "yes",
        "guess_mode": "no",
        "prompt": f"a predator alien wearing a {prompt_part} helmet with this shape",
        "negative_prompt": None,
        "init_image": f"https://s3.amazonaws.com/{ARGS_IMAGES_BUCKET}/sp_512.jpg",
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
        "seed": randint_seed,
        "webhook": None,
        "track_id": None
    })

    headers = {
    'Content-Type': 'application/json'
    }
    print("helm: sending request")
    response = requests.request("POST", url, headers=headers, data=payload)
    print("helm: request sent")

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

def compose_image(l1_img, helm, l3_img, l4_img):
    base_image = Image.new('RGBA', l1_img.size, (0, 0, 0, 0))
    base_image.paste(l4_img, (0, 0))
    base_image.paste(l3_img, (0, 0), l3_img)
    base_image.paste(helm, (0, 0), helm)
    base_image.paste(l1_img, (0, 0), l1_img)
    return base_image

def generate_metadata(image_cid, seed, l1, l2, l3, l4):
    json_data = {
        "name": "valiAnt",
        "description": "valiAnts are the core volunteer participants in the original Riddle of the Crown. They are the few, the brave, they are the gladiators, they are the Revolt!",
        "image_cid": image_cid,
        "attributes": [
            {
                "trait_type": "Prompt",
                "value": l2["name"]
            },
            {
                "trait_type": "Seed",
                "value": seed
            },
            {
                "trait_type": "Chin guard",
                "value": l1["name"]
            },
            {
                "trait_type": "Body Type",
                "value": l3["name"]
            },
            {
                "trait_type": "Body Color 1",
                "value": l3["color"]
            },
            {
                "trait_type": "Background",
                "value": l4["name"]
            },
            {
                "trait_type":"MintDate",
                "value": time.strftime("%Y-%m-%d") 
            }
        ]
    }    
    return json_data

def generate_pfp(request, context):
    if not auth(request):
        return {
        'statusCode': 401,
        'body': json.dumps("Unauthorized")
    }
    print("Request started")

    print("Getting random items")
    l1 = get_random_item(L1)
    l2 = get_random_item(L2)
    l3 = get_random_item(L3)
    l4 = get_random_item(L4)

    print("Getting images")
    get_img(l1)
    get_img(l3)
    get_img(l4)

    print("Creating helm")
    randint_seed = random.randint(0, 1000000)
    helm = get_cn_image(l2["name"], randint_seed)
    if helm is None:
        print("No helm")
        return "Internal server error", 500
    # quality drop here, upgrade to upscale
    # todo save helm and image on the backup bsafe ucket
    print("Resizing helm")
    helm = helm.resize((800, 800))
    print("Removing bg")
    helm = remove_bg(helm)
    print("Composing image")
    pilImage = compose_image(l1['img'], helm, l3['img'], l4['img'])
    print("Saving image to S3")
    image_url = save_image_to_bucket(pilImage)
    print("Saving image to IPFS")
    byte_stream = io.BytesIO()
    pilImage.save(byte_stream, format='PNG')
    image_cid = upload_to_nft(byte_stream)
    metadata = generate_metadata(image_cid, randint_seed, l1, l2, l3, l4)
    print("Saving metadata to S3")
    metadata_url = save_metadata_to_bucket(metadata)
    print("Saving metadata to IPFS")
    metadata_cid = upload_to_nft(io.BytesIO(json.dumps(metadata).encode('utf-8')))
    print("Request ended")
    return {
        'statusCode': 200,
        'body': json.dumps({
            "image_cid": image_cid,
            "metadata_cid": metadata_cid,
            "imageUrl": image_url,
            "metadataUrl": metadata_url
        })
    }

# todo: rename bg->house images
def get_random_bg(request, context):
    if not auth(request):
        return {
        'statusCode': 401,
        'body': json.dumps("Unauthorized")
    }
    print("Request started")
    val = redis_client.eval(randombag_value_lua, 0, "pfp_bg", ','.join(map(str, range(1, 6))))
    print(f"Random val: {val}")
    int_val = int(val)
    print("Request ended")
    img_url = get_s3_pub_url(ARGS_IMAGES_BUCKET, f'bgs/pub_bg_{int_val}.jpg')
    print(f"Image url: {img_url}")
    return {
        'statusCode': 200,
        'body': json.dumps({
            "imageUrl": img_url
        })
    }
