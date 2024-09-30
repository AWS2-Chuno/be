from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Depends
from pydantic import BaseModel
import boto3
from botocore.exceptions import ClientError
import os
from fastapi.security import OAuth2PasswordBearer
from fastapi.middleware.cors import CORSMiddleware
import uuid

from dotenv import load_dotenv

app = FastAPI()


# .env 파일 로드
load_dotenv()

# CORS 설정
origins = [
    #"https://d1otwmssn5i115.cloudfront.net"    # 도메인
    "*"    # 도메인
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,  # 허용할 오리진 목록
    allow_credentials=True,
    allow_methods=["*"],     # 허용할 HTTP 메서드 (GET, POST 등)
    allow_headers=["*"],     # 허용할 HTTP 헤더
)

# AWS 리전, S3 버킷 이름, DynamoDB 테이블 이름 환경 변수에서 가져오기
AWS_REGION = os.getenv("AWS_REGION")
S3_BUCKET = os.getenv("S3_BUCKET_NAME")
DYNAMODB_TABLE_NAME = os.getenv("DYNAMODB_TABLE_NAME")
COGNITO_USER_POOL_ID = os.getenv("COGNITO_USER_POOL_ID")

# AWS 클라이언트 설정
s3_client = boto3.client('s3', region_name=AWS_REGION)  # S3 클라이언트
dynamodb_client = boto3.resource('dynamodb', region_name=AWS_REGION)  # DynamoDB 클라이언트
dynamodb_table = dynamodb_client.Table(DYNAMODB_TABLE_NAME)  # DynamoDB 테이블 객체

# Cognito 설정
cognito_client = boto3.client('cognito-idp', region_name=AWS_REGION)

# OAuth2PasswordBearer를 사용하여 토큰을 받기 위한 경로를 정의합니다.
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

# 엑세스 토큰 유효성 검사
def validate_token(token: str):
    try:
         # Cognito에서 토큰 검증
        cognito_client.get_user(
            AccessToken=token
        )
    except ClientError as e:
        raise HTTPException(status_code=401, detail=str(e))
    
# User ID 조회
def get_user_id(token: str):
    try:
         # Cognito에서 토큰 검증
        response = cognito_client.get_user(
            AccessToken=token
        )
        
        # 사용자 ID 반환
        user_id = response['Username']  # Username은 기본적으로 사용자의 ID
        return user_id
    except ClientError as e:
        raise HTTPException(status_code=401, detail=str(e))
    

@app.get("/")
def test(token: str = Depends(oauth2_scheme)):
    try:
        # 엑세스 토큰 유효성 검사
        validate_token(token)
        user_id = get_user_id(token)

        return user_id
    except ClientError as e:
        raise HTTPException(status_code=401, detail=str(e))

    
@app.get("/videos/")
async def list_videos(token: str = Depends(oauth2_scheme)):
    """DynamoDB에서 동영상 데이터 목록을 조회합니다."""
    # 엑세스 토큰 유효성 검사
    validate_token(token)
    
    try:
        response = dynamodb_table.scan(ProjectionExpression='id, title')  # 항목 조회 (단, 큰 테이블에서는 성능 문제 발생 가능)
        items = response.get('Items', [])
        return {"items": items}
    except ClientError as e:
        raise HTTPException(status_code=500, detail=str(e))  # 클라이언트 오류 처리

@app.post("/videos/")
async def upload_video(file: UploadFile = File(...), title: str = Form(...), description: str = Form(...), token: str = Depends(oauth2_scheme)):
    """S3에 동영상을 업로드하고 메타데이터를 DynamoDB에 저장합니다."""
    # 엑세스 토큰 유효성 검사
    validate_token(token)
    user_id = get_user_id(token)
    try:
        # S3에 동영상 업로드
        s3_key = f"{uuid.uuid4()}"
        s3_client.upload_fileobj(file.file, S3_BUCKET, s3_key + ".mp4")

        # DynamoDB에 메타데이터 저장
        dynamodb_table.put_item(
            Item={
                'id': s3_key,  # S3 키를 사용하여 비디오 ID 설정
                'title': title,
                'description': description,
                'uploader': user_id,
                'file_path': S3_BUCKET+s3_key+".mp4",
                'file_path_org': S3_BUCKET+s3_key+".mp4"
            }
        )
        return {"message": "Video uploaded successfully!", "filename": file.filename}  # 성공 메시지 반환
    except ClientError as e:
        raise HTTPException(status_code=500, detail=str(e))  # 클라이언트 오류 처리

@app.get("/videos/{video_id}")
async def get_video_details(video_id: str, token: str = Depends(oauth2_scheme)):
    """DynamoDB에서 동영상 메타데이터를 조회합니다."""
    # 엑세스 토큰 유효성 검사
    validate_token(token)

    try:
        response = dynamodb_table.get_item(Key={'id': video_id})  # DynamoDB에서 동영상 메타데이터 조회
        if 'Item' not in response:
            raise HTTPException(status_code=404, detail="Video not found")  # 동영상이 없는 경우 404 오류

        return response['Item']  # 동영상 메타데이터 반환
    except ClientError as e:
        raise HTTPException(status_code=500, detail=str(e))  # 클라이언트 오류 처리
        
@app.delete("/videos/{video_id}")
async def delete_video(video_id: str, token: str = Depends(oauth2_scheme)):
    """S3에서 동영상을 삭제하고 DynamoDB에서 메타데이터를 제거합니다."""
    # 엑세스 토큰 유효성 검사
    validate_token(token)
    user_id = get_user_id(token)
    
    try:
        # DynamoDB에서 메타데이터 가져오기
        response = dynamodb_table.get_item(Key={'id': video_id})
        
        # 메타데이터가 없는 경우 404 오류
        if 'Item' not in response:
            raise HTTPException(status_code=404, detail="Video not found in DynamoDB")

        # uploader가 user_id와 일치하는지 확인
        uploader_id = response['Item'].get('uploader')
        if uploader_id != user_id:
            raise HTTPException(status_code=403, detail="You do not have permission to delete this video.")  # 권한 오류

        # file_path에서 버킷명과 파일명 분리
        file_path = response['Item'].get('file_path')
        if not file_path:
            raise HTTPException(status_code=404, detail="File path not found in metadata")

        # 파일 경로에서 버킷명과 파일명을 분리
        bucket_name, file_name = file_path.split('/', 1)

        # S3에서 동영상 삭제
        s3_client.delete_object(Bucket=bucket_name, Key=file_name)

        # DynamoDB에서 메타데이터 삭제
        dynamodb_table.delete_item(Key={'id': video_id})

        return {"message": "Video deleted successfully!"}  # 성공 메시지 반환
    except ClientError as e:
        raise HTTPException(status_code=500, detail=str(e))  # 클라이언트 오류 처리
