import pytest
import asyncio
from fastapi.testclient import TestClient
from main import app
from tachyon.core.database import init_db

@pytest.fixture(scope="module", autouse=True)
def setup_test_db():
    asyncio.run(init_db())

client = TestClient(app)

def test_health_check():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "quantum_stable"

def test_api_status():
    response = client.get("/api/v1/status")
    assert response.status_code == 200
    assert response.json()["module"] == "tachyon.api"

def test_upload_placeholder():
    files = {'file': ('test.txt', b'hello world')}
    response = client.post("/api/v1/upload", files=files)
    assert response.status_code == 200
    assert response.json()["status"] == "uploaded"
