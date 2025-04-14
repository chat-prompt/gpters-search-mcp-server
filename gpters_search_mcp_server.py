"""
MCP 서버 - GPTers AI 스터디 커뮤니티 검색 기능 (JWT 인증 방식)

Lambda API 호출 시 JWT 인증을 사용합니다.
"""

# 표준 라이브러리
import logging
import os
from datetime import datetime
import tzlocal

# 서드파티 라이브러리
from dotenv import load_dotenv
import httpx
from mcp.server.fastmcp import FastMCP

# .env 파일에서 환경 변수를 로드합니다.
load_dotenv()


# 로깅 설정을 구성합니다.
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
# 이 모듈에 대한 로거를 생성합니다.
logger = logging.getLogger("gpters-search-mcp")

# 특정 이름으로 FastMCP 서버를 초기화합니다.
mcp = FastMCP("gpters-search-mcp")

# 환경 변수에서 로그인 및 검색 엔드포인트 URL을 설정합니다.
LOGIN_URL = os.getenv("LOGIN_URL")
SEARCH_URL = os.getenv("SEARCH_URL")
API_SECRET_KEY = os.getenv("API_SECRET_KEY")

# JWT 토큰 캐시
_jwt_token = None

# JWT 토큰을 가져오는 함수
async def get_jwt_token() -> str:
    """
    JWT 토큰을 가져오는 비동기 함수입니다.

    Returns:
        str: 유효한 JWT 토큰을 반환합니다. 만약 캐시된 토큰이 있다면 이를 반환하고,
        그렇지 않으면 새로운 토큰을 요청하여 반환합니다.

    Raises:
        Exception: 로그인 실패 시 예외를 발생시킵니다.
    """
    global _jwt_token

    # 캐시된 토큰이 있으면 반환합니다.
    if _jwt_token:
        return _jwt_token

    try:
        # 비동기 HTTP 클라이언트를 생성합니다.
        async with httpx.AsyncClient() as client:
            # API 키를 사용하여 로그인 URL로 POST 요청을 보냅니다.
            response = await client.post(
                LOGIN_URL,
                headers={"x-api-key": API_SECRET_KEY},
                timeout=10.0
            )
            # 응답이 성공적인지 확인합니다.
            if response.status_code != 200:
                logger.error(f"JWT 로그인 실패: {response.status_code} - {response.text}")
                raise Exception("로그인 실패")
            
            # JSON 응답을 파싱하여 토큰을 가져옵니다.
            data = response.json()
            _jwt_token = data["token"]
            return _jwt_token

    except Exception as e:
        logger.error(f"JWT 발급 중 오류: {str(e)}")
        raise

def to_local_timestr_with_tzname(timestamp: int) -> str:
    """
    유닉스 타임스탬프를 로컬 타임존의 이름과 오프셋을 포함한 문자열로 변환합니다.

    Args:
        timestamp (int): 유닉스 타임스탬프 (초 단위)

    Returns:
        str: 'YYYY-MM-DDThh:mm:ss TZ±hhmm' 형식의 날짜/시간 문자열
             예: '2023-10-11T20:57:04 KST+0900'

    Note:
        - TZ는 타임존의 약자 (예: KST, UTC)
        - ±hhmm은 UTC 기준 오프셋 (예: +0900, -0500)
    """
    local_tz = tzlocal.get_localzone()
    dt = datetime.fromtimestamp(timestamp, tz=local_tz)
    return dt.strftime("%Y-%m-%dT%H:%M:%S %Z%z")  # 예: "2023-10-11T20:57:04 KST+0900"

# GPTers AI 스터디 커뮤니티 지식을 검색하는 도구를 정의합니다.
@mcp.tool()
async def search_gpters(query: str, top_k: int = 5, space_name: str = None, owner_name: str = None, created_within_days: int = None) -> str:
    """
    GPTers AI 스터디 커뮤니티의 지식을 검색합니다.
    
    Args:
        query (str): 검색 쿼리
        top_k (int): 반환할 결과 수 (기본값: 5)
        space_name (str): 게시판 이름 (선택 사항)
        owner_name (str): 작성자 이름 (선택 사항)
        created_within_days (int): 작성일 기준 일수 (선택 사항), 예: 최근 30일 이내 검색
    Returns:
        str: 검색 결과를 포맷팅한 문자열
    """
    try:
        logger.info(f"검색 요청: query='{query}', top_k={top_k}")
        # JWT 토큰을 가져옵니다.
        token = await get_jwt_token()

        # 비동기 HTTP 클라이언트를 생성합니다.
        async with httpx.AsyncClient() as client:
            # 쿼리와 토큰을 사용하여 검색 URL로 POST 요청을 보냅니다.
            response = await client.post(
                SEARCH_URL,
                json={"query": query, "top_k": top_k, "space_name": space_name, "owner_name": owner_name, "created_within_days": created_within_days},
                headers={
                    "x-api-key": API_SECRET_KEY,
                    "Authorization": f"Bearer {token}"
                },
                timeout=30.0
            )

            # 토큰 만료 또는 유효하지 않은 경우 처리합니다.
            if response.status_code == 401:
                logger.warning("JWT 만료 또는 유효하지 않음. 토큰 갱신 후 재시도.")
                # 토큰을 초기화하고 재시도합니다.
                global _jwt_token
                _jwt_token = None
                return await search_gpters(query, top_k, space_name, owner_name, created_within_days)

            # 응답이 성공적인지 확인합니다.
            if response.status_code != 200:
                logger.error(f"API 오류: status={response.status_code}, response={response.text}")
                return f"검색 중 오류가 발생했습니다: 서버 응답 코드 {response.status_code}"

            # JSON 응답을 파싱하여 검색 결과를 가져옵니다.
            data = response.json()
            if 'message' in data:
                logger.info("검색 결과 없음")
                return data['message']

            # 검색 결과를 포맷팅합니다.
            results = []
            for doc in data['results']:
                results.append(f"""
제목: {doc['title']}
내용: {doc['text']}
작성자: {doc['owner_name']}
게시판: {doc['space_name']}
태그: {doc['tags']}
작성일: {to_local_timestr_with_tzname(doc['created_at'])}
URL: {doc['url']}
관련도: {doc['score']:.2f}
원본 관련도: {doc['original_score']:.2f}
시간 가중치(오래될수록 더 낮음): {doc['recency_weight']:.2f}
""")
            return "\n---\n".join(results)

    except Exception as e:
        logger.error(f"검색 오류: {str(e)}")
        return f"검색 중 오류가 발생했습니다: {str(e)}"

# 이 스크립트가 직접 실행될 경우 서버를 시작합니다.
if __name__ == "__main__":
    logger.info("GPTers AI 스터디 커뮤니티 MCP 서버 시작")
    mcp.run(transport='stdio')
