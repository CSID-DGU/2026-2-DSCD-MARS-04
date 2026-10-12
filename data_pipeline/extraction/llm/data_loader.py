import pandas as pd


def load_articles(file_path: str, limit: int = 10) -> list[dict]:
    dataframe = pd.read_excel(file_path)

    if "original_text" not in dataframe.columns:
        raise ValueError("original_text 컬럼이 없습니다.")

    articles = []

    for index, text in dataframe["original_text"].head(limit).items():
        if not isinstance(text, str) or not text.strip():
            continue

        articles.append(
            {
                "document_id": f"news_{len(articles) + 1:03d}",
                "source_row": index + 2,
                "source_text": text.strip(),
            }
        )

    return articles