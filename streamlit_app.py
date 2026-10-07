"""HealthVision AI — architecture documentation viewer (Streamlit).

Renders README.md and every docs/*.md file. This is a docs viewer only;
it is not the HealthVision AI application.
"""

import re
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).parent
DOCS_DIR = ROOT / "docs"

st.set_page_config(page_title="HealthVision AI — Architecture", page_icon="🩺", layout="wide")


def load_docs() -> dict[str, Path]:
    docs = {"README": ROOT / "README.md"}
    for path in sorted(DOCS_DIR.glob("*.md")):
        docs[path.stem] = path
    return docs


def title_of(path: Path) -> str:
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("# "):
            return line[2:].strip()
    return path.stem


def rewrite_links(text: str) -> str:
    """Turn relative .md links into ?doc= links so they work inside the app."""

    def repl(match: re.Match) -> str:
        label, target = match.group(1), match.group(2)
        stem = Path(target.split("#")[0]).stem
        return f"[{label}](?doc={stem})"

    return re.sub(r"\[([^\]]+)\]\((?!https?://)([^)]+\.md)(?:#[^)]*)?\)", repl, text)


docs = load_docs()
keys = list(docs)

requested = st.query_params.get("doc", "README")
if requested not in docs:
    requested = "README"

with st.sidebar:
    st.title("🩺 HealthVision AI")
    st.caption("Architecture & implementation plan — planning phase, no application code yet.")
    query = st.text_input("Search all documents")
    selected = st.radio(
        "Documents",
        keys,
        index=keys.index(requested),
        format_func=lambda k: title_of(docs[k]),
    )
    if selected != requested:
        st.query_params["doc"] = selected

if query:
    st.header(f"Search: “{query}”")
    hits = 0
    pattern = re.compile(re.escape(query), re.IGNORECASE)
    for key, path in docs.items():
        lines = path.read_text(encoding="utf-8").splitlines()
        matches = [ln.strip() for ln in lines if pattern.search(ln)]
        if matches:
            hits += len(matches)
            with st.expander(f"{title_of(path)} — {len(matches)} match(es)"):
                st.markdown(f"[Open document](?doc={key})")
                for m in matches[:25]:
                    st.text(m)
    if not hits:
        st.info("No matches.")
else:
    text = docs[selected].read_text(encoding="utf-8")
    st.markdown(rewrite_links(text), unsafe_allow_html=False)
    st.divider()
    st.download_button(
        "Download this document (.md)",
        text,
        file_name=docs[selected].name,
        mime="text/markdown",
    )
