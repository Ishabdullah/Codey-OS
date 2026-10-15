import os
import pytest
import io
import sqlite3

from restoricon_core.api.server import RestoriconAPIServer

# We can mock the HTTP server environment to test the router directly.
class MockRFile:
    def __init__(self, data: bytes):
        self._f = io.BytesIO(data)
        
    def read(self, size: int = -1) -> bytes:
        return self._f.read(size)

@pytest.fixture
def server_app():
    db_path = ":memory:"
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

def test_assessment_photo_upload_uses_valid_document_type(server_app):
    # Regression test: the B8.5b assessment photo-upload form
    # (handleAssessmentPhotoUpload in web_surfaces.py) used to send
    # document_type='assessment_photo', which is not in the
    # documents.document_type CHECK constraint ('assessment_photo' was
    # not a valid value and made every real upload 500) -- caught by
    # code-reviewer's live repro, not by any test, since no test
    # exercised the real multipart upload path with that value. It now
    # sends 'photo' plus an 'assessment' form field, which routes.py
    # turns into an 'assessment' tag -- mirroring the existing
    # subcontractor_id -> tag pattern. This test asserts against a
    # fresh GET re-read of the created document, not just the POST's
    # echoed response, since create_document() returns the same
    # in-memory Document it was handed rather than a re-read row.
    token = server_app.auth_service.create_token(server_app._test_user)
    admin_ctx = server_app.auth_service.authenticate_token(token)

    # Real parent row for the FK-constrained customer_id -- matches
    # handleAssessmentPhotoUpload, which only sends customer_id when
    # currentCustomer360Id is set (the real caller's only entry point --
    # the form is always launched from inside the Customer 360 modal),
    # so this exercises the customer_id storage sub-directory branch,
    # not the 'general' fallback.
    from restoricon_core.models import Customer
    customer = server_app.crm_service.create_customer(
        Customer(first_name="Roof", last_name="Owner"), admin_ctx
    )

    boundary = "----WebKitFormBoundary7MA4YWxkTrZu0gW"
    file_content = b"fake jpeg bytes" * 5

    body_str = (
        f"--{boundary}\r\n"
        f"Content-Disposition: form-data; name=\"document_type\"\r\n\r\n"
        f"photo\r\n"
        f"--{boundary}\r\n"
        f"Content-Disposition: form-data; name=\"assessment\"\r\n\r\n"
        f"true\r\n"
        f"--{boundary}\r\n"
        f"Content-Disposition: form-data; name=\"title\"\r\n\r\n"
        f"roof_damage.jpg\r\n"
        f"--{boundary}\r\n"
        f"Content-Disposition: form-data; name=\"customer_id\"\r\n\r\n"
        f"{customer.id}\r\n"
        f"--{boundary}\r\n"
        f"Content-Disposition: form-data; name=\"file\"; filename=\"roof_damage.jpg\"\r\n"
        f"Content-Type: image/jpeg\r\n\r\n"
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
    assert doc_dict["document_type"] == "photo"
    assert doc_dict["tags"] == ["assessment"]

    # Re-read from the DB via the real GET route -- create_document()
    # returns the same in-memory object it was handed, so the POST
    # response alone doesn't prove the row actually persisted this way.
    get_status, _, get_body = server_app.router.handle_request(
        method="GET",
        path_with_query=f"/api/v1/documents/{doc_dict['id']}",
        headers={"Authorization": f"Bearer {token}"},
        body_bytes=b"",
    )
    assert get_status == 200
    persisted = get_body["document"]
    assert persisted["document_type"] == "photo"
    assert "assessment" in persisted["tags"]

    file_path = doc_dict["file_path"]
    # Pins the metadata-before-file field ordering this form relies on
    # (see the ordering-trap comment in handleAssessmentPhotoUpload /
    # NEW-571): if 'file' were appended before the metadata fields,
    # document_type would still be read (it's on the outer metadata
    # dict by the time of the assert above) but the storage directory
    # would silently fall back to 'photos/general/' instead of
    # 'photos/customers/<id>/'.
    assert "/photos/customers/" in file_path
    assert os.path.exists(file_path)
    with open(file_path, "rb") as f:
        assert f.read() == file_content

    os.remove(file_path)


def test_document_download(server_app, tmp_path, monkeypatch):
    token = server_app.auth_service.create_token(server_app._test_user)

    # NEW-938's download-side containment check requires the file to
    # live under the configured doc store -- point the store at tmp_path
    # instead of writing a document row that points outside it (which
    # this test used to do, but that no longer represents a legitimate
    # document: every real producer -- the multipart upload handler,
    # the contract-PDF path -- writes under get_restoricon_doc_store_path()).
    monkeypatch.setenv("RESTORICON_DOC_STORE_PATH", str(tmp_path))
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


# ==========================================
# NEW-937: write-side path traversal + authz-after-effect
# ==========================================


def _walk_all_paths(root):
    """All files and directories under root (recursively), for asserting
    'nothing was written anywhere', not just 'the expected file is
    absent' -- catches an escape into a sibling directory, and catches
    os.makedirs() running even if open() never did."""
    found = set()
    for dirpath, dirnames, filenames in os.walk(root):
        for d in dirnames:
            found.add(os.path.join(dirpath, d))
        for f in filenames:
            found.add(os.path.join(dirpath, f))
    return found


def _build_multipart_body(boundary, fields, file_field_name, filename, file_content):
    parts = []
    for name, value in fields.items():
        parts.append(
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="{name}"\r\n\r\n'
            f"{value}\r\n"
        )
    body = "".join(parts).encode()
    body += (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="{file_field_name}"; filename="{filename}"\r\n'
        f"Content-Type: text/plain\r\n\r\n"
    ).encode() + file_content + f"\r\n--{boundary}--\r\n".encode()
    return body


def test_document_upload_relative_traversal_document_type_refused(server_app, tmp_path, monkeypatch):
    # NEW-937: document_type = "../evil" used to be spliced straight
    # into os.path.join() unvalidated, escaping the doc store via
    # relative traversal -- rel_dir = f"{document_type}s" = "../evils"
    # would resolve to a sibling of store_dir, i.e. tmp_path/evils.
    # NOTE (W2, code-reviewer round 2): in practice this request is
    # actually refused by the _LEGAL_DOCUMENT_TYPES whitelist check,
    # which runs BEFORE any path is constructed -- so this test alone
    # does not discriminate whether the separate realpath/commonpath
    # containment check works; see
    # test_document_upload_symlinked_store_dir_containment_check and
    # test_document_upload_symlinked_target_file_containment_check
    # below for tests that exercise the containment check on its own
    # with a whitelisted document_type. This test still tightens its
    # assertion to the specific traversal target (not just "nothing
    # changed under tmp_path") so it's at least meaningful for the
    # whitelist layer.
    store_dir = tmp_path / "store"
    monkeypatch.setenv("RESTORICON_DOC_STORE_PATH", str(store_dir))

    before = _walk_all_paths(tmp_path)

    token = server_app.auth_service.create_token(server_app._test_user)
    boundary = "----boundaryNEW937a"
    file_content = b"malicious content"
    body = _build_multipart_body(
        boundary,
        {"document_type": "../evil"},
        "file",
        "payload.txt",
        file_content,
    )

    status, headers, resp_body = server_app.router.handle_request(
        method="POST",
        path_with_query="/api/v1/documents",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": f"multipart/form-data; boundary={boundary}",
        },
        body_bytes=b"",
        rfile=MockRFile(body),
        content_length=len(body),
    )

    assert status == 400
    assert "document_type" in resp_body["error"]

    # W2 tightening: assert the specific traversal target was never
    # created, not just "nothing unexpected is in tmp_path" -- that
    # weaker form would pass even if containment were silently broken,
    # as long as nothing else happened to write into tmp_path either.
    assert not (tmp_path / "evils").exists()

    after = _walk_all_paths(tmp_path)
    assert after == before, f"traversal wrote something: {after - before}"


