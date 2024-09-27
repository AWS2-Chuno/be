# 1. 베이스 이미지 설정
FROM 339712823683.dkr.ecr.ap-northeast-2.amazonaws.com/chuno:20

# 2. 작업 디렉토리 생성
WORKDIR /app

# 3. 요구 사항 파일을 컨테이너에 복사
COPY requirements.txt .

# 4. 필요한 패키지 설치
RUN pip install --no-cache-dir -r requirements.txt

# 5. 애플리케이션 소스 코드를 컨테이너에 복사
COPY . .

# 6. FastAPI 애플리케이션 실행
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]

