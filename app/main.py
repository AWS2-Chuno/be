from fastapi import FastAPI, UploadFile, File, HTTPException
from pydantic import BaseModel
import boto3
from botocore.exceptions import ClientError
import os
from dotenv import load_dotenv

app = FastAPI()


# .env 파일에서 환경변수를 로드
load_dotenv()


# AWS 리전, S3 버킷 이름, DynamoDB 테이블 이름 환경 변수에서 가져오기
AWS_REGION = os.getenv("AWS_REGION")
S3_BUCKET = os.getenv("S3_BUCKET_NAME")
DYNAMODB_TABLE_NAME = os.getenv("DYNAMODB_TABLE_NAME")

# AWS 클라이언트 설정
s3_client = boto3.client('s3', region_name=AWS_REGION)  # S3 클라이언트
dynamodb_client = boto3.resource('dynamodb', region_name=AWS_REGION)  # DynamoDB 클라이언트
dynamodb_table = dynamodb_client.Table(DYNAMODB_TABLE_NAME)  # DynamoDB 테이블 객체

# 동영상 메타데이터를 위한 Pydantic 모델
class VideoMetadata(BaseModel):
    id: str
    title: str
    registerdddddddddd: str
    description: str
    thumbnailx: str



@app.get("/")
def test():
    return "Success"

    
@app.get("/videos/")
async def list_videos():
    """S3에서 동영상 목록을 조회합니다."""
    try:
        response = s3_client.list_objects_v2(Bucket=S3_BUCKET)  # S3에서 객체 목록 조회
        videos = [obj['Key'] for obj in response.get('Contents', [])]  # 객체 키 목록 생성
        return {"videos": videos}  # 동영상 목록 반환
    except ClientError as e:
        raise HTTPException(status_code=500, detail=str(e))  # 클라이언트 오류 처리

@app.post("/videos/")
async def upload_video(file: UploadFile = File(...)):
    """S3에 동영상을 업로드하고 메타데이터를 DynamoDB에 저장합니다."""
    try:
        # S3에 동영상 업로드
        s3_client.upload_fileobj(file.file, S3_BUCKET, file.filename)

        # DynamoDB에 메타데이터 저장
        dynamodb_table.put_item(
            Item={
                'id': metadata.id,
                'title': metadata.title,
                'description': metadata.description,
                'filename': file.filename  # S3에 업로드한 파일 이름
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