def test_document_upload_symlinked_store_dir_containment_check(server_app, tmp_path, monkeypatch):
    # W1 (code-reviewer round 2): the realpath+commonpath containment
    # check on target_dir is unreachable by the existing traversal test
    # above (the whitelist rejects any non-legal document_type first),
    # and by the absolute-path-id test below (int() rejects any
    # non-numeric id first) -- so neither test actually exercises the
    # containment check. This test uses a whitelisted document_type
    # and valid (absent) ids, so execution reaches the containment
    # check, and defeats it with a symlink planted INSIDE the doc store
    # that points OUTSIDE it: store_dir/uploads -> outside_dir. Without
    # the containment check, os.makedirs(target_dir) would create
    # (or traverse) outside_dir/general and the upload would succeed;
    # with it, this must be refused before any directory is created
    # under outside_dir.
    store_dir = tmp_path / "store"
    store_dir.mkdir()
    outside_dir = tmp_path / "outside"
    outside_dir.mkdir()
    os.symlink(outside_dir, store_dir / "uploads")
    monkeypatch.setenv("RESTORICON_DOC_STORE_PATH", str(store_dir))

    before_outside = _walk_all_paths(outside_dir)

    token = server_app.auth_service.create_token(server_app._test_user)
    boundary = "----boundaryNEW937e"
    file_content = b"malicious content via symlinked store dir"
    body = _build_multipart_body(
        boundary,
        {"document_type": "upload"},
        "file",
        "payload.txt",
        file_content,
    )

    status, headers, resp_body = server_app.router.handle_request(
        method="POST",
        path_with_query="/api/v1/documents",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": f"multipart/form-data; boundary={boundary}",
        },
        body_bytes=b"",
        rfile=MockRFile(body),
        content_length=len(body),
    )

    assert status == 400
    assert "escapes" in resp_body["error"]

    after_outside = _walk_all_paths(outside_dir)
    assert after_outside == before_outside, (
        f"containment check failed to stop a symlinked store dir: {after_outside - before_outside}"
    )


