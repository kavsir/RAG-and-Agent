from langchain_groq import ChatGroq


llm = ChatGroq(
    model="llama-3.1-8b-instant",   # model Groq
    api_key="key",
    temperature=0
)


def generate_answer(prompt):

    response = llm.invoke(prompt)

    return response.content