"""Run a reproducible Ragas benchmark on a workspace.

Usage (from sourcecode/backend):
    python eval/prepare_eval_workspace.py
    python eval/ragas_eval.py --workspace ragas-eval --limit 3
    python eval/ragas_eval.py --workspace default --golden eval/my_golden.jsonl

The first command creates an isolated workspace from the sample fixture. Replace
the golden file with your own questions for a real benchmark.
"""
import argparse
import asyncio
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import DEFAULT_LLM_MODEL, OLLAMA_BASE_URL, TOP_K_RETRIEVAL
from app.services.embedding_service import embed_texts
from app.services.llm_service import check_ollama_status, generate_rag_answer
from app.services.retrieval_service import search_relevant_chunks

DEFAULT_GOLDEN = Path(__file__).parent / "golden.sample.jsonl"
DEFAULT_OUTPUT = Path(__file__).parent / "results"


def load_golden(path: Path, limit: int | None) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            item = json.loads(line)
            if not item.get("question") or not item.get("reference"):
                raise SystemExit(f"Golden row missing question/reference: {item}")
            rows.append(item)
    if limit:
        rows = rows[:limit]
    if not rows:
        raise SystemExit(f"Golden dataset is empty: {path}")
    return rows


def build_predictions(rows: List[Dict[str, Any]], workspace_id: str, top_k: int,
                      answer_model: str) -> List[Dict[str, Any]]:
    predictions: List[Dict[str, Any]] = []
    for index, item in enumerate(rows, start=1):
        question = item["question"]
        chunks = search_relevant_chunks(workspace_id, question, top_k)
        result = asyncio.run(
            generate_rag_answer(question, chunks, model_name=answer_model)
        )
        predictions.append(
            {
                "id": item.get("id", f"q{index}"),
                "user_input": question,
                "reference": item["reference"],
                "response": result.get("answer", ""),
                "retrieved_contexts": [chunk["content"] for chunk in chunks],
                "retrieved_documents": [chunk["document_name"] for chunk in chunks],
                "retrieved_chunk_ids": [chunk["chunk_id"] for chunk in chunks],
                "rerank_scores": [chunk.get("rerank_score") for chunk in chunks],
                "engine": result.get("engine"),
                "model_used": result.get("model_used"),
                "fallback_reason": result.get("fallback_reason"),
            }
        )
        print(f"[{index}/{len(rows)}] {item.get('id', index)}: {len(chunks)} chunks, "
              f"engine={result.get('engine')}")
    return predictions


class FastEmbedEmbeddings:
    """LangChain-compatible wrapper around the app's BGE-M3 model."""

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        vectors = embed_texts(list(texts))
        if vectors is None:
            raise RuntimeError("BGE-M3 không sẵn sàng để chạy Ragas.")
        return vectors

    def embed_query(self, text: str) -> List[float]:
        vectors = self.embed_documents([text])
        return vectors[0]


def run_ragas(predictions: List[Dict[str, Any]], judge_model: str,
              output_dir: Path, stamp: str, raise_exceptions: bool = False) -> None:
    try:
        # nest_asyncio 1.6 breaks asyncio.wait_for inside tasks on Python 3.14.
        # Ragas patches asyncio at import time; disable that patch before import.
        import nest_asyncio

        nest_asyncio.apply = lambda *args, **kwargs: None

        from langchain_ollama import ChatOllama
        from ragas import EvaluationDataset, evaluate
        from ragas.embeddings import LangchainEmbeddingsWrapper
        from ragas.llms import LangchainLLMWrapper
        from ragas.metrics import (
            AnswerCorrectness,
            Faithfulness,
            LLMContextPrecisionWithReference,
            LLMContextRecall,
            ResponseRelevancy,
        )
    except ImportError as exc:
        raise SystemExit(
            "Chưa cài bộ đánh giá Ragas. Hãy chạy:\n"
            "  pip install -r requirements-eval.txt"
        ) from exc

    from langchain_core.embeddings import Embeddings

    class RagasEmbeddings(Embeddings):
        def __init__(self) -> None:
            self.wrapper = FastEmbedEmbeddings()

        def embed_documents(self, texts):
            return self.wrapper.embed_documents(texts)

        def embed_query(self, text):
            return self.wrapper.embed_query(text)

    dataset = EvaluationDataset.from_list(
        [
            {
                "user_input": row["user_input"],
                "retrieved_contexts": row["retrieved_contexts"],
                "response": row["response"],
                "reference": row["reference"],
            }
            for row in predictions
        ]
    )
    judge = LangchainLLMWrapper(
        ChatOllama(
            model=judge_model,
            base_url=OLLAMA_BASE_URL,
            temperature=0,
            num_ctx=4096,
        )
    )
    embeddings = LangchainEmbeddingsWrapper(RagasEmbeddings())
    metrics = [
        Faithfulness(),
        ResponseRelevancy(),
        LLMContextPrecisionWithReference(),
        LLMContextRecall(),
        AnswerCorrectness(),
    ]
    result = evaluate(
        dataset,
        metrics=metrics,
        llm=judge,
        embeddings=embeddings,
        raise_exceptions=raise_exceptions,
        show_progress=True,
    )
    frame = result.to_pandas()
    csv_path = output_dir / f"ragas-{stamp}.csv"
    frame.to_csv(csv_path, index=False, encoding="utf-8-sig")

    metric_names = [metric.name for metric in metrics]
    summary = {
        name: float(frame[name].mean())
        for name in metric_names
        if name in frame.columns
    }
    summary_path = output_dir / f"ragas-{stamp}.summary.json"
    summary_path.write_text(
        json.dumps(
            {
                "judge_model": judge_model,
                "samples": len(predictions),
                "metrics": summary,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    print("\nRagas metrics:")
    for name, value in summary.items():
        print(f"  {name}: {value:.4f}")
    print(f"\nPer-sample: {csv_path}")
    print(f"Summary:    {summary_path}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Benchmark the PBL6 RAG pipeline with Ragas.")
    parser.add_argument("--workspace", default="ragas-eval")
    parser.add_argument("--golden", type=Path, default=DEFAULT_GOLDEN)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--top-k", type=int, default=TOP_K_RETRIEVAL)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--answer-model", default=DEFAULT_LLM_MODEL)
    parser.add_argument("--judge-model", default=os.getenv("RAGAS_JUDGE_MODEL", DEFAULT_LLM_MODEL))
    parser.add_argument("--skip-ragas", action="store_true",
                        help="Only generate predictions and retrieval logs.")
    parser.add_argument("--raise-exceptions", action="store_true",
                        help="Raise the first metric error instead of returning NaN.")
    args = parser.parse_args()

    status = asyncio.run(check_ollama_status())
    if not status["running"]:
        print("CẢNH BÁO: Ollama chưa chạy; câu trả lời sẽ là fallback, điểm Ragas sẽ thấp.")
    elif args.judge_model not in status["available_models"]:
        print(f"CẢNH BÁO: chưa có model judge '{args.judge_model}'. Hãy chạy: ollama pull {args.judge_model}")

    rows = load_golden(args.golden, args.limit)
    args.output.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    predictions = build_predictions(rows, args.workspace, args.top_k, args.answer_model)

    predictions_path = args.output / f"predictions-{stamp}.jsonl"
    with predictions_path.open("w", encoding="utf-8") as handle:
        for row in predictions:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    print(f"\nPredictions: {predictions_path}")

    if args.skip_ragas:
        print("Đã bỏ qua Ragas (--skip-ragas).")
        return
    run_ragas(predictions, args.judge_model, args.output, stamp, args.raise_exceptions)


if __name__ == "__main__":
    main()