def test_document_upload_symlinked_target_file_containment_check(server_app, tmp_path, monkeypatch):
    # W1 (code-reviewer round 2), second containment check: target_dir
    # itself is legitimately inside the doc store, but the final
    # per-upload filename (saved_file_path) is checked again because
    # open(..., "wb") would otherwise follow a symlink planted at that
    # exact future filename straight through to an outside target --
    # the directory-level check above does not cover this. time.time()
    # is frozen so the filename this handler will compute is
    # predictable, and a symlink is pre-planted at that exact path
    # pointing at a file outside the store.
    store_dir = tmp_path / "store"
    monkeypatch.setenv("RESTORICON_DOC_STORE_PATH", str(store_dir))

    target_dir = store_dir / "uploads" / "general"
    target_dir.mkdir(parents=True)

    outside_dir = tmp_path / "outside"
    outside_dir.mkdir()
    victim = outside_dir / "victim.txt"
    victim.write_bytes(b"pre-existing victim content")

    fixed_time = 1700000000
    monkeypatch.setattr("time.time", lambda: fixed_time)
    planted_symlink = target_dir / f"{fixed_time}_payload.txt"
    os.symlink(victim, planted_symlink)

    token = server_app.auth_service.create_token(server_app._test_user)
    boundary = "----boundaryNEW937f"
    file_content = b"malicious content via symlinked target file"
    body = _build_multipart_body(
        boundary,
        {"document_type": "upload"},
        "file",
        "payload.txt",
        file_content,
    )

    status, headers, resp_body = server_app.router.handle_request(
        method="POST",
        path_with_query="/api/v1/documents",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": f"multipart/form-data; boundary={boundary}",
        },
        body_bytes=b"",
        rfile=MockRFile(body),
        content_length=len(body),
    )

    assert status == 400
    assert "escapes" in resp_body["error"]

    # The victim file outside the store must be untouched -- not
    # overwritten via the planted symlink.
    assert victim.read_bytes() == b"pre-existing victim content"


def test_document_upload_absolute_path_id_field_refused(server_app, tmp_path, monkeypatch):
    # NEW-937: an id field set to an absolute path used to fully escape
    # the doc store, since os.path.join() discards every preceding
    # component once one is absolute -- the fix int()-parses every id
    # field before it can reach any path construction, so a
    # non-numeric absolute-path string is now refused at that parse
    # step, never a path-construction step.
    store_dir = tmp_path / "store"
    monkeypatch.setenv("RESTORICON_DOC_STORE_PATH", str(store_dir))

    before = _walk_all_paths(tmp_path)

    token = server_app.auth_service.create_token(server_app._test_user)
    boundary = "----boundaryNEW937b"
    file_content = b"malicious content"
    absolute_evil = str(tmp_path / "absolute_evil")
    body = _build_multipart_body(
        boundary,
        {"document_type": "upload", "project_id": absolute_evil},
        "file",
        "payload.txt",
        file_content,
    )

    status, headers, resp_body = server_app.router.handle_request(
        method="POST",
        path_with_query="/api/v1/documents",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": f"multipart/form-data; boundary={boundary}",
        },
        body_bytes=b"",
        rfile=MockRFile(body),
        content_length=len(body),
    )

    assert status == 400
    assert "project_id" in resp_body["error"]

    after = _walk_all_paths(tmp_path)
    assert after == before, f"absolute-path id field wrote something: {after - before}"


