import json
import os
import logging
import time
import boto3
from openai import OpenAI
from opensearchpy import OpenSearch, RequestsHttpConnection, AWSV4SignerAuth
from opensearchpy.helpers import bulk

# --- Logging ---
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# --- Clients ---
s3 = boto3.client("s3")

# --- Environment Variables ---
S3_BUCKET         = os.environ["S3_BUCKET"]
OPENAI_API_KEY    = os.environ["OPENAI_API_KEY"]
EMBEDDING_MODEL   = os.environ.get("EMBEDDING_MODEL", "text-embedding-3-small")
EMBED_DIMENSIONS  = int(os.environ.get("EMBED_DIMENSIONS", "1024"))
OPENSEARCH_DOMAIN = os.environ["OPENSEARCH_DOMAIN"]
MAIN_INDEX_NAME   = os.environ["INDEX_NAME"]
MAX_RECORDS       = int(os.environ.get("MAX_RECORDS", "0"))  # 0 = no cap
EMBED_DELAY       = float(os.environ.get("EMBED_DELAY", "0.0"))  # sec between embed calls

openai_client = OpenAI(api_key=OPENAI_API_KEY)


# --- Helper Functions ---

def generate_embeddings(text, max_retries=5):
    if not text or not text.strip():
        return None
    # Retry with exponential backoff on rate limit / transient errors
    for attempt in range(max_retries):
        try:
            response = openai_client.embeddings.create(
                model=EMBEDDING_MODEL,
                input=text,
                dimensions=EMBED_DIMENSIONS,
            )
            if EMBED_DELAY > 0:
                time.sleep(EMBED_DELAY)
            return response.data[0].embedding
        except Exception as e:
            msg = str(e).lower()
            if "rate limit" in msg or "429" in msg or "too many" in msg:
                wait = (2 ** attempt) + 1  # 2s, 3s, 5s, 9s, 17s
                logger.warning(f"Rate-limited on embed attempt {attempt + 1}, sleeping {wait}s")
                time.sleep(wait)
                continue
            raise
    raise RuntimeError("Embedding failed after retries (sustained rate limit)")


def _details_to_text(details):
    if not details or not isinstance(details, dict):
        return ""
    parts = []
    for k, v in details.items():
        if v is None:
            continue
        if isinstance(v, dict):
            parts.append(f"{k} {json.dumps(v)}")
        else:
            parts.append(f"{k} {v}")
    return " ".join(parts)


def build_embedding_text(json_data):
    embedding_text = [
        json_data.get("title") or "",
        json_data.get("main_category") or "",
        " ".join(json_data.get("features") or []),
        " ".join(json_data.get("description") or []),
    ]

    price = json_data.get("price")
    if price is not None:
        embedding_text.append(f"Item price: {price}")

    embedding_text.append(_details_to_text(json_data.get("details") or {}))
    return " ".join(filter(None, embedding_text))


def add_embeddings_to_data(json_data):
    embedding_text = build_embedding_text(json_data)
    embeddings = generate_embeddings(embedding_text)
    json_data["embedding"] = embeddings
    return json_data


def extract_main_image_url(images):
    if not isinstance(images, list):
        return None
    for img in images:
        if isinstance(img, dict) and img.get("variant") == "MAIN":
            return img.get("large") or img.get("hi_res") or img.get("thumb")
    return None


def process_row(row):
    json_data = {
        "parent_asin":    row.get("parent_asin"),
        "main_category":  row.get("main_category"),
        "title":          row.get("title"),
        "average_rating": row.get("average_rating"),
        "rating_number":  row.get("rating_number"),
        "price":          row.get("price"),
        "store":          row.get("store"),
        "features":       row.get("features") if isinstance(row.get("features"), list) else None,
        "description":    row.get("description") if isinstance(row.get("description"), list) else row.get("description"),
        "categories":     row.get("categories") if isinstance(row.get("categories"), list) else None,
        "details":        row.get("details") if isinstance(row.get("details"), dict) else None,
        "image_url":      extract_main_image_url(row.get("images")),
    }
    return add_embeddings_to_data(json_data)


def get_opensearch_client(opensearch_url):
    credentials = boto3.Session().get_credentials()
    auth = AWSV4SignerAuth(credentials, "eu-central-1", "es")
    return OpenSearch(
        hosts=[{"host": opensearch_url, "port": 443}],
        http_auth=auth,
        use_ssl=True,
        verify_certs=True,
        connection_class=RequestsHttpConnection,
        pool_maxsize=20,
        timeout=300,
        max_retries=3,
        retry_on_timeout=True,
    )


def push_data_to_opensearch(client, processed_data, chunk_size=100, delay=0.5):
    for i in range(0, len(processed_data), chunk_size):
        chunk = processed_data[i:i + chunk_size]
        actions = [{"_index": MAIN_INDEX_NAME, "_id": d.get("parent_asin"), "_source": d} for d in chunk]
        success, errors = bulk(client, actions, raise_on_error=False, max_retries=3, initial_backoff=2, max_backoff=10)
        logger.info(f"Chunk {i // chunk_size + 1}: indexed {success} | failed {len(errors)}")
        time.sleep(delay)


# --- Lambda Handler ---

def lambda_handler(event, context):
    # 1. get the json file key from the event
    json_file = event["json_file"]
    logger.info(f"Loading s3://{S3_BUCKET}/{json_file}")

    # 2. load the file from s3
    response = s3.get_object(Bucket=S3_BUCKET, Key=json_file)
    file_content = response["Body"].read().decode("utf-16")

    # handles both json array and jsonl formats — plain list, no pandas
    try:
        data = json.loads(file_content)
        if isinstance(data, dict):
            data = [data]
    except json.JSONDecodeError:
        logger.warning("Failed to parse as JSON array, attempting JSONL format")
        data = [json.loads(line) for line in file_content.strip().splitlines() if line.strip()]

    logger.info(f"Loaded {len(data)} records from {json_file}")

    # Cap for demo / quota-constrained environments
    if MAX_RECORDS > 0 and len(data) > MAX_RECORDS:
        logger.info(f"Capping to {MAX_RECORDS} records (MAX_RECORDS env)")
        data = data[:MAX_RECORDS]

    # 3. process each row
    processed_data = []
    failed = 0
    for row in data:
        try:
            processed_data.append(process_row(row))
        except Exception as e:
            failed += 1
            logger.error(f"Failed to process row {row.get('parent_asin', 'unknown')}: {e}")
            continue

    logger.info(f"Processing complete — succeeded: {len(processed_data)} | failed: {failed}")

    # 4. push to opensearch
    logger.info(f"Pushing {len(processed_data)} documents to OpenSearch index '{MAIN_INDEX_NAME}'")
    opensearch_client = get_opensearch_client(OPENSEARCH_DOMAIN)
    push_data_to_opensearch(opensearch_client, processed_data)

    return {
        "statusCode": 200,
        "body": json.dumps({
            "processed": len(processed_data),
            "failed":    failed,
            "source":    json_file,
        }),
    }
