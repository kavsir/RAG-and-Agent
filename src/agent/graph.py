from langgraph.graph import StateGraph, END
from .state import AgentState
from .nodes import (
    cache_node,
    rewrite_node,
    memory_node,
    intent_node,
    retrieve_node,
    context_node,
    answer_node,
    validation_node,   # thêm import
    save_chat_node,
    parse_reminder_node,
    reminder_node,
    parse_email_request_node,
    send_email_node
)

# Debug flag
DEBUG = True

workflow = StateGraph(AgentState)

# Thêm nodes
workflow.add_node("cache", cache_node)
workflow.add_node("rewrite", rewrite_node)
workflow.add_node("memory", memory_node)
workflow.add_node("intent", intent_node)
workflow.add_node("retrieve", retrieve_node)
workflow.add_node("context", context_node)
workflow.add_node("answer", answer_node)
workflow.add_node("validation", validation_node)   # thêm node validation
workflow.add_node("save_chat", save_chat_node)
workflow.add_node("parse_reminder", parse_reminder_node)
workflow.add_node("reminder", reminder_node)
workflow.add_node("parse_email_request", parse_email_request_node)
workflow.add_node("send_email", send_email_node)

workflow.set_entry_point("cache")

def route_from_cache(state):
    if state.get("skip_pipeline", False):
        return "save_chat"
    else:
        return "rewrite"

workflow.add_conditional_edges(
    "cache",
    route_from_cache,
    {
        "save_chat": "save_chat",
        "rewrite": "rewrite"
    }
)

workflow.add_edge("rewrite", "memory")
workflow.add_edge("memory", "intent")

def route_after_intent(state):
    """
    Điều hướng dựa trên category:
    - DOMAIN_DATA: Cần RAG để lấy dữ liệu → retrieve_node
    - GENERAL_LLM: Không cần RAG → answer_node (bỏ qua retrieve)
    """
    category = state.get("category", "GENERAL_LLM")
    
    if DEBUG:
        print(f"🔀 Router: category={category}")
    
    if category == "DOMAIN_DATA":
        # Câu hỏi về dữ liệu nội bộ → Must use RAG
        return "retrieve"
    else:
        # GENERAL_LLM: Kiến thức chung → Bỏ qua retrieve, đi thẳng đến answer
        return "answer"

workflow.add_conditional_edges(
    "intent",
    route_after_intent,
    {
        "retrieve": "retrieve",
        "answer": "answer"
    }
)

workflow.add_edge("retrieve", "context")
workflow.add_edge("context", "answer")

# Sau answer, quyết định có cần validate hay không
def route_after_answer(state):
    """
    - DOMAIN_DATA: Cần validation để kiểm tra đạt yêu cầu không
    - GENERAL_LLM: Không cần validation, đi thẳng save_chat
    """
    category = state.get("category", "GENERAL_LLM")
    
    if DEBUG:
        print(f"🔀 Route after answer: category={category}")
    
    if category == "DOMAIN_DATA":
        # Yêu cầu validation cho câu trả lời dựa trên dữ liệu nội bộ
        return "validation"
    else:
        # GENERAL_LLM không cần validation
        return "save_chat"

workflow.add_conditional_edges(
    "answer",
    route_after_answer,
    {
        "validation": "validation",
        "save_chat": "save_chat"
    }
)

# Điều hướng sau validation: nếu không valid và còn lượt regenerate, quay lại retrieve
def should_continue(state):
    """
    Smart routing after validation to prevent infinite loops.
    Uses retry_count to track attempts and break out gracefully.
    """
    max_regenerate = 2  # tối đa 2 lần regenerate
    validation = state.get("validation_result", {})
    regenerate_count = state.get("regenerate_count", 0)
    retry_count = state.get("retry_count", 0)
    
    # Safety: max retry attempts to prevent infinite loop
    MAX_RETRY_ATTEMPTS = 3
    
    # If validation is valid, proceed to save
    if validation.get("valid", False):
        return "save_chat"
    
    # If max retries exceeded, force save (escape hatch)
    if retry_count >= MAX_RETRY_ATTEMPTS:
        if DEBUG: print(f"⚠️ Max retry count ({MAX_RETRY_ATTEMPTS}) reached. Forcing save_chat.")
        return "save_chat"
    
    # If still have regenerate attempts, try retrieve again
    if regenerate_count < max_regenerate and retry_count < MAX_RETRY_ATTEMPTS:
        if DEBUG: print(f"↻ Regenerating (attempt {regenerate_count + 1}/{max_regenerate}, retry {retry_count})")
        return "retrieve"
    
    # Default: save and end
    return "save_chat"

workflow.add_conditional_edges(
    "validation",
    should_continue,
    {
        "retrieve": "retrieve",
        "save_chat": "save_chat"
    }
)

# Sau save_chat, xử lý reminder/email
def route_after_save(state):
    if state.get("reminder_requests"):
        return "reminder"
    elif state.get("email_requests"):
        return "send_email"
    else:
        return END

workflow.add_conditional_edges(
    "save_chat",
    route_after_save,
    {
        "reminder": "reminder",
        "send_email": "send_email",
        END: END
    }
)

workflow.add_edge("parse_reminder", "save_chat")
workflow.add_edge("reminder", END)
workflow.add_edge("parse_email_request", "save_chat")
workflow.add_edge("send_email", END)

graph = workflow.compile()