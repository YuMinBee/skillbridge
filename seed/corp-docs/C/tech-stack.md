# 한빛AI랩(가상) 서비스 구조

문서 검색 서비스는 Amazon Bedrock의 LLM과 RAG 구조로 동작합니다.
인프라는 AWS를 쓰고, API 서버는 Docker로 배포합니다.
사용 로그는 SQL로 분석하고, 모델·프롬프트 버전은 MLOps 방식으로 관리합니다.