def test_document_upload_unauthorized_role_refused_before_write(server_app, tmp_path, monkeypatch):
    # NEW-937: previously PERM_WRITE_DOCUMENTS was only checked inside
    # crm.create_document(), which ran AFTER the file was already
    # written -- a ROLE_CUSTOMER actor (which lacks the permission)
    # could trigger the write and only get a 403 back afterward, with
    # the already-written file left on disk. Checks the filesystem
    # directly, not just the response code.
    store_dir = tmp_path / "store"
    monkeypatch.setenv("RESTORICON_DOC_STORE_PATH", str(store_dir))

    from restoricon_core.models import Customer

    customer = server_app.crm_service.create_customer(
        Customer(first_name="No", last_name="Perm"),
        server_app.auth_service.authenticate_token(
            server_app.auth_service.create_token(server_app._test_user)
        ),
    )
    customer_user = server_app.auth_service.create_user(
        username="cust_937",
        plain_password="password",
        full_name="Customer",
        email="cust_937@test.com",
        role="customer",
        customer_id=customer.id,
    )
    server_app.db.get_connection().commit()
    token = server_app.auth_service.create_token(customer_user)

    before = _walk_all_paths(tmp_path)

    boundary = "----boundaryNEW937c"
    file_content = b"should never land on disk"
    body = _build_multipart_body(
        boundary,
        {"document_type": "upload"},
        "file",
        "payload.txt",
        file_content,
    )

    status, headers, resp_body = server_app.router.handle_request(
        method="POST",
        path_with_query="/api/v1/documents",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": f"multipart/form-data; boundary={boundary}",
        },
        body_bytes=b"",
        rfile=MockRFile(body),
        content_length=len(body),
    )

    assert status == 403

    after = _walk_all_paths(tmp_path)
    assert after == before, f"unauthorized upload wrote something: {after - before}"


def test_document_upload_legitimate_still_works_after_937_fix(server_app, tmp_path, monkeypatch):
    # Regression test: a normal, legitimate multipart upload still
    # succeeds exactly as before, now that document_type/id validation,
    # the permission check, and the containment check all run earlier.
    store_dir = tmp_path / "store"
    monkeypatch.setenv("RESTORICON_DOC_STORE_PATH", str(store_dir))

    token = server_app.auth_service.create_token(server_app._test_user)
    boundary = "----boundaryNEW937d"
    file_content = b"perfectly normal content"
    body = _build_multipart_body(
        boundary,
        {"document_type": "invoice"},
        "file",
        "normal.txt",
        file_content,
    )

    status, headers, resp_body = server_app.router.handle_request(
        method="POST",
        path_with_query="/api/v1/documents",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": f"multipart/form-data; boundary={boundary}",
        },
        body_bytes=b"",
        rfile=MockRFile(body),
        content_length=len(body),
    )

    assert status == 201
    doc_dict = resp_body["document"]
    assert doc_dict["document_type"] == "invoice"
    file_path = doc_dict["file_path"]
    assert os.path.exists(file_path)
    assert str(store_dir) in file_path
    with open(file_path, "rb") as f:
        assert f.read() == file_content


# ==========================================
# NEW-938: read-side arbitrary file disclosure via JSON-body registration
# ==========================================


def test_document_json_post_with_file_path_rejected(server_app):
    token = server_app.auth_service.create_token(server_app._test_user)

    status, headers, resp_body = server_app.router.handle_request(
        method="POST",
        path_with_query="/api/v1/documents",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        body_bytes=b'{"document_type": "contract", "title": "evil", "file_path": "/etc/passwd"}',
    )

    assert status == 400
    assert "file_path" in resp_body["error"]


