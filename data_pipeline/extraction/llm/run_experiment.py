import json
import time
from pathlib import Path

from data_pipeline.extraction.llm.data_loader import load_articles
from data_pipeline.extraction.llm.extractor import extract_key_sentences
from data_pipeline.extraction.llm.sentence_splitter import split_sentences
from data_pipeline.extraction.llm.summarizer import summarize_key_sentences

FILE_PATH = "/Users/parksooyeon/Downloads/original_text.xlsx"

RESULT_DIR = Path("experiments/extraction/llm/results")

RESULT_PATH = RESULT_DIR / "llm_results.json"


def process_article(article: dict) -> dict:
    started_at = time.perf_counter()

    sentences = split_sentences(article["source_text"])

    selected_ids = extract_key_sentences(sentences)

    summaries = summarize_key_sentences(
        sentences=sentences,
        selected_ids=selected_ids,
    )

    sentence_map = {sentence["sentence_id"]: sentence["text"] for sentence in sentences}

    key_sentences = [
        {
            "key_id": f"K{index}",
            "source_sentence_ids": [item["sentence_id"]],
            "original_text": sentence_map[item["sentence_id"]],
            "summary": item["summary"],
        }
        for index, item in enumerate(
            summaries,
            start=1,
        )
    ]

    elapsed_seconds = time.perf_counter() - started_at

    return {
        "document_id": article["document_id"],
        "source_row": article["source_row"],
        "source_text_length": len(article["source_text"]),
        "sentence_count": len(sentences),
        "selected_sentence_count": len(key_sentences),
        "processing_time_seconds": round(
            elapsed_seconds,
            2,
        ),
        "key_sentences": key_sentences,
    }


def main():
    articles = load_articles(
        FILE_PATH,
        limit=10,
    )

    results = []
    failures = []

    print(f"총 {len(articles)}개 기사를 처리합니다.")

    for index, article in enumerate(
        articles,
        start=1,
    ):
        document_id = article["document_id"]

        print(f"[{index}/{len(articles)}] {document_id} 처리 중...")

        try:
            result = process_article(article)
            results.append(result)

            print(
                f"완료: "
                f"{result['selected_sentence_count']}개 선택, "
                f"{result['processing_time_seconds']}초"
            )

        except Exception as error:  # noqa: BLE001
            failures.append(
                {
                    "document_id": document_id,
                    "source_row": article["source_row"],
                    "error_type": type(error).__name__,
                    "error_message": str(error),
                }
            )

            print(f"실패: {document_id} - {type(error).__name__}: {error}")

    output = {
        "experiment": {
            "model": "gpt-4.1-mini",
            "article_count": len(articles),
            "success_count": len(results),
            "failure_count": len(failures),
            "source_excel_rows": [article["source_row"] for article in articles],
        },
        "results": results,
        "failures": failures,
    }

    RESULT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    with RESULT_PATH.open(
        "w",
        encoding="utf-8",
    ) as file:
        json.dump(
            output,
            file,
            ensure_ascii=False,
            indent=2,
        )

    print()
    print("실험 완료")
    print(f"성공: {len(results)}개")
    print(f"실패: {len(failures)}개")
    print(f"결과 파일: {RESULT_PATH}")


if __name__ == "__main__":
    main()
