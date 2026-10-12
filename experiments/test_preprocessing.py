import json

from data_pipeline.extraction.llm.data_loader import load_articles
from data_pipeline.extraction.llm.sentence_splitter import split_sentences


FILE_PATH = "/Users/parksooyeon/Downloads/original_text.xlsx"


def main():
    articles = load_articles(FILE_PATH, limit=1)

    if not articles:
        raise ValueError("불러온 기사가 없습니다.")

    article = articles[0]
    sentences = split_sentences(article["source_text"])

    result = {
        "document_id": article["document_id"],
        "source_row": article["source_row"],
        "source_text_length": len(article["source_text"]),
        "sentence_count": len(sentences),
        "sentences": sentences,
    }

    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()