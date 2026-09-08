import pytest
import os
from pathlib import Path
from core.filesystem import get_filesystem, reset_filesystem, FilesystemAccessError

def test_path_traversal():
    """Verify that path traversal outside the workspace is correctly blocked."""
    import tempfile

    # NEW-404: get_filesystem() caches a singleton across tests; without a
    # reset, a workspace set by an earlier test in the full suite run can
    # persist here and make the assertions below check the wrong workspace.
    reset_filesystem()

    with tempfile.TemporaryDirectory() as temp_workspace:
        fs = get_filesystem(workspace=Path(temp_workspace))
        
        # Test valid path
        valid_path = os.path.join(temp_workspace, "allowed_file.txt")
        assert fs._validate_path(valid_path) == Path(valid_path).resolve()
        
        # Test path traversal (escape attempts)
        escapes = [
            "../../../etc/passwd",
            "/etc/hosts",
            os.path.join(temp_workspace, "..", "outside.txt"),
            os.path.expanduser("~/.bashrc")
        ]
        
        for attempt in escapes:
            with pytest.raises(FilesystemAccessError):
                fs._validate_path(attempt)

