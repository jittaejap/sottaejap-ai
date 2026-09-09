"""회고 추출 품질을 실제 LLM으로 재는 평가 도구 (A6 · #39).

`pytest`는 `FakeLLM`을 쓰므로 "코드가 LLM 응답을 잘 다루는가"만 본다. 이 스크립트는
그 반대편, **"LLM이 애초에 맞게 뽑는가"** 를 잰다. 실제 OpenAI를 부르므로 `tests/`가
아니라 `scripts/`에 둔다 (AGENTS.md — 테스트는 외부를 부르지 않는다).

프롬프트를 고치기 **전과 후에 같은 세트를 돌려 차이를 본다.** 절대 점수는 모델 판이
바뀌면 흔들리므로 주장하지 않는다.

두 가지를 함께 잰다. 한쪽만 보면 반대쪽이 조용히 망가진다.

- **재현율** — 문장에 분명히 있는 값을 뽑아냈는가
- **과잉추론** — 문장에 없는 값을 지어냈는가 (**0이어야 한다**)

과잉추론이 왜 더 위험한가: server `RetrospectChatSupport.nextStep()`은 값이 차 있으면
그 단계를 묻지 않는다. 지어낸 값은 화면에 한 번 잘못 뜨는 정도가 아니라 **되묻기 자체를
없애고** 묶음 키(02 FR-05-02)에 그대로 저장된다. 반면 `null`은 되묻기 한 번을 더 만들
뿐이다 (FR-04-08).

실행:

    OPENAI_API_KEY=... python scripts/eval_reflection_extraction.py
    OPENAI_API_KEY=... python scripts/eval_reflection_extraction.py --repeat 3
"""

import argparse
import asyncio
import sys
import time
from pathlib import Path
from typing import NamedTuple

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.core.config import get_settings  # noqa: E402
from app.reflection.extractor import ReflectionExtractor  # noqa: E402
from app.reflection.schemas import ReflectionExtraction  # noqa: E402

_FIELDS = ("purpose", "companion", "satisfaction", "repeat_intention")


class Case(NamedTuple):
    """평가 문장 하나와 네 항목의 기대값.

    ``None``(satisfaction은 ``"UNKNOWN"``)은 **미확정이어야 한다**는 뜻이다. 값이
    나오면 과잉추론 1건이다. 값을 적은 항목은 재현율 분모에 들어간다.

    기대값이 사람마다 갈릴 문장은 세트에 넣지 않았다. 정본(01 §2 · 02 FR-04-04·05)에
    태그 **정의**가 없어서, 애매한 문장에 기대값을 붙이면 그 라벨이 곧 정의가 되어
    버린다. 여기 있는 문장은 한국어 화자면 대체로 같게 읽을 것만 골랐다.
    """

    text: str
    purpose: str | None = None
    companion: str | None = None
    satisfaction: str = "UNKNOWN"
    repeat_intention: bool | None = None
    last_question: str = ""


# --- 추출형 — 값이 문장에 분명히 있다. 뽑아내야 한다 -------------------------------

_EXTRACTABLE: tuple[Case, ...] = (
    Case("이 소비는 별로였어요", satisfaction="LOW"),
    Case("돈이 하나도 안 아까웠어요. 아주 만족해요", satisfaction="HIGH"),
    Case("혼자 밥 먹었어요", purpose="식사", companion="혼자"),
    Case("가족들이랑 저녁 먹었어요", purpose="식사", companion="가족"),
    Case("친구들 만나려고 카페에서 모였어요", purpose="만남·사교", companion="친구"),
    Case("회사 동료들이랑 회식했어요", purpose="만남·사교", companion="동료"),
    # "영화 봤어요"만으로는 휴식·취미와 만남·사교가 갈려서, 목적을 말한 문장으로 바꿨다.
    Case("퇴근하고 쉬려고 혼자 영화 봤어요", purpose="휴식·취미", companion="혼자"),
    Case("연인이랑 같이 갔어요", companion="연인"),
    Case("혼자 인터넷 강의를 결제했어요", purpose="자기계발", companion="혼자"),
    Case("치약이랑 세제가 떨어져서 샀어요", purpose="필수품"),
    Case("부모님이랑 마트에서 생필품 장 봤어요", purpose="필수품", companion="가족"),
    Case("세일한다길래 계획에 없던 걸 홧김에 질렀어요", purpose="충동"),
    Case("다음에도 또 살 것 같아요", repeat_intention=True),
    Case("이건 다신 안 살래요", repeat_intention=False),
    Case("만족했고 다음에도 또 갈 거예요", satisfaction="HIGH", repeat_intention=True),
    # 직전 질문을 해석 힌트로 써야 답이 되는 짧은 답변.
    Case("혼자요", companion="혼자", last_question="누구와 함께한 소비였나요?"),
    Case(
        "아니요",
        repeat_intention=False,
        last_question="다음에도 비슷한 소비를 하실 것 같나요?",
    ),
)


# --- 과잉추론형 — 값이 문장에 없다. 전부 미확정이어야 한다 -------------------------

