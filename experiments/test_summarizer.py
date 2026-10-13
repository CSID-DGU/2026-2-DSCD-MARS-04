import json

from data_pipeline.extraction.llm.data_loader import load_articles
from data_pipeline.extraction.llm.extractor import extract_key_sentences
from data_pipeline.extraction.llm.sentence_splitter import split_sentences
from data_pipeline.extraction.llm.summarizer import summarize_key_sentences

FILE_PATH = "/Users/parksooyeon/Downloads/original_text.xlsx"


def main():
    articles = load_articles(FILE_PATH, limit=1)
    article = articles[0]

    sentences = split_sentences(article["source_text"])

    selected_ids = extract_key_sentences(sentences)

    summaries = summarize_key_sentences(
        sentences=sentences,
        selected_ids=selected_ids,
    )

    sentence_map = {sentence["sentence_id"]: sentence["text"] for sentence in sentences}

    result = {
        "document_id": article["document_id"],
        "key_sentences": [
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
        ],
    }

    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
