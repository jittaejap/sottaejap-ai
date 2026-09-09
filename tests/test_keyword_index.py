"""BM25 키워드 인덱스가 형태소 분석·점수·순위를 올바르게 계산하는지 확인한다."""

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
