from __future__ import annotations

import io
import logging

from google import genai

logger = logging.getLogger(__name__)


class GeminiUploader:
    """Uploads documents to an existing Gemini File Search Tool store."""

    def __init__(self, client: genai.Client, store_id: str):
        self.client = client
        self.store_id = store_id

    def upload_document(self, text: str, display_name: str) -> str:
        """Upload text as a file to the Gemini FST store.

        Returns the Gemini file ID (e.g. 'files/abc123').
        """
        file_bytes = text.encode("utf-8")
        file_obj = io.BytesIO(file_bytes)

        uploaded = self.client.files.upload(
            file=file_obj,
            config=genai.types.UploadFileConfig(
                display_name=display_name,
                mime_type="text/plain",
            ),
        )

        logger.info("Uploaded %s -> %s", display_name, uploaded.name)
        return uploaded.name
