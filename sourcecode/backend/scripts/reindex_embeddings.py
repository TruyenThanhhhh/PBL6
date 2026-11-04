"""Rebuild BGE-M3 vectors for existing documents after changing embedding config."""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.database import get_db_connection, init_db
from app.services.document_service import reindex_document_embeddings


def main() -> None:
    parser = argparse.ArgumentParser(description="Reindex BGE-M3 vectors for stored documents.")
    parser.add_argument("--workspace", default=None, help="Only reindex this workspace id.")
    args = parser.parse_args()

    init_db()
    conn = get_db_connection()
    try:
        if args.workspace:
            rows = conn.execute(
                "SELECT id, file_name FROM documents WHERE workspace_id = ? ORDER BY created_at",
                (args.workspace,),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT id, file_name FROM documents ORDER BY created_at"
            ).fetchall()
    finally:
        conn.close()

    if not rows:
        print("Không có tài liệu nào cần reindex.")
        return

    failed = 0
    for index, row in enumerate(rows, start=1):
        print(f"[{index}/{len(rows)}] {row['file_name']} ({row['id']})")
        try:
            result = reindex_document_embeddings(row["id"])
            print(f"  OK: {result['dense_indexed']}/{result['total_chunks']} chunks")
        except Exception as exc:
            failed += 1
            print(f"  FAILED: {exc}")

    print(f"\nHoàn tất: {len(rows) - failed}/{len(rows)} tài liệu.")
    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
