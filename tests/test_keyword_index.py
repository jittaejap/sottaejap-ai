"""BM25 키워드 인덱스가 형태소 분석·점수·순위를 올바르게 계산하는지 확인한다."""

import subprocess
import sys

from app.rag.keyword_index import KeywordIndex, tokenize


def test_tokenize_keeps_only_noun_like_content_words() -> None:
    """동사 어간(예: "알리다")은 거의 모든 질문에 등장해 BM25 신호를 오염시킨다.

    "파이썬 코딩 알려줘"가 금융 코퍼스와 무관한데도 "알려줘"의 어간 "알리"가
    명사와 같은 취급을 받으면 점수가 크게 나오는 게 실측으로 확인됐다(#78).
    """

    assert tokenize("파이썬 코딩 알려줘") == ["파이썬", "코딩"]
    assert tokenize("적금이란") == ["적금"]


def test_tokenize_splits_compound_nouns() -> None:
    """"정기적금"처럼 복합어 안에 있어도 "적금"을 독립된 명사로 뽑아낸다."""

    assert "적금" in tokenize("정기적금에 가입하다")


def test_build_creates_index_matching_row_order() -> None:
    index = KeywordIndex.build(
        [("c1", "적금은 목돈 마련을 위한 저축 상품이다"), ("c2", "완전히 다른 내용입니다")]
    )

    assert index.chunk_ids == ["c1", "c2"]


def test_scores_ranks_matching_document_higher() -> None:
    # BM25는 어떤 용어가 코퍼스 전체 문서에 다 있으면(IDF가 0에 가까워짐)
    # 구분을 못 한다 — 무관한 문서를 여러 개 둬 "적금"이 일부에만 있게 한다.
    index = KeywordIndex.build(
        [
            ("relevant", "적금 적금 적금 목돈 마련을 위한 상품"),
            ("irrelevant-1", "완전히 다른 주제의 내용입니다"),
            ("irrelevant-2", "이것도 관련 없는 문서입니다"),
            ("irrelevant-3", "역시 상관없는 내용을 담고 있습니다"),
        ]
    )

    scores = index.scores("적금이란")

    assert scores["relevant"] > scores["irrelevant-1"]
    assert scores["irrelevant-1"] == 0.0


def test_rank_returns_top_k_by_score_descending() -> None:
    index = KeywordIndex.build(
        [
            ("a", "복리는 원금과 이자에 이자가 붙는 방식이다"),
            ("b", "적금은 정기적으로 납입하는 저축 상품이다"),
            ("c", "무관한 내용입니다"),
        ]
    )

    assert index.rank("복리란 무엇인가?", top_k=1) == ["a"]


def test_build_with_empty_rows_returns_empty_index() -> None:
    index = KeywordIndex.build([])

    assert index.scores("아무 질문") == {}
    assert index.rank("아무 질문", top_k=5) == []


def test_rank_excludes_chunks_with_zero_score() -> None:
    """질문 용어가 하나도 없는 Chunk는 `top_k`가 남아도 후보에 넣지 않는다.

    `scores()`는 코퍼스 전체를 돌려주므로 그대로 자르면 매칭이 1건뿐인
    질문에서도 `top_k`개가 꽉 찬다 — 나머지는 **적재 순서**로 뽑힌 무근거
    Chunk고, RRF 융합에 들어가면 순위 가점을 받는다(#78 리뷰).
    """

    index = KeywordIndex.build(
        [(f"c{i}", f"금융 문단 {i} 내용") for i in range(20)]
        + [("match", "적금 적금 적금 목돈 마련")]
    )

    assert index.rank("적금이란", top_k=15) == ["match"]


def test_importing_the_app_does_not_load_the_kiwi_model() -> None:
    """모듈을 import하는 것만으로 형태소 모델이 상주 메모리에 올라오면 안 된다.

    `retriever.py`가 이 모듈을 무조건 import하므로, `Kiwi()`가 모듈 최상단으로
    돌아가면 하이브리드를 쓰지 않는 기동(`DATABASE_URL` 미설정 · 인덱스 구축
    실패)까지 모델 값을 그대로 문다 — 실측 `app.main` import 기준 108MB → 416MB
    (#79 리뷰). 운영 EC2가 메모리 1.9GiB 한 대라(07 §12) 조용히 되돌아가면 곤란하다.

    이 세션 안에서는 다른 테스트가 이미 분석기를 만들어 뒀을 수 있어, 깨끗한
    하위 프로세스에서 확인한다.
    """

    probe = (
        "import app.main, app.rag.keyword_index as k; "
        "print('LAZY' if k._kiwi is None else 'EAGER')"
    )
    result = subprocess.run(
        [sys.executable, "-c", probe], capture_output=True, text=True, check=True
    )

    assert result.stdout.strip() == "LAZY", (
        "import만으로 Kiwi가 만들어졌다 — `_analyzer()` 지연 생성이 풀렸는지 확인할 것"
    )
