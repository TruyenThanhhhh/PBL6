"""Deterministically list vocabulary entries from indexed document text."""
import re
from typing import Any, Dict, List, Optional

from app.database import get_db_connection

_LIST_INTENT = re.compile(
    r"\b(?:liệt\s+kê|kể\s+tên|danh\s+sách|list|show\s+me|name\s+all)\b", re.I
)
_VOCAB_INTENT = re.compile(
    r"\b(?:từ\s+vựng|từ\s+tiếng\s+anh|vocabulary|vocabularies|english\s+words|các\s+từ)\b", re.I
)
_PREFIX_INTENT = re.compile(
    r"\b(?:bắt\s+đầu|khởi\s+đầu|begin(?:ning)?|start(?:ing)?)\s+"
    r"(?:bằng|với|with|by)?\s*(?:chữ|ký\s+tự|letter|character)?\s*"
    r"[\"'“”‘’]?([a-z])[\"'“”‘’]?(?![a-z])",
    re.I,
)
_ENTRY_LINE = re.compile(
    r"^\s*([A-Za-z][A-Za-z'-]*)\s+(?="
    r"(?:n|v|adj|adv|prep|conj|pron|det|aux|num|interj|modal)\b|/)"
)


def _requested_letter(query: str) -> Optional[str]:
    if not _LIST_INTENT.search(query) or not _VOCAB_INTENT.search(query):
        return None
    match = _PREFIX_INTENT.search(query)
    return match.group(1).lower() if match else None


def extract_vocabulary_listing(
    workspace_id: str,
    query: str,
    document_id: Optional[str] = None,
    document_ids: Optional[List[str]] = None,
) -> Optional[Dict[str, Any]]:
    """Return a complete exact list when the request explicitly asks for one."""
    letter = _requested_letter(query)
    if not letter:
        return None

    if document_id:
        document_filter = " AND d.id = ?"
        document_params: tuple = (document_id,)
    elif document_ids:
        placeholders = ",".join("?" for _ in document_ids)
        document_filter = f" AND d.id IN ({placeholders})"
        document_params = tuple(document_ids)
    else:
        document_filter = ""
        document_params = ()

    conn = get_db_connection()
    try:
        rows = conn.execute(
            """
            SELECT d.id AS document_id, d.file_name AS document_name,
                   c.page_number, c.chunk_index, c.content
            FROM documents d
            JOIN document_chunks c ON c.document_id = d.id
            WHERE d.workspace_id = ? AND d.status IN ('indexed', 'ready', 'completed')
            {document_filter}
            ORDER BY d.id, c.chunk_index
            """.format(document_filter=document_filter),
            (workspace_id, *document_params),
        ).fetchall()
    finally:
        conn.close()

    by_document: Dict[str, Dict[str, Any]] = {}
    for row in rows:
        doc_id = row["document_id"]
        doc = by_document.setdefault(doc_id, {
            "document_id": doc_id,
            "document_name": row["document_name"],
            "entries": {},
        })
        for line in row["content"].splitlines():
            match = _ENTRY_LINE.match(line)
            if not match or not match.group(1).lower().startswith(letter):
                continue
            clean_line = re.sub(r"\s+", " ", line).strip()
            key = clean_line.casefold()
            doc["entries"].setdefault(key, {
                "text": clean_line,
                "page_number": row["page_number"],
            })

    # Avoid turning a general question about a small note into a vocabulary dump.
    matching_docs = [doc for doc in by_document.values() if len(doc["entries"]) >= 10]
    if not matching_docs:
        return None

    citations: List[Dict[str, Any]] = []
    citation_by_page: Dict[tuple[str, int], int] = {}
    lines = [f"Tìm thấy **{sum(len(doc['entries']) for doc in matching_docs)} từ vựng** bắt đầu bằng chữ **{letter.upper()}** trong tài liệu:"]
    for doc in matching_docs:
        lines.append(f"\n### {doc['document_name']}")
        for entry in doc["entries"].values():
            page = int(entry["page_number"] or 1)
            page_key = (doc["document_id"], page)
            if page_key not in citation_by_page:
                ref_id = len(citations) + 1
                citation_by_page[page_key] = ref_id
                citations.append({
                    "ref_id": ref_id,
                    "source_type": "document",
                    "document_id": doc["document_id"],
                    "document_name": doc["document_name"],
                    "page_number": page,
                    "page_label": f"Trang {page}",
                    "snippet": entry["text"][:200],
                })
            lines.append(f"- {entry['text']} [{citation_by_page[page_key]}]")

    return {
        "answer": "\n".join(lines),
        "citations": citations,
        "model_used": "document_list_extractor",
        "engine": "deterministic_document_extractor",
        "listed_count": sum(len(doc["entries"]) for doc in matching_docs),
    }
