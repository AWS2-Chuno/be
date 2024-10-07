from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Depends, Query
from pydantic import BaseModel
import boto3
from botocore.exceptions import ClientError
from boto3.dynamodb.conditions import Attr, Key
import os
from fastapi.security import OAuth2PasswordBearer
from fastapi.middleware.cors import CORSMiddleware
import uuid
import logging
from datetime import datetime
import requests
import json
from dotenv import load_dotenv


logging.basicConfig(level=logging.INFO)


app = FastAPI()

# .env 파일 로드
#load_dotenv()

logging.basicConfig(level=logging.INFO)

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
S3_BUCKET_NAME_ORG = os.getenv("S3_BUCKET_NAME_ORG")
S3_BUCKET_NAME = os.getenv("S3_BUCKET_NAME")
DYNAMODB_TABLE_NAME = os.getenv("DYNAMODB_TABLE_NAME")
COGNITO_USER_POOL_ID = os.getenv("COGNITO_USER_POOL_ID")
VIDEO_CF= 'https://d5p87gbtmit6i.cloudfront.net/uploads/'




# AWS 클라이언트 설정
s3_client = boto3.client('s3', region_name=AWS_REGION)  # S3 클라이언트
dynamodb_client = boto3.resource('dynamodb', region_name=AWS_REGION)  # DynamoDB 클라이언트
dynamodb_table = dynamodb_client.Table(DYNAMODB_TABLE_NAME)  # DynamoDB 테이블 객체

# Cognito 설정
cognito_client = boto3.client('cognito-idp', region_name=AWS_REGION)

# OAuth2PasswordBearer를 사용하여 토큰을 받기 위한 경로 정의
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

@app.get("/")
def test(token: str = Depends(oauth2_scheme)):
    try:
        # 엑세스 토큰 유효성 검사
        validate_token(token)
        user_name = get_user_name(token)

        return user_name
    except ClientError as e:
        raise HTTPException(status_code=401, detail=str(e))

@app.get("/health")
def health_check():
    return {"status": "ok"}
    
@app.get("/videos/")
async def list_videos(token: str = Depends(oauth2_scheme)):
    """DynamoDB에서 동영상 데이터 목록을 조회합니다."""
    logging.info("DynamoDB에서 동영상 데이터 목록을 조회 시작")
    # 엑세스 토큰 유효성 검사
    validate_token(token)
    
    try:
        response = dynamodb_table.scan(
            ProjectionExpression='id, title, thumbnail_path, uploader, #ts',  # 필요한 필드만 선택
            ExpressionAttributeNames={
                '#ts': 'timestamp'  # timestamp를 매핑
            }
        )

        # 전체 데이터를 메모리에 가져온 후 timestamp 기준으로 정렬
        items = response.get('Items', [])

        # timestamp 기준으로 최신순으로 정렬
        sorted_items = sorted(items, key=lambda x: x['timestamp'], reverse=True)

        return {"items": sorted_items}
    except ClientError as e:
        raise HTTPException(status_code=500, detail=str(e))  # 클라이언트 오류 처리
    
@app.get("/myVideos/")
async def list_my_videos(token: str = Depends(oauth2_scheme)):
    """DynamoDB에서 동영상 데이터 목록을 조회합니다."""
    # 엑세스 토큰 유효성 검사
    validate_token(token)
    user_name = get_user_name(token)

    try:
        # 'uploader'가 user_id와 일치하는 항목을 필터링하여 조회
        response = dynamodb_table.scan(
            FilterExpression=Attr('uploader').eq(user_name),  # uploader가 user_id와 일치하는 항목만 필터링
            ProjectionExpression='id, title, thumbnail_path, uploader, #ts',  # 필요한 필드만 선택
            ExpressionAttributeNames={
                '#ts': 'timestamp'  # timestamp를 매핑
            }
        )
        items = response.get('Items', [])

        # timestamp 기준으로 최신순으로 정렬
        sorted_items = sorted(items, key=lambda x: x['timestamp'], reverse=True)

        return {"items": sorted_items}
    except ClientError as e:
        raise HTTPException(status_code=500, detail=str(e))  # 클라이언트 오류 처리

    
