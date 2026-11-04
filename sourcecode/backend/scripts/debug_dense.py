import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2])) # Add backend root to path

from app.config import EMBEDDING_MODEL
from app.database import get_db_connection
from app.services.embedding_service import embed_texts, unpack_vector

query = "ConvNeXt Tiny dùng kiến trúc gì?"
qv = embed_texts([query])[0]
conn = get_db_connection()


def cos(a, b):
    return sum(x * y for x, y in zip(a, b)) / (
        math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(y * y for y in b))
    )


rows = conn.execute(
    "SELECT c.content,c.chunk_index,d.file_name,e.vector,e.dimensions "
    "FROM chunk_embeddings e JOIN document_chunks c ON c.id=e.chunk_id "
    "JOIN documents d ON d.id=c.document_id WHERE c.workspace_id=? AND e.model=?",
    ("default", EMBEDDING_MODEL),
).fetchall()
scored = []
for r in rows:
    v = unpack_vector(r["vector"], r["dimensions"])
    scored.append((cos(qv, v), r["file_name"], r["chunk_index"], r["content"][:100]))
scored.sort(reverse=True)
for s in scored[:8]:
    print(round(s[0], 4), s[1], s[2], repr(s[3]))
conn.close()
