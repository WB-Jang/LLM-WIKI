#!/usr/bin/env python3
"""LLM-Wiki NiceGUI Web Interface."""

import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from nicegui import ui

from scripts.config import get_config, wiki_dir, raw_dir
from scripts.ingest import ingest
from scripts.query import query
from scripts.lint import lint

_cfg = get_config()
WIKI_DIR = wiki_dir()
RAW_DIR = raw_dir()


def _tree_nodes(wdir: Path) -> list:
    if not wdir.exists():
        return []
    nodes = []
    for special in ("index.md", "log.md"):
        if (wdir / special).exists():
            nodes.append({"id": special, "label": f"📄 {Path(special).stem}"})
    for subdir in ("sources", "concepts", "entities", "synthesis"):
        d = wdir / subdir
        if d.exists() and any(d.glob("*.md")):
            nodes.append({
                "id": subdir,
                "label": f"📁 {subdir}",
                "children": [
                    {"id": str(f.relative_to(wdir)), "label": f.stem}
                    for f in sorted(d.glob("*.md"))
                ],
            })
    return nodes


def _strip_frontmatter(text: str) -> str:
    if text.startswith("---"):
        end = text.find("---", 3)
        if end > 0:
            return text[end + 3:].strip()
    return text


@ui.page("/")
def main():

    def open_page(path: str):
        full = WIKI_DIR / path
        if not path or not full.exists() or full.is_dir():
            return
        content = _strip_frontmatter(full.read_text("utf-8"))
        page_title.set_text(full.stem)
        page_view.set_content(content)

    def refresh_tree():
        tree_container.clear()
        with tree_container:
            nodes = _tree_nodes(WIKI_DIR)
            if nodes:
                ui.tree(nodes, label_key="label", on_select=lambda e: open_page(e.value))
            else:
                ui.label("위키가 비어있습니다").classes("text-sm text-gray-400")

    async def on_upload(e):
        RAW_DIR.mkdir(exist_ok=True)
        dest = RAW_DIR / e.name
        dest.write_bytes(e.content.read())
        ui.notify(f"'{e.name}' 인제스트 시작...", type="info")
        await asyncio.to_thread(ingest, dest, False)
        ui.notify(f"'{e.name}' 인제스트 완료!", type="positive")
        refresh_tree()

    async def on_query():
        q = chat_input.value.strip()
        if not q:
            return
        chat_input.value = ""
        with chat_log:
            ui.label(f"❓ {q}").classes("font-semibold text-blue-700 text-sm")
            loading = ui.label("생각 중...").classes("text-gray-400 italic text-sm")
        answer, refs = await asyncio.to_thread(query, q, False)
        loading.delete()
        with chat_log:
            ui.markdown(answer).classes("text-sm")
            if refs:
                ui.label(f"참고: {', '.join(Path(r).stem for r in refs)}").classes("text-xs text-blue-400")
            ui.separator()

    async def on_lint():
        result = await asyncio.to_thread(lint, False)
        broken = len(result.get("broken_links", []))
        orphaned = len(result.get("orphaned_pages", []))
        total = result.get("total_pages", 0)
        if broken == 0 and orphaned == 0:
            ui.notify(f"✅ 위키 양호 ({total}개 페이지)", type="positive")
        else:
            ui.notify(f"⚠️ 깨진 링크 {broken}개, 고아 페이지 {orphaned}개", type="warning")

    # ── Layout ────────────────────────────────────────────────────────────────
    with ui.header().classes("bg-slate-800 text-white items-center px-4 py-2"):
        ui.label(_cfg["app"]["title"]).classes("text-xl font-bold")

    with ui.row().classes("w-full h-[calc(100vh-56px)] overflow-hidden"):

        # Sidebar
        with ui.column().classes("w-64 shrink-0 h-full bg-gray-50 border-r p-3 overflow-y-auto gap-2"):
            ui.label("📁 위키").classes("font-bold")
            tree_container = ui.column().classes("w-full")
            refresh_tree()

            ui.separator()
            ui.label("📥 문서 추가").classes("font-bold text-sm")
            ui.upload(auto_upload=True, on_upload=on_upload).classes("w-full")

            ui.separator()
            with ui.row().classes("gap-1"):
                ui.button("Lint", icon="verified", on_click=on_lint).props("flat dense color=orange")
                ui.button("새로고침", icon="refresh", on_click=refresh_tree).props("flat dense color=grey")

        # Main content
        with ui.column().classes("flex-1 h-full overflow-hidden p-3 gap-3"):

            # Wiki page viewer
            with ui.card().classes("flex-1 overflow-auto w-full min-h-0"):
                page_title = ui.label("페이지를 선택하세요").classes(
                    "text-lg font-bold text-gray-400 mb-2"
                )
                page_view = ui.markdown("").classes("w-full prose max-w-none")

            # Chat panel
            with ui.card().classes("w-full shrink-0"):
                ui.label("💬 질문하기").classes("font-bold mb-1")
                with ui.scroll_area().classes("h-48 w-full border rounded p-2 bg-gray-50"):
                    chat_log = ui.column().classes("w-full gap-1")
                with ui.row().classes("w-full gap-2 mt-2 items-center"):
                    chat_input = (
                        ui.input(placeholder="질문을 입력하세요...")
                        .classes("flex-1")
                        .props("outlined dense")
                    )
                    ui.button("전송", on_click=on_query, color="blue").props("dense")
                    chat_input.on("keydown.enter", on_query)


def run():
    ui.run(
        title=_cfg["app"]["title"],
        port=_cfg["app"]["port"],
        reload=False,
        favicon="📚",
    )


if __name__ == "__main__":
    run()
