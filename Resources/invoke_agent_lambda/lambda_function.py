import os
import json
import logging
import psycopg
from strands import Agent
from strands.models.anthropic import AnthropicModel
from strands.tools.mcp import MCPClient
from mcp.client.streamable_http import streamablehttp_client

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# --- SQL ---

SQL_LOAD_MESSAGES = """
    SELECT role, content FROM messages
    WHERE account_id = %s
    ORDER BY created_at ASC
    LIMIT %s
"""

SQL_INSERT_MESSAGE = """
    INSERT INTO messages (account_id, role, content)
    VALUES (%s, %s, %s)
"""

# --- Config ---

PG_DSN = (
    f"host={os.environ['PG_HOST']} dbname={os.environ['PG_DB']} "
    f"user={os.environ['PG_USER']} password={os.environ['PG_PASSWORD']}"
)
MCP_URL            = os.environ["MCP_URL"]
AGENT_MODEL        = os.environ.get("AGENT_MODEL", "claude-haiku-4-5")
ANTHROPIC_API_KEY  = os.environ["ANTHROPIC_API_KEY"]
HISTORY_LIMIT      = 20

SYSTEM_PROMPT = (
    "You are an e-commerce shopping assistant. Use your tools to search the "
    "catalogue, view a user's past orders, place new orders, and fetch product "
    "images for display. "
    "ONLY use information returned by tools — never invent product details. "
    "Always cite the ASIN when referencing a product. "
    "When presenting a product to the user, include its image_url so the chat UI "
    "can render the image. If you only have an ASIN (e.g. from order history), "
    "call get_image to fetch the URL."
)

# module-scope: survives warm invocations
_model = AnthropicModel(
    client_args={"api_key": ANTHROPIC_API_KEY},
    model_id=AGENT_MODEL,
    max_tokens=4096,
)

# --- Memory helpers ---

def load_history(account_id: str) -> list[dict]:
    with psycopg.connect(PG_DSN) as conn, conn.cursor() as cur:
        cur.execute(SQL_LOAD_MESSAGES, (account_id, HISTORY_LIMIT))
        return [
            {"role": role, "content": [{"text": content}]}
            for role, content in cur.fetchall()
        ]

def save_message(account_id: str, role: str, content: str) -> None:
    with psycopg.connect(PG_DSN) as conn, conn.cursor() as cur:
        cur.execute(SQL_INSERT_MESSAGE, (account_id, role, content))

# --- Handler ---

def lambda_handler(event, context):
    logger.info("STEP 1: handler entered")
    body = json.loads(event["body"]) if isinstance(event.get("body"), str) else event
    account_id = body["account_id"]
    question   = body["question"]
    logger.info("STEP 2: parsed body, account_id=%s, q=%r", account_id, question[:80])

    logger.info("STEP 3: loading history from Postgres")
    history = load_history(account_id)
    logger.info("STEP 4: loaded %d history messages", len(history))

    logger.info("STEP 5: opening MCP client connection")
    mcp_client = MCPClient(lambda: streamablehttp_client(MCP_URL))
    with mcp_client:
        logger.info("STEP 6: MCP client opened, listing tools")
        tools = mcp_client.list_tools_sync()
        logger.info("STEP 7: got %d tools, building agent", len(tools))
        agent = Agent(
            model=_model,
            tools=tools,
            system_prompt=f"{SYSTEM_PROMPT}\n\nThe current user's account_id is: {account_id}",
            messages=history,
        )
        logger.info("STEP 8: invoking agent")
        result = agent(question)
        logger.info("STEP 9: agent returned")
        answer = str(result)

    logger.info("STEP 10: saving messages to Postgres")
    save_message(account_id, "user", question)
    save_message(account_id, "assistant", answer)
    logger.info("STEP 11: done, returning response")
    return {"statusCode": 200, "body": json.dumps({"response": answer})}