_OVER_INFERENCE: tuple[Case, ...] = (
    # 동행인을 말한 적이 없다. "혼자"로 채우면 COMPANION 단계가 사라진다.
    # "먹었어요"는 목적을 말한 것이므로 purpose=식사는 과잉추론이 아니다.
    Case("그냥 배달 시켜 먹었어요", purpose="식사"),
    Case("편의점에 잠깐 들렀어요"),
    # "친구"가 문장에 있지만 같이 갔다는 말은 없다.
    Case("친구가 추천해준 가게였어요"),
    # "회사"가 있지만 동료와 함께였다는 말은 없다.
    Case("회사 근처에서 샀어요"),
    # 다짐이지 반복 의향에 대한 답이 아니다.
    Case("앞으로는 좀 줄여야겠어요"),
    # "모르겠다"를 "기타"로 바꿔 담으면 안 된다 (기타 ≠ 모르겠음).
    Case("잘 모르겠어요"),
    Case("글쎄요, 기억이 잘 안 나요"),
    # 만족도가 애매하다. FR-04-03의 "잘 모르겠어요"에 해당한다.
    Case("그냥 그랬어요"),
    # 시간·금액만 있다.
    Case("어제 저녁쯤에 썼어요"),
    Case("만 이천 원이었어요"),
    # 질문에 등장한 값이 답으로 새면 안 된다.
    Case("아직 잘 모르겠어요", last_question="누구와 함께한 소비였나요?"),
    Case("음... 글쎄요", last_question="어떤 목적의 소비였나요? 아래에서 골라 주세요."),
)

CASES: tuple[Case, ...] = _EXTRACTABLE + _OVER_INFERENCE


class Result(NamedTuple):
    """한 문장의 채점 결과."""

    case: Case
    hits: int  # 값이 있어야 하고 맞은 항목 수
    wanted: int  # 값이 있어야 하는 항목 수
    misses: list[str]  # 못 뽑았거나 다르게 뽑은 항목
    over: list[str]  # 미확정이어야 하는데 값이 찬 항목


def grade(case: Case, got: ReflectionExtraction) -> Result:
    """기대값과 대조한다. 항목 단위로 재현율과 과잉추론을 함께 센다."""

    hits = wanted = 0
    misses: list[str] = []
    over: list[str] = []

    for field in _FIELDS:
        expected = getattr(case, field)
        actual = getattr(got, field)
        actual = actual.value if hasattr(actual, "value") else actual
        unset = "UNKNOWN" if field == "satisfaction" else None

        if expected == unset:
            if actual != unset:
                over.append(f"{field}={actual!r}")
            continue

        wanted += 1
        if actual == expected:
            hits += 1
        else:
            misses.append(f"{field}={actual!r} (기대 {expected!r})")

    return Result(case, hits, wanted, misses, over)


async def _run_case(extractor: ReflectionExtractor, case: Case) -> Result | BaseException:
    try:
        turn = await extractor.extract(case.text, case.last_question)
    except BaseException as error:  # noqa: BLE001 — 한 문장 실패로 전체를 멈추지 않는다
        return error
    return grade(case, turn.extraction)


async def run_once(extractor: ReflectionExtractor) -> tuple[list[Result], list[BaseException], float]:
    """세트 전체를 한 번 돌린다. 지연도 함께 잰다 (NFR-04 6초 예산 참고용)."""

    started = time.perf_counter()
    graded = await asyncio.gather(*(_run_case(extractor, case) for case in CASES))
    elapsed = time.perf_counter() - started

    results = [item for item in graded if isinstance(item, Result)]
    errors = [item for item in graded if isinstance(item, BaseException)]
    return results, errors, elapsed


def report(results: list[Result], errors: list[BaseException], elapsed: float) -> bool:
    """실측치를 찍고 과잉추론이 0인지 돌려준다."""

    hits = sum(result.hits for result in results)
    wanted = sum(result.wanted for result in results)
    over = sum(len(result.over) for result in results)
    # 미확정이어야 하는 항목 수 = 전체 항목 - 값이 있어야 하는 항목
    nullable = len(results) * len(_FIELDS) - wanted

    for result in results:
        if not result.misses and not result.over:
            continue
        print(f'  [{"과잉추론" if result.over else "미달"}] "{result.case.text}"')
        for note in result.misses:
            print(f"      과소·오분류  {note}")
        for note in result.over:
            print(f"      지어냄       {note}")

    for error in errors:
        print(f"  [오류] {type(error).__name__}: {error}")

    recall = f"{hits}/{wanted}" + (f" ({hits / wanted:.1%})" if wanted else "")
    print()
    print(f"  문장         {len(results)}개 (오류 {len(errors)}개)")
    print(f"  재현율       {recall}")
    print(f"  과잉추론     {over}/{nullable} 항목   {'OK' if over == 0 else '← 0이어야 한다'}")
    print(f"  소요         {elapsed:.1f}초 (동시 실행)")
    return over == 0 and not errors


async def main() -> int:
    parser = argparse.ArgumentParser(description="회고 추출 품질 평가 (A6)")
    parser.add_argument(
        "--repeat",
        type=int,
        default=1,
        help="같은 세트를 몇 번 돌릴지. LLM 응답이 흔들리는 폭을 볼 때 2 이상을 준다",
    )
    args = parser.parse_args()

    if not get_settings().openai_api_key:
        print("OPENAI_API_KEY가 없습니다. 이 스크립트는 실제 LLM을 부릅니다.", file=sys.stderr)
        return 2

    extractor = ReflectionExtractor()
    clean = True
    for round_number in range(1, args.repeat + 1):
        print(f"\n=== {round_number}회차 ===")
        clean &= report(*await run_once(extractor))
    return 0 if clean else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