def test_document_download_refuses_file_outside_doc_store(server_app, tmp_path, monkeypatch):
    # NEW-938 defense-in-depth: even if some other code path manages to
    # construct a Document row with a file_path outside the doc store,
    # /download must refuse it independently of the JSON-body rejection
    # above. Constructed directly against the service layer (not via the
    # now-rejected JSON POST) to test this check on its own.
    store_dir = tmp_path / "store"
    monkeypatch.setenv("RESTORICON_DOC_STORE_PATH", str(store_dir))

    outside_dir = tmp_path / "outside_the_store"
    outside_dir.mkdir()
    secret_file = outside_dir / "secret.txt"
    secret_file.write_bytes(b"top secret")

    admin_ctx = server_app.auth_service.authenticate_token(
        server_app.auth_service.create_token(server_app._test_user)
    )
    from restoricon_core.models import Document

    doc = server_app.crm_service.create_document(
        Document(document_type="upload", title="Escaped Doc", file_path=str(secret_file)),
        admin_ctx,
    )

    token = server_app.auth_service.create_token(server_app._test_user)
    status, headers, resp_body = server_app.router.handle_request(
        method="GET",
        path_with_query=f"/api/v1/documents/{doc.id}/download",
        headers={"Authorization": f"Bearer {token}"},
        body_bytes=b"",
    )

    assert status == 403
    assert "not permitted" in resp_body["error"]


# ==========================================
# NEW-461: don't orphan the uploaded file when the DB insert fails
# ==========================================


def test_document_upload_fk_failure_does_not_orphan_file(server_app, tmp_path, monkeypatch):
    # NEW-461: a nonexistent project_id passes NEW-937's int()-validation
    # (it's a valid int) but fails the documents.project_id FK constraint
    # at INSERT time inside create_document() -- which used to leave the
    # already-written file on disk with no DB row behind. The route
    # handler's own try/except around the parse-through-create_document
    # block must clean it up.
    store_dir = tmp_path / "store"
    monkeypatch.setenv("RESTORICON_DOC_STORE_PATH", str(store_dir))

    before = _walk_all_paths(tmp_path)

    token = server_app.auth_service.create_token(server_app._test_user)
    boundary = "----boundaryNEW461a"
    file_content = b"orphan-candidate content"
    body = _build_multipart_body(
        boundary,
        {"document_type": "upload", "project_id": "999999"},
        "file",
        "payload.txt",
        file_content,
    )

    status, headers, resp_body = server_app.router.handle_request(
        method="POST",
        path_with_query="/api/v1/documents",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": f"multipart/form-data; boundary={boundary}",
        },
        body_bytes=b"",
        rfile=MockRFile(body),
        content_length=len(body),
    )

    assert status == 500

    after = _walk_all_paths(tmp_path)
    # Empty directories created by os.makedirs() along the way are fine
    # (NEW-937's containment check runs before them and they're not the
    # orphan this test targets) -- only files must not remain.
    leftover_files = {p for p in (after - before) if os.path.isfile(p)}
    assert not leftover_files, f"FK-failure orphaned a file: {leftover_files}"


def test_document_upload_non_utf8_metadata_field_does_not_orphan_file(server_app, tmp_path, monkeypatch):
    # NEW-461 (related manifestation): a non-UTF-8 byte in a metadata
    # field arriving after the file part raises UnicodeDecodeError (a
    # ValueError) out of on_part_data's .decode("utf-8") -- this used to
    # propagate past the already-opened/written file with no cleanup.
    store_dir = tmp_path / "store"
    monkeypatch.setenv("RESTORICON_DOC_STORE_PATH", str(store_dir))

    before = _walk_all_paths(tmp_path)

    token = server_app.auth_service.create_token(server_app._test_user)
    boundary = "----boundaryNEW461b"
    file_content = b"orphan-candidate content"

    body = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="document_type"\r\n\r\n'
        f"upload\r\n"
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="file"; filename="payload.txt"\r\n'
        f"Content-Type: text/plain\r\n\r\n"
    ).encode() + file_content + (
        f"\r\n--{boundary}\r\n"
        f'Content-Disposition: form-data; name="title"\r\n\r\n'
    ).encode() + b"\xff\xfe" + f"\r\n--{boundary}--\r\n".encode()

    status, headers, resp_body = server_app.router.handle_request(
        method="POST",
        path_with_query="/api/v1/documents",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": f"multipart/form-data; boundary={boundary}",
        },
        body_bytes=b"",
        rfile=MockRFile(body),
        content_length=len(body),
    )

    assert status in (400, 500)

    after = _walk_all_paths(tmp_path)
    leftover_files = {p for p in (after - before) if os.path.isfile(p)}
    assert not leftover_files, f"non-UTF-8 metadata field orphaned a file: {leftover_files}"


