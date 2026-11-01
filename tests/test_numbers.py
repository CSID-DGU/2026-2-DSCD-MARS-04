from ai.verification.numbers import find_missing_numbers, find_new_numbers, number_context


def test_find_missing_numbers_treats_commas_as_same():
    assert find_missing_numbers("주민 1,200명, 58명", "주민 1200명, 58명") == []
    assert find_missing_numbers("14일 58명", "14일") == ["58"]


def test_find_new_numbers_finds_numbers_not_in_source():
    assert find_new_numbers("최대 5개 지역에 120억 원", "5개 지역에 120억 원") == []
    assert find_new_numbers("최대 5개 지역", "7개 지역에 120억 원") == ["7", "120"]


def test_number_context_returns_word_with_number():
    assert number_context("54", "김모(54)씨에 따르면") == "김모(54)씨에"
    assert number_context("9", "숫자 없음") == "9"


def test_middle_dot_between_digits_is_same_as_period():
    assert find_new_numbers("3.1운동 제100주년", "3·1운동 100주년") == []
