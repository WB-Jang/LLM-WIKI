from typing import Annotated, Sequence, TypedDict
from langchain_core.messages import BaseMessage, SystemMessage, ToolMessage
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI
from langgraph.graph import END, StateGraph
from langgraph.graph.message import add_messages
from app.config import get_api_key, get_config
from app.rag import search as rag_search

SYSTEM_PROMPT = """당신은 한국 금융법규 전문가 AI 어시스턴트입니다.
금융법규 관련 질문에는 knowledge base를 검색하여 정확한 법령 근거를 제시하세요.
항상 한국어로 답변하세요."""


def make_llm(model: str = None, **kwargs):
    cfg = get_config()["llm"]
    return ChatOpenAI(
        model=model or cfg["model"],
        openai_api_key=get_api_key(),
        openai_api_base=cfg["base_url"],
        temperature=cfg["temperature"],
        max_tokens=cfg.get("max_tokens", 4096),
        **kwargs,
    )


@tool
def search_knowledge_base(query: str) -> str:
    """금융법규 지식베이스에서 관련 조항과 내용을 검색합니다."""
    results = rag_search(query)
    if not results:
        return "관련 내용을 찾을 수 없습니다."
    parts = [f"[출처: {r['source']}]\n{r['content']}" for r in results]
    return "\n\n---\n\n".join(parts)


TOOLS = [search_knowledge_base]


class AgentState(TypedDict):
    messages: Annotated[Sequence[BaseMessage], add_messages]


def build_agent(model: str = None):
    llm = make_llm(model).bind_tools(TOOLS)
    tool_map = {t.name: t for t in TOOLS}

    def agent_node(state: AgentState):
        msgs = [SystemMessage(content=SYSTEM_PROMPT)] + list(state["messages"])
        return {"messages": [llm.invoke(msgs)]}

    def tool_node(state: AgentState):
        last = state["messages"][-1]
        results = []
        for call in last.tool_calls:
            result = tool_map[call["name"]].invoke(call["args"])
            results.append(ToolMessage(content=result, tool_call_id=call["id"]))
        return {"messages": results}

    def should_continue(state: AgentState):
        last = state["messages"][-1]
        if getattr(last, "tool_calls", None):
            return "tools"
        return END

    graph = StateGraph(AgentState)
    graph.add_node("agent", agent_node)
    graph.add_node("tools", tool_node)
    graph.set_entry_point("agent")
    graph.add_conditional_edges("agent", should_continue)
    graph.add_edge("tools", "agent")
    return graph.compile()
