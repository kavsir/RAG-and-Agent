"""
LangGraph Workflow: Cấu trúc đồ thị điều hướng hội thoại AI Academic Advisor.
Đảm bảo 100% các node đều có đường dẫn đến và thoát, không có dead nodes.
"""
import logging
from langgraph.graph import StateGraph, END

from src.agent.state import AgentState
from src.agent.nodes import (
    cache_node,
    query_analysis_node,
    router_node,
    retrieve_node,
    rerank_node,
    context_node,
    grounded_answer_node,
    general_answer_node,
    validation_node,
    parse_reminder_node,
    parse_email_node,
    save_chat_node,
)

logger = logging.getLogger(__name__)

# Khởi tạo workflow StateGraph
workflow = StateGraph(AgentState)

# 1. Khai báo toàn bộ các node
workflow.add_node("cache", cache_node)
workflow.add_node("analysis", query_analysis_node)
workflow.add_node("router", router_node)

# Nhánh DOMAIN_DATA (RAG)
workflow.add_node("retrieve", retrieve_node)
workflow.add_node("rerank", rerank_node)
workflow.add_node("context", context_node)
workflow.add_node("grounded_answer", grounded_answer_node)
workflow.add_node("validation", validation_node)

# Nhánh GENERAL_LLM (Direct)
workflow.add_node("general_answer", general_answer_node)

# Nhánh TOOL_ACTION
workflow.add_node("reminder", parse_reminder_node)
workflow.add_node("email", parse_email_node)

# Node kết thúc & lưu trữ
workflow.add_node("save_chat", save_chat_node)

# 2. Entry Point
workflow.set_entry_point("cache")


# 3. Điều hướng sau Cache
def route_from_cache(state: AgentState) -> str:
    if state.get("cache_hit", False):
        return "save_chat"
    return "analysis"


workflow.add_conditional_edges(
    "cache",
    route_from_cache,
    {
        "save_chat": "save_chat",
        "analysis": "analysis",
    },
)

# Analysis -> Router
workflow.add_edge("analysis", "router")


# 4. Điều hướng chính sau Router
def route_after_router(state: AgentState) -> str:
    category = state.get("category", "DOMAIN_DATA")
    tool_intent = state.get("tool_intent")

    if category == "TOOL_ACTION":
        if tool_intent == "SEND_EMAIL":
            return "email"
        return "reminder"
    elif category == "GENERAL_LLM":
        return "general_answer"
    else:
        # Default: DOMAIN_DATA (RAG)
        return "retrieve"


workflow.add_conditional_edges(
    "router",
    route_after_router,
    {
        "retrieve": "retrieve",
        "general_answer": "general_answer",
        "reminder": "reminder",
        "email": "email",
    },
)

# 5. Các cạnh trong nhánh DOMAIN_DATA
workflow.add_edge("retrieve", "rerank")
workflow.add_edge("rerank", "context")
workflow.add_edge("context", "grounded_answer")
workflow.add_edge("grounded_answer", "validation")


# 6. Điều hướng sau Validation (chống lặp vô tận)
def route_after_validation(state: AgentState) -> str:
    val_res = state.get("validation_result", {})
    retry_count = state.get("retry_count", 0)

    # Nếu câu trả lời hợp lệ hoặc đã retry đủ 2 lần -> lưu chat và hoàn tất
    if val_res.get("valid", True) or retry_count >= 2:
        return "save_chat"

    # Nếu không hợp lệ và còn lượt thử -> quay lại retrieve
    logger.info(f"Validation khong dat. Thu lai retrieve lan {retry_count + 1}/2...")
    return "retrieve"


workflow.add_conditional_edges(
    "validation",
    route_after_validation,
    {
        "save_chat": "save_chat",
        "retrieve": "retrieve",
    },
)

# 7. Các cạnh thoát về save_chat
workflow.add_edge("general_answer", "save_chat")
workflow.add_edge("reminder", "save_chat")
workflow.add_edge("email", "save_chat")

# 8. Kết thúc workflow
workflow.add_edge("save_chat", END)

# Compile LangGraph
graph = workflow.compile()