@app.post("/videos/")
def upload_video(file: UploadFile = File(...), title: str = Form(...), description: str = Form(...), token: str = Depends(oauth2_scheme)):
    """S3에 동영상을 업로드하고 메타데이터를 DynamoDB에 저장합니다."""
    logging.info("S3에 동영상을 업로드하고 메타데이터를 DynamoDB에 저장 시작")
    # 엑세스 토큰 유효성 검사
    validate_token(token)
    user_name = get_user_name(token)

    logging.info("엑세스 토큰 유효성 검사 완료")

    # DynamoDB에서 title 중복 체크
    # try:
    #     response = dynamodb_table.scan(
    #         FilterExpression=Attr('title').eq(title)
    #     )
    #     if response['Items']:
    #         raise HTTPException(status_code=400, detail="Title already exists, please choose another title.")
    # except ClientError as e:
    #     logging.info(e)
    #     raise HTTPException(status_code=500, detail=str(e))
    try:
        # S3에 동영상 업로드
        logging.info("S3 동영상 업로드 시작")
        s3_key = f"{uuid.uuid4()}"
        s3_client.upload_fileobj(file.file, S3_BUCKET_NAME_ORG, "uploads/" + s3_key + ".mp4")
        logging.info("S3 동영상 업로드 완료")

        logging.info("DynamoDB에 메타데이터 저장 시작")
        # DynamoDB에 메타데이터 저장
        dynamodb_table.put_item(
            Item={
                'id': s3_key,  # S3 키를 사용하여 비디오 ID 설정
                'title': title,
                'description': description,
                'uploader': user_name,
                'file_path': S3_BUCKET_NAME+'/uploads/'+s3_key+".m3u8",
                'file_url': VIDEO_CF + s3_key + '/' + s3_key +'.m3u8',
                'thumbnail_path': VIDEO_CF + s3_key + '/' + s3_key + "_thumbnail.0000000.jpg",
                'file_path_org': S3_BUCKET_NAME_ORG+'/uploads/'+s3_key+".mp4",
                'timestamp': datetime.utcnow().isoformat()  # ISO 8601 형식으로 저장
            }
        )
        
       
        
        url = "https://hooks.slack.com/services/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"
        data = {
            "text": user_name+" 님이 동영상을 업로드했습니다"
        }
        # Make the POST request
        response = requests.post(url, data=json.dumps(data), headers={'Content-type': 'application/json'})
        
        # Check the response
        if response.status_code == 200:
            print("Message sent successfully!")
        else:
            print(f"Failed to send message: {response.status_code}, {response.text}")
    
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
    user_name = get_user_name(token)
    
    try:
        # DynamoDB에서 메타데이터 가져오기
        response = dynamodb_table.get_item(Key={'id': video_id})
        
        # 메타데이터가 없는 경우 404 오류
        if 'Item' not in response:
            raise HTTPException(status_code=404, detail="Video not found in DynamoDB")

        # uploader가 user_id와 일치하는지 확인
        uploader_id = response['Item'].get('uploader')
        if uploader_id != user_name:
            raise HTTPException(status_code=403, detail="You do not have permission to delete this video.")  # 권한 오류

        # file_path에서 버킷명과 파일명 분리
        file_path_org = response['Item'].get('file_path_org')
        if not file_path_org:
            raise HTTPException(status_code=404, detail="File path not found in metadata")

        # 파일 경로에서 버킷명과 파일명을 분리
        bucket_name_org, file_name = file_path_org.split('/', 1)

        # S3에서 원본 동영상 삭제
        s3_client.delete_object(Bucket=bucket_name_org, Key=file_name)

        # S3 버킷 내 폴더 내 모든 객체 가져오기
        id = response['Item'].get('id')
        if not id:
            raise HTTPException(status_code=404, detail="File path not found in metadata")
        objects_to_delete = s3_client.list_objects_v2(Bucket=S3_BUCKET_NAME, Prefix='uploads/'+id+'/')

        # 폴더 내 객체가 있을 경우 삭제
        if 'Contents' in objects_to_delete:
            delete_keys = [{'Key': obj['Key']} for obj in objects_to_delete['Contents']]

            # 객체 삭제
            response = s3_client.delete_objects(
                Bucket=S3_BUCKET_NAME,
                Delete={
                    'Objects': delete_keys
                }
            )
            print(f"{len(delete_keys)} objects deleted from uploads")
        else:
            print(f"No objects found in uploads")

        # DynamoDB에서 메타데이터 삭제
        dynamodb_table.delete_item(Key={'id': video_id})

        return {"message": "Video deleted successfully!"}  # 성공 메시지 반환
    except ClientError as e:
        raise HTTPException(status_code=500, detail=str(e))  # 클라이언트 오류 처리
    
@app.get("/search/")
async def search_in_dynamodb(category: str, key: str, token: str = Depends(oauth2_scheme)):
    """DynamoDB에서 category에 해당하는 key 값을 검색 (포함하는 문자열 및 대소문자 무시)"""
    # 엑세스 토큰 유효성 검사
    validate_token(token)
    
    try:
        # Scan을 사용하여 모든 항목 검색
        response = dynamodb_table.scan(
            FilterExpression=Attr(category).contains(key),  # category에서 key가 포함된 항목 필터링
            ProjectionExpression='id, title, uploader, #ts',  # 필요한 필드만 선택
            ExpressionAttributeNames={
                '#ts': 'timestamp'  # timestamp를 매핑
            }
        )
        items = response.get('Items', [])

        # timestamp 기준으로 최신순으로 정렬
        sorted_items = sorted(items, key=lambda x: x['timestamp'], reverse=True)

        return {"items": sorted_items}
    except ClientError as e:
        raise HTTPException(status_code=500, detail=str(e))  # 클라이언트 오류 처리


###########################################################################################

# 엑세스 토큰 유효성 검사
def validate_token(token: str):
    try:
         # Cognito에서 토큰 검증
        cognito_client.get_user(
            AccessToken=token
        )
    except ClientError as e:
        raise HTTPException(status_code=401, detail=str(e))
    
# User Name 조회
def get_user_name(token: str):
    try:
        # Cognito에서 토큰 검증
        response = cognito_client.get_user(
            AccessToken=token
        )
        
        # UserAttributes에서 'name' 속성 찾기
        user_attributes = response['UserAttributes']
        for attribute in user_attributes:
            if attribute['Name'] == 'name':
                return attribute['Value']
        
        # 'name' 속성을 찾지 못한 경우
        raise HTTPException(status_code=404, detail="Name attribute not found")
    
    except ClientError as e:
        raise HTTPException(status_code=401, detail=str(e))
