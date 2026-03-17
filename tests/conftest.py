import os
import pytest


@pytest.fixture(autouse=True)
def isolate_db(tmp_path):
    """Redirect DB and library to temp dirs for each test."""
    db_path = tmp_path / "test.db"
    library_path = tmp_path / "library"
    library_path.mkdir()
    os.environ["LAESER_DB_PATH"] = str(db_path)
    os.environ["LAESER_LIBRARY_PATH"] = str(library_path)
    from db.schema import init_db
    init_db()
    yield
    os.environ.pop("LAESER_DB_PATH", None)
    os.environ.pop("LAESER_LIBRARY_PATH", None)


@pytest.fixture
def client():
    from fastapi.testclient import TestClient
    from main import app
    return TestClient(app)
