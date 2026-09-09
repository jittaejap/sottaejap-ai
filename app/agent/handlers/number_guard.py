"""생성된 문장의 숫자가 집계 근거 안에 있는지 코드로 한 번 더 검증한다 (E-79 · E-101).

프롬프트 지시("근거에 없는 수치를 지어내지 마세요")만으로는 100% 못 막는다는 게
실측으로 남아 있다(ANALYSIS_NARRATE, 지어낸 `9.9%`). `ANALYSIS_NARRATE`(#43)와
`ANALYSIS`(#48)가 이 검증을 공유한다 — 두 Handler는 근거를 서로 다른 모양으로
들고 있어서(`ANALYSIS_NARRATE`는 `state.by_verdict[]` snake_case, `ANALYSIS`는
Tool 응답 `byVerdict` camelCase), 이 모듈은 필드 이름을 모른다. 호출자가 각자의
근거에서 항목 리스트와 기준 연월만 뽑아서 넘긴다.
"""

import re

# 소수점을 한 덩어리로 잡는다. "3.6%"를 "3"·"6"으로 쪼개면 둘 다 한 자리라
# 아래 서수 예외에 걸려 검사 없이 통과한다 — 지어낸 "9.9%"가 그 구멍으로 샜다(E-79).
_NUMBER_PATTERN = re.compile(r"\d[\d,]*(?:\.\d+)?")
_YEAR_MONTH_PATTERN = re.compile(r"^(\d{4})-(0[1-9]|1[0-2])$")

# 근거 값과 문장 속 값을 견줄 때 허용하는 오차.
_TOLERANCE = 0.05


def known_numbers(groups: list[object], year_month: object = None) -> set[float]:
    """집계 항목과 기준 연월에 실제로 있는 수치만 허용 목록으로 만든다.

    `groups`는 `by_verdict`·`by_category`처럼 항목(dict) 리스트를 담은
    리스트들이다. 비율(`share`)은 문장에서 퍼센트로 나오므로 100배 한 값도
    넣는다. 소수 그대로(`3.6`)와 반올림한 정수(`4`) 둘 다 자연스러운 표기라
    함께 허용한다. `year_month`는 정상 `YYYY-MM` 형식일 때만 연도와 월을 허용한다.
    """

    numbers: set[float] = set()
    if isinstance(year_month, str) and (
        year_month_match := _YEAR_MONTH_PATTERN.fullmatch(year_month)
    ):
        numbers.update(float(part) for part in year_month_match.groups())

    for items in groups:
        if not isinstance(items, list):
            continue
        for item in items:
            if not isinstance(item, dict):
                continue
            for key, value in item.items():
                if isinstance(value, bool) or not isinstance(value, int | float):
                    continue
                numbers.add(float(value))
                if key == "share" and 0 <= value <= 1:
                    numbers.update(_percent_forms(value))
    return numbers


def known_percentages(groups: list[object]) -> set[float]:
    """`share`에서 실제로 표현 가능한 퍼센트 값만 모은다."""

    percentages: set[float] = set()
    for items in groups:
        if not isinstance(items, list):
            continue
        for item in items:
            if not isinstance(item, dict):
                continue
            share = item.get("share")
            if isinstance(share, bool) or not isinstance(share, int | float):
                continue
            if 0 <= share <= 1:
                percentages.update(_percent_forms(share))
    return percentages


def _percent_forms(share: int | float) -> set[float]:
    percent = share * 100
    return {float(percent), float(round(percent))}


def has_unverified_number(
    sentence: str, known: set[float], *, known_percentages: set[float]
) -> bool:
    """문장에 등장한 숫자 중 근거에 없는 게 있으면 True다.

    한 자리 정수는 서수 표현에 섞일 수 있어 건너뛰되, 뒤의 공백을 제외한 첫
    문자가 `%`면 비율이므로 반드시 검사한다. 퍼센트는 연·월 같은 일반 숫자와
    값이 같아도 통과하지 않도록 `share`에서 만든 별도 집합과 견준다(E-79 · E-101).
    """

    for match in _NUMBER_PATTERN.finditer(sentence):
        text = match.group().replace(",", "")
        is_percent = sentence[match.end() :].lstrip().startswith("%")
        if "." not in text and len(text) < 2 and not is_percent:
            continue
        value = float(text)
        candidates = known_percentages if is_percent else known
        if not any(abs(value - candidate) < _TOLERANCE for candidate in candidates):
            return True
    return False
