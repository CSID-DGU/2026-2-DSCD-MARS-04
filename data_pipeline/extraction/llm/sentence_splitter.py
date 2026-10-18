import re

SENTENCE_END = r"[.!?]"
CLOSERS = "\"'”’)]」』"
QUOTE_PAIRS = [("“", "”"), ("‘", "’")]
STRAIGHT_QUOTES = ['"', "'"]

BOUNDARY_PATTERN = re.compile(rf"{SENTENCE_END}[{re.escape(CLOSERS)}]*(?=\s+)")
NO_SPLIT_PATTERN = re.compile(
    r"(?:\b[A-Z]\.|\b(?:Mr|Mrs|Ms|Dr|Prof|St|Jr|Sr|vs|etc|No)\.|(?:^|\s)\d{1,2}\.)$"
)  # 영문 약어(U.S., Dr.)와 목록 번호(1.)에서는 자르지 않는다.


def _quotes_balanced(line: str) -> bool:
    straight_ok = all(line.count(quote) % 2 == 0 for quote in STRAIGHT_QUOTES)
    curly_ok = all(line.count(left) == line.count(right) for left, right in QUOTE_PAIRS)
    return straight_ok and curly_ok


def _inside_quotes(line: str, position: int) -> bool:
    before = line[:position]
    straight_open = any(before.count(quote) % 2 == 1 for quote in STRAIGHT_QUOTES)
    curly_open = any(before.count(left) > before.count(right) for left, right in QUOTE_PAIRS)
    return straight_open or curly_open


def split_line(line: str) -> list[str]:
    line = re.sub(r"\s+", " ", line).strip()
    if not line:
        return []

    protect_quotes = _quotes_balanced(line)
    sentences = []
    start = 0

    for match in BOUNDARY_PATTERN.finditer(line):
        end = match.end()
        if NO_SPLIT_PATTERN.search(line[start : match.start() + 1]):
            continue
        if protect_quotes and _inside_quotes(line, end):
            continue
        sentences.append(line[start:end].strip())
        start = end

    rest = line[start:].strip()
    if rest:
        sentences.append(rest)

    return [sentence for sentence in sentences if sentence]


def split_sentences(text: str) -> list[dict]:
    if not isinstance(text, str):
        return []

    sentences = [sentence for line in text.splitlines() for sentence in split_line(line)]

    return [
        {
            "sentence_id": f"S{index}",
            "text": sentence,
        }
        for index, sentence in enumerate(sentences, start=1)
    ]


# ex) {"sentence_id" : "S1", 'text': "..."}
