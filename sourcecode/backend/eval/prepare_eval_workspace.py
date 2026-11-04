"""Create an isolated workspace and index the RAGAS sample fixture."""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.database import get_db_connection, init_db
from app.services.document_service import process_and_index_document

DEFAULT_FIXTURE = Path(__file__).parent / "fixtures" / "pbl6_rag_notes.md"
DEFAULT_WORKSPACE = "ragas-eval"


def main() -> None:
    parser = argparse.ArgumentParser(description="Prepare the isolated Ragas evaluation workspace.")
    parser.add_argument("--workspace-id", default=DEFAULT_WORKSPACE)
    parser.add_argument("--fixture", type=Path, default=DEFAULT_FIXTURE)
    args = parser.parse_args()

    if not args.fixture.exists():
        raise SystemExit(f"Fixture not found: {args.fixture}")

    init_db()
    conn = get_db_connection()
    try:
        conn.execute(
            "INSERT OR IGNORE INTO workspaces (id, name, description) VALUES (?, ?, ?)",
            (args.workspace_id, "RAGAS Evaluation", "Workspace tự động cho benchmark Ragas"),
        )
        conn.execute(
            "UPDATE workspaces SET name = ?, description = ? WHERE id = ?",
            ("RAGAS Evaluation", "Workspace tự động cho benchmark Ragas", args.workspace_id),
        )
        old_documents = conn.execute(
            "SELECT id FROM documents WHERE workspace_id = ? AND file_name = ?",
            (args.workspace_id, args.fixture.name),
        ).fetchall()
        for document in old_documents:
            conn.execute(
                "DELETE FROM chunks_fts WHERE workspace_id = ? AND document_id = ?",
                (args.workspace_id, document["id"]),
            )
            conn.execute("DELETE FROM documents WHERE id = ?", (document["id"],))
        conn.commit()
    finally:
        conn.close()

    result = process_and_index_document(
        args.workspace_id,
        args.fixture.name,
        args.fixture.read_bytes(),
    )
    print(json.dumps({"workspace_id": args.workspace_id, **result}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
