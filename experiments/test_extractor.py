import json

from data_pipeline.extraction.llm.data_loader import load_articles
from data_pipeline.extraction.llm.extractor import extract_key_sentences
from data_pipeline.extraction.llm.sentence_splitter import split_sentences

FILE_PATH = "/Users/parksooyeon/Downloads/original_text.xlsx"


def main():
    articles = load_articles(FILE_PATH, limit=1)
    article = articles[0]

    sentences = split_sentences(article["source_text"])
    selected_ids = extract_key_sentences(sentences)

    sentence_map = {sentence["sentence_id"]: sentence["text"] for sentence in sentences}

    result = {
        "document_id": article["document_id"],
        "key_sentences": [
            {
                "sentence_id": sentence_id,
                "text": sentence_map[sentence_id],
            }
            for sentence_id in selected_ids
        ],
    }

    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
