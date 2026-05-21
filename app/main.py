import streamlit as st
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from app.agent import SYSTEM_PROMPT, build_agent, make_llm
from app.config import get_api_key, get_config
from app.rag import get_collection, ingest_pdfs, search

cfg = get_config()

st.set_page_config(
    page_title=cfg["app"]["title"],
    page_icon="📚",
    layout="wide",
)


# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.title("⚙️ 설정")

    model_options = [
        cfg["llm"]["model"],
        "openai/gpt-4o",
        "anthropic/claude-3.5-sonnet",
        "google/gemini-flash-1.5",
        "meta-llama/llama-3.3-70b-instruct",
        "deepseek/deepseek-chat",
        "qwen/qwen-2.5-72b-instruct",
    ]
    # deduplicate while preserving order
    seen = set()
    model_options = [m for m in model_options if not (m in seen or seen.add(m))]

    selected_model = st.selectbox("모델", model_options)

    mode = st.radio("모드", ["RAG Q&A", "에이전트", "일반 채팅"])

    st.divider()

    chunk_count = get_collection().count()
    st.metric("인덱싱된 청크 수", chunk_count)

    if st.button("📥 PDF 문서 인덱싱"):
        with st.spinner("인덱싱 중..."):
            n = ingest_pdfs()
        if n > 0:
            st.success(f"{n}개 문서 인덱싱 완료")
            st.rerun()
        else:
            st.info("새로운 문서가 없습니다")

    if chunk_count == 0:
        st.warning("문서가 인덱싱되지 않았습니다.\n'PDF 문서 인덱싱'을 먼저 실행하세요.")

    if not get_api_key():
        st.error("OPENROUTER_API_KEY 환경변수가 필요합니다")

    if st.button("대화 초기화"):
        st.session_state.messages = []
        st.rerun()


# ── Main ──────────────────────────────────────────────────────────────────────
st.title(cfg["app"]["title"])

if "messages" not in st.session_state:
    st.session_state.messages = []

for msg in st.session_state.messages:
    role = "user" if isinstance(msg, HumanMessage) else "assistant"
    with st.chat_message(role):
        st.markdown(msg.content)

if prompt := st.chat_input("금융법규에 대해 질문하세요..."):
    st.session_state.messages.append(HumanMessage(content=prompt))
    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant"):
        answer = ""
        refs = []

        if mode == "RAG Q&A":
            refs = search(prompt)
            context = "\n\n".join(
                f"[출처: {d['source']}]\n{d['content']}" for d in refs
            )
            rag_prompt = (
                f"다음 금융법규 조항을 참고하여 질문에 답하세요.\n\n"
                f"---\n{context}\n---\n\n질문: {prompt}"
            )
            llm = make_llm(selected_model)
            with st.spinner("답변 생성 중..."):
                resp = llm.invoke(
                    [SystemMessage(content=SYSTEM_PROMPT), HumanMessage(content=rag_prompt)]
                )
            answer = resp.content
            st.markdown(answer)
            if refs:
                with st.expander(f"📎 참고 문서 ({len(refs)}건)"):
                    for d in refs:
                        st.caption(f"**{d['source']}** (유사도: {d['score']})")
                        st.text(d["content"][:400] + ("..." if len(d["content"]) > 400 else ""))
                        st.divider()

        elif mode == "에이전트":
            agent = build_agent(selected_model)
            with st.spinner("에이전트 실행 중..."):
                result = agent.invoke({"messages": list(st.session_state.messages)})
            answer = result["messages"][-1].content
            st.markdown(answer)

        else:  # 일반 채팅
            llm = make_llm(selected_model)
            with st.spinner("답변 생성 중..."):
                resp = llm.invoke(
                    [SystemMessage(content=SYSTEM_PROMPT)] + list(st.session_state.messages)
                )
            answer = resp.content
            st.markdown(answer)

    st.session_state.messages.append(AIMessage(content=answer))
