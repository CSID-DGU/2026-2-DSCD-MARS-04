from data_pipeline.extraction.llm.sentence_splitter import split_sentences


def texts(text: str) -> list[str]:
    return [sentence["text"] for sentence in split_sentences(text)]


def test_basic_split_and_ids():
    result = split_sentences("시는 감사를 실시한다. 기간은 10일이다.")
    assert [s["sentence_id"] for s in result] == ["S1", "S2"]
    assert [s["text"] for s in result] == ["시는 감사를 실시한다.", "기간은 10일이다."]


def test_decimal_numbers_are_not_split():
    assert texts("금리는 3.5%로 올랐다. 물가는 2.1% 상승했다.") == [
        "금리는 3.5%로 올랐다.",
        "물가는 2.1% 상승했다.",
    ]


def test_closing_quote_after_period():
    assert texts('그는 "최선을 다하겠다."라고 말했다. 이어 질문을 받았다.') == [
        '그는 "최선을 다하겠다."라고 말했다.',
        "이어 질문을 받았다.",
    ]
    assert texts('"충성도가 높습니다." 그는 덧붙였다.') == [
        '"충성도가 높습니다."',
        "그는 덧붙였다.",
    ]


def test_no_split_inside_quotes():
    assert texts('그는 "계획을 다시 세워야 한다. 늘릴 이유가 없다"고 말했다. 회의는 끝났다.') == [
        '그는 "계획을 다시 세워야 한다. 늘릴 이유가 없다"고 말했다.',
        "회의는 끝났다.",
    ]


def test_no_split_inside_single_quotes():
    assert texts(
        "동반위는 '함께 하는 상생의 힘! 혁신으로 성장'을 주제로 연다. 행사는 이틀간이다."
    ) == [
        "동반위는 '함께 하는 상생의 힘! 혁신으로 성장'을 주제로 연다.",
        "행사는 이틀간이다.",
    ]


def test_unbalanced_quotes_fall_back_to_normal_split():
    assert texts('그는 "계획을 다시 세워야 한다. 회의는 끝났다.') == [
        '그는 "계획을 다시 세워야 한다.',
        "회의는 끝났다.",
    ]


def test_heading_lines_are_separated():
    assert texts("보조금 집행 위법행위 늘어\n충주시가 감사를 실시한다.") == [
        "보조금 집행 위법행위 늘어",
        "충주시가 감사를 실시한다.",
    ]


def test_english_abbreviations_and_list_numbers():
    assert texts("U.S. 정부는 발표했다. 1. 지원 대상은 청년이다.") == [
        "U.S. 정부는 발표했다.",
        "1. 지원 대상은 청년이다.",
    ]


def test_question_and_exclamation():
    assert texts("왜 늦었나? 다시 확인했다!") == ["왜 늦었나?", "다시 확인했다!"]


def test_blank_and_invalid_input():
    assert split_sentences("") == []
    assert split_sentences("   \n\n  ") == []
    assert split_sentences(None) == []


def test_whitespace_normalized():
    assert texts("시는   감사를\t실시한다.   기간은 10일이다.") == [
        "시는 감사를 실시한다.",
        "기간은 10일이다.",
    ]
