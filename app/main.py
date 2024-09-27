from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Depends
from pydantic import BaseModel
import boto3
from botocore.exceptions import ClientError
import os
from fastapi.security import OAuth2PasswordBearer
import uuid

from dotenv import load_dotenv

app = FastAPI()


# .env 파일 로드
load_dotenv()


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
#COGNITO_USER_POOL_ID = 'ap-northeast-3_Rt1SkOGagd'  # 사용자 풀 ID
cognito_client = boto3.client('cognito-idp', region_name=AWS_REGION)

# OAuth2PasswordBearer를 사용하여 토큰을 받기 위한 경로를 정의합니다.
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

@app.get("/")
def test(token: str = Depends(oauth2_scheme)):
    try:
        # Cognito에서 토큰 검증
        response = cognito_client.get_user(
            AccessToken=token
        )
        
        # 사용자 ID 반환
        user_id = response['Username']  # Username은 기본적으로 사용자의 ID입니다.
        return user_id
    except ClientError as e:
        raise HTTPException(status_code=401, detail=str(e))

    
@app.get("/videos/")
async def list_videos():
    """DynamoDB에서 동영상 데이터 목록을 조회합니다."""
    try:
        response = dynamodb_table.scan(ProjectionExpression='id, title')  # 항목 조회 (단, 큰 테이블에서는 성능 문제 발생 가능)
        items = response.get('Items', [])
        return {"items": items}
    except ClientError as e:
        raise HTTPException(status_code=500, detail=str(e))  # 클라이언트 오류 처리

@app.post("/videos/")
async def upload_video(file: UploadFile = File(...), title: str = Form(...), description: str = Form(...)):
    """S3에 동영상을 업로드하고 메타데이터를 DynamoDB에 저장합니다."""
    try:
        # S3에 동영상 업로드
        s3_key = f"videos/{uuid.uuid4()}.mp4"
        s3_client.upload_fileobj(file.file, S3_BUCKET, s3_key)

        # DynamoDB에 메타데이터 저장
        #metadata = VideoMetadata(title=title, description=description)
        dynamodb_table.put_item(
            Item={
                'id': s3_key,  # S3 키를 사용하여 비디오 ID 설정
                'title': title,
                'description': description
            }
        )
        return {"message": "Video uploaded successfully!", "filename": file.filename}  # 성공 메시지 반환
    except ClientError as e:
        raise HTTPException(status_code=500, detail=str(e))  # 클라이언트 오류 처리

@app.get("/videos/{video_id}")
async def get_video_details(video_id: str):
    """DynamoDB에서 동영상 메타데이터를 조회합니다."""
    try:
        response = dynamodb_table.get_item(Key={'id': video_id})  # DynamoDB에서 동영상 메타데이터 조회
        if 'Item' not in response:
            raise HTTPException(status_code=404, detail="Video not found")  # 동영상이 없는 경우 404 오류

        return response['Item']  # 동영상 메타데이터 반환
    except ClientError as e:
        raise HTTPException(status_code=500, detail=str(e))  # 클라이언트 오류 처리

@app.delete("/videos/{video_id}")
async def delete_video(video_id: str):
    """S3에서 동영상을 삭제하고 DynamoDB에서 메타데이터를 제거합니다."""
    try:
        # DynamoDB에서 메타데이터 삭제
        response = dynamodb_table.get_item(Key={'id': video_id})
        if 'Item' not in response:
            raise HTTPException(status_code=404, detail="Video not found in DynamoDB")  # 메타데이터가 없는 경우 404 오류

        # S3에서 동영상 삭제
        s3_client.delete_object(Bucket=S3_BUCKET, Key=response['Item']['filename'])

        # DynamoDB에서 메타데이터 삭제
        dynamodb_table.delete_item(Key={'id': video_id})

        return {"message": "Video deleted successfully!"}  # 성공 메시지 반환
    except ClientError as e:
        raise HTTPException(status_code=500, detail=str(e))  # 클라이언트 오류 처리

