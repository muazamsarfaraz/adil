from unittest.mock import MagicMock

import pytest

from app.services.gemini_uploader import GeminiUploader


@pytest.fixture
def mock_genai_client():
    client = MagicMock()
    mock_file = MagicMock()
    mock_file.name = "files/abc123"
    client.files.upload.return_value = mock_file
    return client


@pytest.fixture
def uploader(mock_genai_client):
    return GeminiUploader(
        client=mock_genai_client,
        store_id="fileSearchStores/test-store",
    )


def test_upload_document_returns_file_id(uploader, mock_genai_client):
    file_id = uploader.upload_document(
        text="CITATION: [2023] EAT 45\n---\nJudgment text here",
        display_name="[2023] EAT 45 - Smith v Employer Ltd",
    )
    assert file_id == "files/abc123"
    mock_genai_client.files.upload.assert_called_once()


def test_upload_document_passes_content(uploader, mock_genai_client):
    uploader.upload_document(
        text="test content",
        display_name="Test Case",
    )
    call_args = mock_genai_client.files.upload.call_args
    assert call_args is not None


def test_upload_failure_raises(mock_genai_client):
    mock_genai_client.files.upload.side_effect = Exception("API error")
    uploader = GeminiUploader(client=mock_genai_client, store_id="fileSearchStores/test-store")
    with pytest.raises(Exception, match="API error"):
        uploader.upload_document(text="test", display_name="test")
