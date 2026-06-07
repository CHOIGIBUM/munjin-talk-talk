"""Runtime configuration and AWS clients.

환경 변수, 데이터 파일 경로, boto3 client를 한 곳에서 초기화합니다.
Lambda cold start 때 한 번 만들어진 client는 이후 호출에서 재사용됩니다.
"""

import os
from pathlib import Path

import boto3
from botocore.config import Config


# 배포 리전과 AWS 리소스 이름은 SAM template/env에서 주입됩니다.
REGION = os.environ.get("AWS_REGION", "ap-northeast-2")
TABLE_NAME = os.environ.get("SESSIONS_TABLE", "MunjinSessions")
CUSTOM_VOCABULARY = os.environ.get("CUSTOM_VOCABULARY", "")
STRONG_MODEL_ID = os.environ.get("STRONG_MODEL_ID", "apac.amazon.nova-pro-v1:0")
LIGHT_MODEL_ID = os.environ.get("LIGHT_MODEL_ID", "apac.amazon.nova-lite-v1:0")
REVIEWER_MODEL_ID = os.environ.get("REVIEWER_MODEL_ID", STRONG_MODEL_ID)
GUIDE_MODEL_ID = os.environ.get("GUIDE_MODEL_ID", LIGHT_MODEL_ID)
MAX_LLM_TOKENS = int(os.environ.get("MAX_LLM_TOKENS", "1600"))
REVIEW_MAX_TOKENS = int(os.environ.get("REVIEW_MAX_TOKENS", "900"))
GUIDE_MAX_TOKENS = int(os.environ.get("GUIDE_MAX_TOKENS", "900"))
EXTRACTION_RETRY_ATTEMPTS = int(os.environ.get("EXTRACTION_RETRY_ATTEMPTS", "3"))
REVIEW_RETRY_ATTEMPTS = int(os.environ.get("REVIEW_RETRY_ATTEMPTS", "2"))

# IR 검색에 필요한 원천 데이터와 사전 계산된 Titan embedding 파일 위치입니다.
DATA_DIR = Path(__file__).resolve().parent / "data"
DISEASES_PATH = DATA_DIR / "diseases_cleaned.json"
SYMPTOM_INDEX_PATH = DATA_DIR / "symptom_index.json"
EMBEDDING_MODEL_ID = os.environ.get("EMBEDDING_MODEL_ID", "amazon.titan-embed-text-v2:0")
EMBEDDING_DIMENSIONS = int(os.environ.get("EMBEDDING_DIMENSIONS", "512"))
HYBRID_TOP_K = int(os.environ.get("HYBRID_TOP_K", "5"))
HYBRID_CANDIDATE_K = int(os.environ.get("HYBRID_CANDIDATE_K", "24"))
HYBRID_ACCEPT_THRESHOLD = float(os.environ.get("HYBRID_ACCEPT_THRESHOLD", "0.18"))
HYBRID_BM25_WEIGHT = float(os.environ.get("HYBRID_BM25_WEIGHT", "0.35"))
HYBRID_VECTOR_WEIGHT = float(os.environ.get("HYBRID_VECTOR_WEIGHT", "0.65"))
HYBRID_MIN_VECTOR_SCORE = float(os.environ.get("HYBRID_MIN_VECTOR_SCORE", "0.12"))
HYBRID_MIN_BM25_SCORE = float(os.environ.get("HYBRID_MIN_BM25_SCORE", "0.04"))
HYBRID_MIN_LABEL_SCORE = float(os.environ.get("HYBRID_MIN_LABEL_SCORE", "0.55"))
EMBEDDING_CACHE_PATH = DATA_DIR / f"symptom_embeddings_{EMBEDDING_MODEL_ID.replace(':', '_').replace('/', '_')}_{EMBEDDING_DIMENSIONS}.json"

# boto3 client/resource는 모듈 전역에 두어 Lambda warm invocation에서 재사용합니다.
ddb = boto3.resource("dynamodb", region_name=REGION)
table = ddb.Table(TABLE_NAME)
bedrock_runtime = boto3.client(
    "bedrock-runtime",
    region_name=REGION,
    config=Config(connect_timeout=5, read_timeout=50, retries={"max_attempts": 2, "mode": "standard"}),
)
