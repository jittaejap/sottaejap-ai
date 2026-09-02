"""금융 문서 적재 파이프라인의 로컬 진입점.

현재는 텍스트 추출과 Chunk 확인까지만 수행한다. Embedding/pgVector 저장은 스키마와
Provider가 확정된 뒤 연결한다.
"""

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.rag.chunker import chunk_text


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="금융 문서 Chunk 생성 확인")
    parser.add_argument("document", type=Path, help="UTF-8 텍스트 문서 경로")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    text = args.document.read_text(encoding="utf-8")
    chunks = chunk_text(text)
    print(f"{len(chunks)}개 Chunk를 생성했습니다.")
    print("TODO: Embedding 생성 및 pgVector 저장을 연결하세요.")


if __name__ == "__main__":
    main()
