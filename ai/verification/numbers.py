"""숫자 비교 규칙. 요약 누락 검사, 사실성 검사, 완전성 검사가 같이 쓴다."""

import re

NUMBER = re.compile(r"\d+(?:[.,]\d+)*")
MIDDLE_DOT = re.compile(r"(?<=\d)[·ㆍ](?=\d)")  # 3·1운동처럼 숫자 사이 가운뎃점은 마침표로 본다


def extract_numbers(text: str) -> list[str]:
    """글에 나온 순서대로 숫자를 뽑는다. 1,000과 1000은 같은 숫자로 본다."""
    return [n.replace(",", "") for n in NUMBER.findall(MIDDLE_DOT.sub(".", text))]


def find_missing_numbers(source: str, text: str) -> list[str]:
    """원문에 있는데 text에 없는 숫자 (누락)."""
    source_numbers = extract_numbers(source)
    return sorted(set(source_numbers) - set(extract_numbers(text)), key=source_numbers.index)


def find_new_numbers(source: str, text: str) -> list[str]:
    """text에 있는데 원문에 없는 숫자 (원문이 뒷받침하지 않는 숫자)."""
    return find_missing_numbers(text, source)


def number_context(number: str, source: str) -> str:
    """숫자가 들어 있는 어절을 돌려준다 (예: '김모(54)씨에'). 없으면 숫자 그대로."""
    for word in source.split():
        if number in extract_numbers(word):
            return word
    return number
