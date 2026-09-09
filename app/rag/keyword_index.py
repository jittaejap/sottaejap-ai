"""BM25 키워드 검색 인덱스 (하이브리드 검색 프로토타입).

pgvector 코사인 검색만으로는 "적금이란"처럼 짧고 사전적인 질문에서 실패하는
사례가 실측으로 확인됐다 — 코퍼스에 정답 문단이 있어도 임베딩 유사도가
임계값(#28) 근처에서 미묘하게 갈린다. Kiwi로 형태소를 분석해 조사·활용형에
흔들리지 않는 명사·용언 어간만 뽑아 BM25로 매칭하면, 정확한 용어 일치를
훨씬 잘 잡는다 — 특히 "정기적금"처럼 복합어 안에 질문 용어("적금")가 섞여
있는 경우.

`financial_chunks` 테이블은 이 모듈이 만들지 않는다(retriever.py와 같은
제약) — 이미 있는 행을 읽어 메모리에 인덱스를 짓기만 한다. 데모 규모(현재
861개 Chunk) 전제로 인메모리·단일 인스턴스다 — `HighlightServiceImpl` 캐시와
같은 전제(docs/DEVELOPMENT.md §6).
"""

from dataclasses import dataclass

from kiwipiepy import Kiwi
from rank_bm25 import BM25Okapi

# 명사류만 남긴다. 동사·형용사 어간(VV·VA)은 "알려줘"·"정해져"처럼 거의 모든
# 질문에 등장하는 범용 동사까지 끌어들여 BM25 점수를 오염시킨다("파이썬 코딩
# 알려줘"가 "알리다" 어간 하나로 무관한 질문인데도 점수가 크게 나온 사례,
# 실측으로 확인) — 주제를 실제로 구분하는 신호는 명사류뿐이다.
_CONTENT_TAGS = frozenset({"NNG", "NNP", "XR", "SL", "SH"})

# Kiwi는 **첫 사용 때** 만든다. 생성만으로 형태소 모델을 상주 메모리에 올리기
# 때문에, 모듈 import 시점에 만들면 하이브리드를 쓰지 않는 기동(`DATABASE_URL`
# 미설정 · 인덱스 구축 실패)도 그 값을 그대로 문다 — `retriever.py`가 이 모듈을
# 무조건 import하므로 차이가 크다(07 §12: 운영 EC2는 메모리 1.9GiB 한 대다).
#
# 생성 옵션은 메모리 기준으로 골랐다(로컬 실측, `ai` 프로세스 RSS 증가분):
#   Kiwi()                                          +514MB
#   Kiwi(load_typo_dict=False, load_multi_dict=False) +300MB
#   위 + num_workers=1                                +189MB
# 오타 사전은 오타 교정(`typos=`)을 쓸 때만, 다어절 사전은 다어절 표제어를 한
# 토큰으로 묶을 때만 필요하다 — 둘 다 안 쓰고 명사 태그만 보므로 결과는 같다
# (재현 질문 17개 토큰화 결과가 기본 설정과 완전히 동일함을 확인했다).
# `num_workers=1`은 코퍼스 배치 토큰화를 병렬화하지 않아 기동이 약 3초 늘지만,
# 1회성 비용이고 여기서는 상주 메모리가 더 비싼 자원이다.
_kiwi: Kiwi | None = None


def _analyzer() -> Kiwi:
    """형태소 분석기를 지연 생성한다 (이벤트 루프 단일 스레드 전제)."""

    global _kiwi
    if _kiwi is None:
        _kiwi = Kiwi(num_workers=1, load_typo_dict=False, load_multi_dict=False)
    return _kiwi


def tokenize(text: str) -> list[str]:
    """형태소 분석 후 내용어(명사류)만 남긴다."""

    return [token.form for token in _analyzer().tokenize(text) if token.tag in _CONTENT_TAGS]


def _tokenize_all(texts: list[str]) -> list[list[str]]:
    """여러 문서를 한 번에 토큰화한다 — 인덱스 구축 경로 전용."""

    return [
        [token.form for token in tokens if token.tag in _CONTENT_TAGS]
        for tokens in _analyzer().tokenize(texts)
    ]


@dataclass(frozen=True)
class KeywordIndex:
    """청크 전체를 대상으로 미리 만들어 둔 BM25 인덱스."""

    chunk_ids: list[str]
    # 코퍼스가 비면 `BM25Okapi([])`가 평균 문서 길이를 0으로 나눠 죽는다 —
    # 그 경우 아예 만들지 않고 `None`으로 둔다.
    _bm25: BM25Okapi | None

    @classmethod
    def build(cls, rows: list[tuple[str, str]]) -> "KeywordIndex":
        """`(chunk_id, content)` 목록으로 인덱스를 짓는다. 비어 있으면 빈 인덱스."""

        if not rows:
            return cls(chunk_ids=[], _bm25=None)
        chunk_ids = [chunk_id for chunk_id, _ in rows]
        corpus_tokens = [
            tokens or [""] for tokens in _tokenize_all([content for _, content in rows])
        ]
        return cls(chunk_ids=chunk_ids, _bm25=BM25Okapi(corpus_tokens))

    def scores(self, query: str) -> dict[str, float]:
        """전체 코퍼스에 대한 BM25 원점수를 `chunk_id`별로 반환한다.

        질문 용어가 하나도 없는 문서는 0점으로 함께 들어온다 — 순위를 매길
        때는 `rank()`를 쓴다(아래 이유로 0점은 후보가 아니다).
        """

        if self._bm25 is None:
            return {}
        raw = self._bm25.get_scores(tokenize(query))
        return dict(zip(self.chunk_ids, raw, strict=True))

    def rank(self, query: str, top_k: int) -> list[str]:
        """BM25 점수 상위 `top_k`개의 `chunk_id`를 점수 내림차순으로 반환한다.

        **0점(질문 용어가 하나도 없는 문서)은 제외한다.** `scores()`는 코퍼스
        전체를 돌려주므로 그대로 잘라 쓰면 실제 매칭이 1건뿐인 질문에서도
        `top_k`개가 꽉 차서, 나머지가 **테이블 순서**만으로 상위 후보 자리를
        차지한다. 그 목록이 RRF 융합에 들어가면 아무 근거 없는 Chunk가 순위
        가점을 받는다 — 코퍼스 적재 순서에 따라 검색 결과가 흔들린다.
        """

        scored = self.scores(query)
        return [
            chunk_id
            for chunk_id, score in sorted(scored.items(), key=lambda kv: kv[1], reverse=True)[
                :top_k
            ]
            if score > 0
        ]
