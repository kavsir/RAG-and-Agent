import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from src.agent.graph import graph

def main():
    print("🤖 Chào bạn! Tôi là trợ lý cố vấn học tập. Hãy nhập câu hỏi (gõ 'exit' để thoát).")
    while True:
        question = input("\n💬 Bạn: ").strip()
        if question.lower() in ['exit', 'quit', 'thoát']:
            print("👋 Tạm biệt!")
            break
        if not question:
            continue

        initial_state = {
            "question": question,
            "rewritten_question": "",
            "intent": "",
            "plan": "",
            "retrieved_docs": [],
            "context": "",
            "answer": "",
            "reflection": "",
            "student_profile": {},
            "chat_history": "",
            "messages": [],
            "validation_result": {},
            "regenerate_count": 0,
            "skip_pipeline": False
        }

        result = graph.invoke(initial_state)
        print(f"\n🤖 Trợ lý: {result['answer']}")

if __name__ == "__main__":
    main()