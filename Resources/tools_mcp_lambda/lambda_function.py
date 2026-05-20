import os
import json
import boto3
import psycopg
from openai import OpenAI
from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings
from mangum import Mangum
from opensearchpy import OpenSearch, RequestsHttpConnection, AWSV4SignerAuth

# --- SQL ---

SQL_GET_ORDERS = """
    SELECT order_id, parent_asin, quantity, created_at
    FROM orders
    WHERE account_id = %s
    ORDER BY created_at DESC
"""

SQL_INSERT_ORDER = """
    INSERT INTO orders (account_id, parent_asin, quantity)
    VALUES (%s, %s, %s)
    RETURNING order_id
"""

# --- Config ---

mcp = FastMCP(
    "data-robot-tools",
    stateless_http=True,
    # API Gateway forwards the original Host header; default DNS rebinding
    # protection only allows localhost so it would 421. Safe to disable here:
    # the MCP endpoint is fronted by API Gateway and demo-grade auth=NONE.
    transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False),
)

PG_DSN = (
    f"host={os.environ['PG_HOST']} dbname={os.environ['PG_DB']} "
    f"user={os.environ['PG_USER']} password={os.environ['PG_PASSWORD']}"
)
OPENSEARCH_DOMAIN = os.environ["OPENSEARCH_DOMAIN"]
MAIN_INDEX_NAME   = os.environ["MAIN_INDEX_NAME"]
OPENAI_API_KEY    = os.environ["OPENAI_API_KEY"]
EMBEDDING_MODEL   = os.environ.get("EMBEDDING_MODEL", "text-embedding-3-small")
EMBED_DIMENSIONS  = int(os.environ.get("EMBED_DIMENSIONS", "1024"))

# module-scope: survives warm invocations
_openai = OpenAI(api_key=OPENAI_API_KEY)
_os_client = OpenSearch(
    hosts=[{"host": OPENSEARCH_DOMAIN.replace("https://", "").replace("http://", ""), "port": 443}],
    http_auth=AWSV4SignerAuth(boto3.Session().get_credentials(), "eu-central-1", "es"),
    use_ssl=True,
    verify_certs=True,
    connection_class=RequestsHttpConnection,
)

# --- Helpers ---

def _embed(text: str) -> list[float]:
    response = _openai.embeddings.create(
        model=EMBEDDING_MODEL,
        input=text,
        dimensions=EMBED_DIMENSIONS,
    )
    return response.data[0].embedding

# --- Tools ---

@mcp.tool()
def search_products(query: str, top_k: int = 5) -> list[dict]:
    """Search the product catalogue. Returns asin, title, price, rating, image_url."""
    emb = _embed(query)
    r = _os_client.search(index=MAIN_INDEX_NAME, body={
        "size": top_k,
        "query": {"knn": {"embedding": {"vector": emb, "k": top_k}}},
        "_source": ["parent_asin", "title", "price", "average_rating", "features", "image_url"],
    })
    return [h["_source"] for h in r["hits"]["hits"]]

@mcp.tool()
def get_orders(account_id: str) -> list[dict]:
    """Return all orders for an account, newest first."""
    with psycopg.connect(PG_DSN) as conn, conn.cursor() as cur:
        cur.execute(SQL_GET_ORDERS, (account_id,))
        return [
            {"order_id": str(r[0]), "parent_asin": r[1],
             "quantity": r[2], "created_at": r[3].isoformat()}
            for r in cur.fetchall()
        ]

@mcp.tool()
def make_purchase(account_id: str, parent_asin: str, quantity: int) -> dict:
    """Place a new order. Returns the created order_id."""
    with psycopg.connect(PG_DSN) as conn, conn.cursor() as cur:
        cur.execute(SQL_INSERT_ORDER, (account_id, parent_asin, quantity))
        return {"order_id": str(cur.fetchone()[0]), "status": "created"}

@mcp.tool()
def get_image(parent_asin: str) -> dict:
    """Return the main product image URL for a given ASIN. Use this when displaying
    a product the user already knows about (e.g. from their order history)."""
    try:
        r = _os_client.get(
            index=MAIN_INDEX_NAME, id=parent_asin, _source=["image_url"]
        )
        return {"parent_asin": parent_asin, "image_url": r["_source"].get("image_url")}
    except Exception:
        return {"parent_asin": parent_asin, "image_url": None}

# Lambda entry point.
#
# FastMCP's StreamableHTTPSessionManager is single-shot: its .run() can only
# be called once. Mangum invokes the ASGI lifespan startup on every warm
# Lambda invocation, so we'd fail on the second request with
# "StreamableHTTPSessionManager .run() can only be called once per instance."
#
# Fix: clear the cached session manager before each invocation so
# streamable_http_app() rebuilds a fresh one. The FastMCP instance itself
# stays at module scope so tools, the OpenSearch client, and the embed client
# all survive warm reuse — only the session manager is per-invocation.
def handler(event, context):
    mcp._session_manager = None
    return Mangum(mcp.streamable_http_app(), lifespan="on")(event, context)
