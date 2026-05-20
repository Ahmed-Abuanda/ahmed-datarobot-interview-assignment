import re
import requests
import streamlit as st

# --- Edit these two values ---
API_URL = "https://u9tklkpvl2.execute-api.eu-central-1.amazonaws.com/invoke"
ACCOUNT_ID = "094fca41-cad5-4c58-8c3e-30dd578c4ea7"

# Match jpg/jpeg/png/gif/webp URLs, optionally with query string
IMAGE_URL_RE = re.compile(
    r"https?://\S+?\.(?:jpg|jpeg|png|gif|webp)(?:\?\S*)?",
    re.IGNORECASE,
)

st.set_page_config(page_title="Shopping Assistant", page_icon="🛒")
st.title("🛒 Shopping Assistant")
st.caption(f"Account: `{ACCOUNT_ID}`")

if "messages" not in st.session_state:
    st.session_state.messages = []

# render past turns
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.write(msg["content"])
        for url in msg.get("images", []):
            st.image(url, width=200)

# new turn
if prompt := st.chat_input("Ask about products, place an order, see your history..."):
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.write(prompt)

    with st.chat_message("assistant"):
        with st.spinner("Thinking..."):
            r = requests.post(
                API_URL,
                json={"account_id": ACCOUNT_ID, "question": prompt},
                timeout=120,
            )
            r.raise_for_status()
            answer = r.json()["response"]

        st.write(answer)
        images = IMAGE_URL_RE.findall(answer)
        for url in images:
            st.image(url, width=200)

        st.session_state.messages.append({
            "role": "assistant",
            "content": answer,
            "images": images,
        })
