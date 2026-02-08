"""
RAG Chat Interface - ChatGPT-like UI
====================================
A simple Streamlit app for users to query the RAG system.

Run locally:
    streamlit run src/admin_ui/chat_app.py

Run in Docker:
    docker run -p 8501:8501 rag-chat-ui
"""

import os
import requests
import streamlit as st
from datetime import datetime

# Configuration
RAG_API_URL = os.environ.get("RAG_API_URL", "http://localhost:8080")

# Page config
st.set_page_config(
    page_title="Siva AI - RAG Assistant",
    page_icon="🤖",
    layout="centered",
    initial_sidebar_state="collapsed",
)

# Custom CSS for ChatGPT-like appearance
st.markdown("""
<style>
    .stApp {
        max-width: 800px;
        margin: 0 auto;
    }
    .chat-message {
        padding: 1rem;
        border-radius: 0.5rem;
        margin-bottom: 1rem;
        display: flex;
        flex-direction: column;
    }
    .user-message {
        background-color: #f0f2f6;
    }
    .assistant-message {
        background-color: #e8f4f8;
    }
    .message-header {
        font-weight: bold;
        margin-bottom: 0.5rem;
        font-size: 0.9rem;
    }
    .message-content {
        line-height: 1.6;
    }
    .metadata {
        font-size: 0.75rem;
        color: #666;
        margin-top: 0.5rem;
    }
    .stTextInput > div > div > input {
        font-size: 1rem;
    }
</style>
""", unsafe_allow_html=True)


def query_rag(question: str, use_rag: bool = True) -> dict:
    """Query the RAG API."""
    endpoint = "/api/v1/query" if use_rag else "/api/v1/chat"
    payload = {"query": question, "top_k": 3} if use_rag else {"message": question}
    
    try:
        response = requests.post(
            f"{RAG_API_URL}{endpoint}",
            json=payload,
            timeout=30,
        )
        response.raise_for_status()
        return response.json()
    except requests.exceptions.ConnectionError:
        return {"error": f"Cannot connect to RAG API at {RAG_API_URL}"}
    except requests.exceptions.Timeout:
        return {"error": "Request timed out"}
    except Exception as e:
        return {"error": str(e)}


def check_health() -> bool:
    """Check if RAG API is healthy."""
    try:
        response = requests.get(f"{RAG_API_URL}/health", timeout=5)
        return response.status_code == 200
    except:
        return False


# Header
st.title("🤖 Siva AI Assistant")
st.caption("Powered by Azure OpenAI + RAG on AKS")

# Sidebar
with st.sidebar:
    st.header("⚙️ Settings")
    
    # API URL config
    api_url = st.text_input("RAG API URL", value=RAG_API_URL)
    if api_url != RAG_API_URL:
        RAG_API_URL = api_url
    
    # Mode toggle
    use_rag = st.toggle("Use RAG (Knowledge Base)", value=True)
    st.caption("Toggle off for direct LLM chat without document retrieval")
    
    # Health check
    st.divider()
    if st.button("🔄 Check API Health"):
        if check_health():
            st.success("✅ API is healthy")
        else:
            st.error("❌ API is not reachable")
    
    # Stats
    st.divider()
    st.header("📊 Session Stats")
    if "total_queries" not in st.session_state:
        st.session_state.total_queries = 0
        st.session_state.total_tokens = 0
        st.session_state.total_cost = 0.0
    
    st.metric("Queries", st.session_state.total_queries)
    st.metric("Tokens Used", st.session_state.total_tokens)
    st.metric("Est. Cost", f"${st.session_state.total_cost:.4f}")
    
    if st.button("Clear Stats"):
        st.session_state.total_queries = 0
        st.session_state.total_tokens = 0
        st.session_state.total_cost = 0.0
        st.rerun()

# Initialize chat history
if "messages" not in st.session_state:
    st.session_state.messages = []

# Display chat history
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])
        if "metadata" in message:
            meta = message["metadata"]
            st.caption(f"🕐 {meta.get('latency', 'N/A')}ms | 📝 {meta.get('tokens', 'N/A')} tokens | 💰 ${meta.get('cost', 0):.4f}")

# Chat input
if prompt := st.chat_input("Ask me anything about Kubernetes, Azure, RAG..."):
    # Add user message
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)
    
    # Get response
    with st.chat_message("assistant"):
        with st.spinner("Thinking..."):
            result = query_rag(prompt, use_rag=use_rag)
        
        if "error" in result:
            st.error(f"❌ {result['error']}")
            response_content = f"Error: {result['error']}"
            metadata = {}
        else:
            response_content = result.get("answer", "No response")
            st.markdown(response_content)
            
            # Extract metadata
            meta = result.get("metadata", {})
            latency = meta.get("latency_ms", result.get("latency_ms", 0))
            tokens = meta.get("total_tokens", result.get("tokens", {}).get("total", 0))
            cost = meta.get("estimated_cost_usd", result.get("estimated_cost_usd", 0))
            
            metadata = {"latency": int(latency), "tokens": tokens, "cost": cost}
            
            # Show metadata
            st.caption(f"🕐 {int(latency)}ms | 📝 {tokens} tokens | 💰 ${cost:.4f}")
            
            # Show sources if available
            sources = result.get("sources", [])
            if sources:
                with st.expander("📚 Sources"):
                    for src in sources:
                        st.markdown(f"- {src}")
            
            # Update session stats
            st.session_state.total_queries += 1
            st.session_state.total_tokens += tokens
            st.session_state.total_cost += cost
    
    # Save assistant message
    st.session_state.messages.append({
        "role": "assistant",
        "content": response_content,
        "metadata": metadata,
    })

# Quick questions
if not st.session_state.messages:
    st.divider()
    st.subheader("💡 Try asking:")
    
    col1, col2 = st.columns(2)
    
    with col1:
        if st.button("What is Kubernetes?", use_container_width=True):
            st.session_state.quick_question = "What is Kubernetes?"
            st.rerun()
        if st.button("Explain RAG architecture", use_container_width=True):
            st.session_state.quick_question = "Explain RAG architecture"
            st.rerun()
    
    with col2:
        if st.button("How does Azure AKS work?", use_container_width=True):
            st.session_state.quick_question = "How does Azure AKS work?"
            st.rerun()
        if st.button("What is vector search?", use_container_width=True):
            st.session_state.quick_question = "What is vector search?"
            st.rerun()

# Handle quick questions
if "quick_question" in st.session_state:
    prompt = st.session_state.pop("quick_question")
    st.session_state.messages.append({"role": "user", "content": prompt})
    result = query_rag(prompt, use_rag=True)
    
    if "error" not in result:
        meta = result.get("metadata", {})
        st.session_state.messages.append({
            "role": "assistant",
            "content": result.get("answer", ""),
            "metadata": {
                "latency": int(meta.get("latency_ms", 0)),
                "tokens": meta.get("total_tokens", 0),
                "cost": meta.get("estimated_cost_usd", 0),
            }
        })
        st.session_state.total_queries += 1
        st.session_state.total_tokens += meta.get("total_tokens", 0)
        st.session_state.total_cost += meta.get("estimated_cost_usd", 0)
    st.rerun()

# Footer
st.divider()
st.caption("Built with ❤️ using Streamlit, FastAPI, Azure OpenAI & AKS")
