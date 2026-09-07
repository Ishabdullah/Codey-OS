import os
import pytest
import io

from restoricon_core.api.server import RestoriconAPIServer

# We can mock the HTTP server environment to test the router directly.
class MockRFile:
    def __init__(self, data: bytes):
        self._f = io.BytesIO(data)
        
    def read(self, size: int = -1) -> bytes:
        return self._f.read(size)

import uuid

@pytest.fixture
def server_app():
    db_path = f"file:test_doc_upload_{uuid.uuid4()}?mode=memory&cache=shared"
    server = RestoriconAPIServer(db_path=db_path, host="127.0.0.1", port=0)
    
    user = server.auth_service.create_user(
        username="admin",
        plain_password="password",
        full_name="Admin",
        email="admin@test.com",
        role="admin"
    )
    server.db.get_connection().commit()
    
    server._test_user = user
    yield server
    server.db.close()

def test_document_streaming_upload(server_app):
    token = server_app.auth_service.create_token(server_app._test_user)
    
    # Let's create a multipart body
    boundary = "----WebKitFormBoundary7MA4YWxkTrZu0gW"
    
    # We want to upload a .txt file
    file_content = b"This is a test file content." * 10
    
    body_str = (
        f"--{boundary}\r\n"
        f"Content-Disposition: form-data; name=\"document_type\"\r\n\r\n"
        f"invoice\r\n"
        f"--{boundary}\r\n"
        f"Content-Disposition: form-data; name=\"file\"; filename=\"test_upload.txt\"\r\n"
        f"Content-Type: text/plain\r\n\r\n"
    ).encode() + file_content + f"\r\n--{boundary}--\r\n".encode()

    rfile = MockRFile(body_str)
    
    status, headers, resp_body = server_app.router.handle_request(
        method="POST",
        path_with_query="/api/v1/documents",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": f"multipart/form-data; boundary={boundary}"
        },
        body_bytes=b"",
        rfile=rfile,
        content_length=len(body_str)
    )
    
    if status != 201:
        print("Error response:", resp_body)
    assert status == 201
    
    doc_dict = resp_body["document"]
    assert doc_dict["customer_id"] is None
    assert doc_dict["project_id"] is None
    assert doc_dict["document_type"] == "invoice"
    
    file_path = doc_dict["file_path"]
    assert os.path.exists(file_path)
    assert "/invoices/general/" in file_path
    
    with open(file_path, "rb") as f:
        assert f.read() == file_content

    # Clean up the test file
    os.remove(file_path)

def test_document_download(server_app, tmp_path):
    token = server_app.auth_service.create_token(server_app._test_user)
    
    test_file = tmp_path / "download_test.txt"
    test_file.write_bytes(b"download this")
    
    # insert a document manually
    server_app.db.get_connection().execute(
        "INSERT INTO documents (id, title, document_type, file_path, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?)",
        (5, "Test Doc", "upload", str(test_file), "2026-09-06T00:00:00Z", "2026-09-06T00:00:00Z")
    )
    server_app.db.get_connection().commit()
    
    status, headers, resp_generator = server_app.router.handle_request(
        method="GET",
        path_with_query="/api/v1/documents/5/download",
        headers={"Authorization": f"Bearer {token}"},
        body_bytes=b""
    )
    
    assert status == 200
    assert headers["Content-Type"] == "application/octet-stream"
    assert "download_test.txt" in headers["Content-Disposition"]
    
    content = b""
    for chunk in resp_generator:
        content += chunk
    assert content == b"download this"

def test_document_upload_too_large(server_app):
    token = server_app.auth_service.create_token(server_app._test_user)
    
    status, headers, resp_body = server_app.router.handle_request(
        method="POST",
        path_with_query="/api/v1/documents",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "multipart/form-data; boundary=xyz"
        },
        body_bytes=b"",
        rfile=MockRFile(b""),
        content_length=26214401  # > 25MB
    )
    
    assert status == 413
    assert resp_body["error"] == "Payload Too Large"
