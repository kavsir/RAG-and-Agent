import streamlit as st
import sys
import os
import threading
import time
sys.path.insert(0, os.path.dirname(__file__))

from src.agent.graph import graph
from src.cache.exact_cache import ExactCache
from src.scheduler.reminder_scheduler import start_scheduler, shutdown_scheduler

# Khởi động scheduler trong thread riêng
def run_scheduler():
    start_scheduler()
    while True:
        time.sleep(1)

scheduler_thread = threading.Thread(target=run_scheduler, daemon=True)
scheduler_thread.start()

st.set_page_config(page_title="Cố vấn học tập Đại Nam", page_icon="🎓")
st.title("🎓 Trợ lý cố vấn học tập - Khoa CNTT")

# Khởi tạo session state
if "conversations" not in st.session_state:
    st.session_state.conversations = {
        "Mặc định": {"messages": [], "cache_hit": 0, "cache_miss": 0}
    }
if "current_conv" not in st.session_state:
    st.session_state.current_conv = "Mặc định"
if "show_delete_confirm" not in st.session_state:
    st.session_state.show_delete_confirm = False
if "profile" not in st.session_state:
    # Đọc profile từ file nếu có
    from src.memory.student_memory import StudentMemory
    mem = StudentMemory()
    st.session_state.profile = mem.get_profile()

# Sidebar
with st.sidebar:
    st.header("💬 Đoạn hội thoại")
    
    # Danh sách hội thoại
    conv_names = list(st.session_state.conversations.keys())
    selected = st.radio(
        "Chọn hội thoại",
        conv_names,
        index=conv_names.index(st.session_state.current_conv) if st.session_state.current_conv in conv_names else 0
    )
    if selected != st.session_state.current_conv:
        st.session_state.current_conv = selected
        st.rerun()
    
    # Tạo mới
    new_name = st.text_input("Tên hội thoại mới", key="new_conv")
    col1, col2 = st.columns(2)
    with col1:
        if st.button("➕ Tạo") and new_name:
            if new_name not in st.session_state.conversations:
                st.session_state.conversations[new_name] = {"messages": [], "cache_hit": 0, "cache_miss": 0}
                st.session_state.current_conv = new_name
                st.rerun()
            else:
                st.error("Tên đã tồn tại!")
    
    # Xóa hội thoại
    with col2:
        if st.session_state.current_conv != "Mặc định":
            if st.button("🗑️ Xóa"):
                st.session_state.show_delete_confirm = True
    
    if st.session_state.get("show_delete_confirm", False):
        st.warning(f"Xóa hội thoại '{st.session_state.current_conv}'?")
        col3, col4 = st.columns(2)
        with col3:
            if st.button("✅ Có"):
                del st.session_state.conversations[st.session_state.current_conv]
                st.session_state.current_conv = list(st.session_state.conversations.keys())[0]
                st.session_state.show_delete_confirm = False
                st.rerun()
        with col4:
            if st.button("❌ Không"):
                st.session_state.show_delete_confirm = False
                st.rerun()
    
    st.markdown("---")
    
    # Thông tin cá nhân
    st.header("👤 Thông tin cá nhân")
    
    # Các ô nhập liệu với giá trị từ session state
    new_name = st.text_input("Họ tên", value=st.session_state.profile.get("name", "") or "")
    new_email = st.text_input("Email", value=st.session_state.profile.get("email", "") or "")
    new_major = st.text_input("Ngành học", value=st.session_state.profile.get("major", "") or "")
    new_cohort = st.text_input("Khóa học (ví dụ: K19)", value=st.session_state.profile.get("cohort", "") or "")
    new_style = st.text_input("Phong cách học tập", value=st.session_state.profile.get("style", "") or "")
    
    if st.button("💾 Lưu thông tin"):
        # Cập nhật profile
        profile = st.session_state.profile
        profile["name"] = new_name if new_name else None
        profile["email"] = new_email if new_email else None
        profile["major"] = new_major if new_major else None
        profile["cohort"] = new_cohort if new_cohort else None
        profile["style"] = new_style if new_style else None
        
        # Lưu vào file
        from src.memory.student_memory import StudentMemory
        mem = StudentMemory()
        mem.profile = profile
        mem.save()
        
        st.success("✅ Đã lưu thông tin cá nhân!")
    
    st.markdown("---")
    
    # Thống kê cache
    current = st.session_state.conversations[st.session_state.current_conv]
    st.header("📊 Thống kê")
    st.write(f"Cache hit: {current['cache_hit']}")
    st.write(f"Cache miss: {current['cache_miss']}")
    
    if st.button("🗑️ Xóa cache toàn bộ"):
        cache = ExactCache()
        cache.clear()
        for conv in st.session_state.conversations.values():
            conv["cache_hit"] = 0
            conv["cache_miss"] = 0
        st.success("Đã xóa cache toàn bộ!")
    
    st.markdown("---")
    st.markdown("**Hướng dẫn:**")
    st.markdown("- Cập nhật thông tin cá nhân ở trên")
    st.markdown("- Đặt lịch nhắc: 'nhắc tôi lịch thi ngày 23/3 trước 2 ngày'")
    st.markdown("- Gửi email: 'gửi email chúc mừng sinh nhật cho ...@gmail.com'")

# Hiển thị lịch sử chat
current_conv = st.session_state.conversations[st.session_state.current_conv]
for msg in current_conv["messages"]:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

# Nhập câu hỏi
if prompt := st.chat_input("Nhập câu hỏi..."):
    current_conv["messages"].append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant"):
        with st.spinner("Đang suy nghĩ..."):
            # Lấy profile hiện tại từ session state (đã được cập nhật qua sidebar)
            profile = st.session_state.profile

            initial_state = {
                "question": prompt,
                "rewritten_question": "",
                "intent": "",
                "plan": "",
                "retrieved_docs": [],
                "context": "",
                "answer": "",
                "reflection": "",
                "student_profile": profile,
                "chat_history": "",
                "messages": [],
                "validation_result": {},
                "regenerate_count": 0,
                "skip_pipeline": False,
                "reminder_requests": [],
                "reminder_results": []
            }
            result = graph.invoke(initial_state)
            answer = result.get("answer", "Xin lỗi, tôi không thể trả lời câu hỏi này.")
            
            # Nếu có need_email từ parse_reminder_node, hiển thị thông báo
            if result.get("need_email"):
                answer = result.get("answer", "Vui lòng cung cấp email của bạn.")
            
            st.markdown(answer)
            current_conv["messages"].append({"role": "assistant", "content": answer})

            # Cập nhật thống kê cache
            if result.get("skip_pipeline", False):
                current_conv["cache_hit"] += 1
            else:
                current_conv["cache_miss"] += 1

# Đảm bảo scheduler dừng khi app kết thúc
import atexit
atexit.register(shutdown_scheduler)