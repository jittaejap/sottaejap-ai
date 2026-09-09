"""FINANCIAL_RAG_PROMPT이 근거 수치는 보존하고 메타데이터만 느슨하게 하는지 확인한다."""

from app.rag.prompt import FINANCIAL_RAG_PROMPT


def test_prompt_does_not_forbid_evidence_numbers() -> None:
    """금융 질문의 답은 대부분 수치라, 수치 자체를 옮기지 말라고 하면 안 된다."""

    assert "수치를 그대로 옮기지" not in FINANCIAL_RAG_PROMPT
    assert "수치와 조건은 그대로 전달" in FINANCIAL_RAG_PROMPT


def test_prompt_loosens_only_document_metadata() -> None:
    """변환 과정에서 깨지기 쉬운 문서명·발행연도만 느슨하게 언급하도록 한다."""

    assert "문서명·발행연도는 단정하지" in FINANCIAL_RAG_PROMPT
    assert "느슨하게 언급" in FINANCIAL_RAG_PROMPT


def test_prompt_forbids_investment_advice() -> None:
    assert "투자 권유" in FINANCIAL_RAG_PROMPT


def test_prompt_follows_nfr09_length_rule() -> None:
    """02 NFR-09 · 01 E-90의 "한두 문장의 한 문단" 규칙과 같은 문구를 써야 한다."""

    assert "한두 문장" in FINANCIAL_RAG_PROMPT
    assert "세 문장" not in FINANCIAL_RAG_PROMPT
