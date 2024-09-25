import os
import pytest
from fastapi.testclient import TestClient
from app import main  # FastAPI 애플리케이션이 정의된 파일 import
from unittest.mock import patch

# FastAPI 클라이언트 생성
client = TestClient(main)

# 환경 변수 설정
os.environ["AWS_REGION"] = "us-west-2"
os.environ["S3_BUCKET_NAME"] = "your-bucket-name"
os.environ["DYNAMODB_TABLE_NAME"] = "your-dynamodb-table"

@pytest.fixture
def mock_s3_client():
    with patch("boto3.client") as mock:
        yield mock

@pytest.fixture
def mock_dynamodb_client():
    with patch("boto3.resource") as mock:
        yield mock

def test_list_videos(mock_s3_client):
    """동영상 목록 조회 테스트"""
    # Mocking S3 list_objects_v2
    mock_s3_client.return_value.list_objects_v2.return_value = {
        'Contents': [{'Key': 'video1.mp4'}, {'Key': 'video2.mp4'}]
    }

    response = client.get("/videos/")
    assert response.status_code == 200  # 응답 코드 확인
    assert response.json() == {"videos": ["video1.mp4", "video2.mp4"]}  # 응답 내용 확인

def test_upload_video(mock_s3_client, mock_dynamodb_client):
    """동영상 업로드 테스트"""
    file_content = b"dummy content"
    response = client.post(
        "/videos/",
        files={"file": ("video.mp4", file_content, "video/mp4")},
        json={"id": "1", "title": "Test Video", "description": "A test video"}
    )

    assert response.status_code == 200  # 응답 코드 확인
    assert response.json() == {"message": "Video uploaded successfully!", "filename": "video.mp4"}  # 응답 내용 확인

def test_get_video_details(mock_dynamodb_client):
    """동영상 상세 조회 테스트"""
    mock_dynamodb_client.return_value.Table.return_value.get_item.return_value = {
        'Item': {'id': '1', 'title': 'Test Video', 'description': 'A test video', 'filename': 'video.mp4'}
    }

    response = client.get("/videos/1")
    assert response.status_code == 200  # 응답 코드 확인
    assert response.json() == {'id': '1', 'title': 'Test Video', 'description': 'A test video', 'filename': 'video.mp4'}  # 응답 내용 확인

def test_delete_video(mock_s3_client, mock_dynamodb_client):
    """동영상 삭제 테스트"""
    mock_dynamodb_client.return_value.Table.return_value.get_item.return_value = {
        'Item': {'id': '1', 'filename': 'video.mp4'}
    }

    response = client.delete("/videos/1")
    assert response.status_code == 200  # 응답 코드 확인
    assert response.json() == {"message": "Video deleted successfully!"}  # 응답 내용 확인