def test_document_upload_post_commit_audit_failure_does_not_orphan_row(server_app, tmp_path, monkeypatch):
    # Regression lock for the bug introduced by this round's own NEW-461
    # fix and caught by code-reviewer: create_document()'s own INSERT
    # commits (via its `with conn:` block) BEFORE it calls audit.log().
    # If audit.log() raises AFTER that commit (e.g. a locked DB, an I/O
    # error), the route handler's broad `except Exception:` cleanup must
    # NOT unlink the file -- a `documents` row already points at it, so
    # deleting it would create an unrecoverable row-without-file state
    # (worse than the original orphan-file bug). Both the file and the
    # row must survive.
    store_dir = tmp_path / "store"
    monkeypatch.setenv("RESTORICON_DOC_STORE_PATH", str(store_dir))

    def _raise_after_commit(*args, **kwargs):
        raise sqlite3.OperationalError("database is locked")

    monkeypatch.setattr(server_app.audit_service, "log", _raise_after_commit)

    before = _walk_all_paths(tmp_path)

    token = server_app.auth_service.create_token(server_app._test_user)
    boundary = "----boundaryNEW461c"
    file_content = b"post-commit-audit-failure content"
    body = _build_multipart_body(
        boundary,
        {"document_type": "upload"},
        "file",
        "payload.txt",
        file_content,
    )

    status, headers, resp_body = server_app.router.handle_request(
        method="POST",
        path_with_query="/api/v1/documents",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": f"multipart/form-data; boundary={boundary}",
        },
        body_bytes=b"",
        rfile=MockRFile(body),
        content_length=len(body),
    )

    assert status == 500

    # The file must still be on disk -- not unlinked by the except
    # block's cleanup, since a documents row already references it.
    new_files = {p for p in (_walk_all_paths(tmp_path) - before) if os.path.isfile(p)}
    assert len(new_files) == 1, f"expected exactly one surviving file, got: {new_files}"
    (surviving_file,) = new_files
    with open(surviving_file, "rb") as f:
        assert f.read() == file_content

    # The documents row itself must have committed (the INSERT's `with
    # conn:` block exited before audit.log() ever ran).
    conn = server_app.db.get_connection()
    row = conn.execute(
        "SELECT file_path FROM documents WHERE file_path = ?",
        (surviving_file,),
    ).fetchone()
    assert row is not None, "documents row did not survive the post-commit audit failure"


def test_document_download_legitimate_upload_still_works_after_938_fix(server_app, tmp_path, monkeypatch):
    # Regression test: downloading a legitimately-uploaded document
    # (one living under the configured doc store) still works.
    store_dir = tmp_path / "store"
    monkeypatch.setenv("RESTORICON_DOC_STORE_PATH", str(store_dir))

    token = server_app.auth_service.create_token(server_app._test_user)
    boundary = "----boundaryNEW938"
    file_content = b"legitimate content to download"
    body = _build_multipart_body(
        boundary,
        {"document_type": "invoice"},
        "file",
        "legit.txt",
        file_content,
    )

    status, headers, resp_body = server_app.router.handle_request(
        method="POST",
        path_with_query="/api/v1/documents",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": f"multipart/form-data; boundary={boundary}",
        },
        body_bytes=b"",
        rfile=MockRFile(body),
        content_length=len(body),
    )
    assert status == 201
    doc_id = resp_body["document"]["id"]

    dl_status, dl_headers, dl_body = server_app.router.handle_request(
        method="GET",
        path_with_query=f"/api/v1/documents/{doc_id}/download",
        headers={"Authorization": f"Bearer {token}"},
        body_bytes=b"",
    )

    assert dl_status == 200
    content = b"".join(dl_body)
    assert content == file_content
