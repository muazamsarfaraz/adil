# Image/Screenshot Support Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add image/screenshot upload support to AskAdil so users can submit evidence photos and document images for legal analysis using Gemini 3 Flash's multimodal capabilities.

**Architecture:** Images uploaded via Chainlit's file upload are read as bytes, base64-encoded, and sent to a new backend endpoint (`POST /api/v1/query/image`). The backend passes them as inline `Part.from_bytes()` data to `gemini-3-flash-preview` alongside the existing system prompt and file search tool in a single combined call. The response flows through the same citation extraction and source building pipeline.

**Tech Stack:** Chainlit 2.9.6 (file upload elements), FastAPI (new endpoint), google-genai SDK (`Part.from_bytes`), Pydantic (request validation)

---

### Task 1: Enable File Upload in Chainlit Config

**Files:**
- Modify: `adil-frontend/.chainlit/config.toml:31`

**Step 1: Add file upload config**

Add this section at the end of `config.toml`:

```toml
[features.spontaneous_file_upload]
    enabled = true
    accept = ["image/png", "image/jpeg", "image/gif", "image/webp"]
    max_files = 5
    max_size_mb = 10
```

**Step 2: Verify config loads**

Run: `cd adil-frontend && python -c "import chainlit; print('OK')"`
Expected: `OK` (no config parse errors)

**Step 3: Commit**

```bash
git add adil-frontend/.chainlit/config.toml
git commit -m "feat: enable image upload in Chainlit config

Allow PNG, JPG, GIF, WebP uploads (max 5 files, 10MB each)"
```

---

### Task 2: Add Image Models to Backend

**Files:**
- Modify: `adil-rag-api/models.py:268` (add IMAGE to ContentType)
- Modify: `adil-rag-api/models.py` (add ImageData and ImageQueryRequest after line 98)

**Step 1: Add IMAGE to ContentType enum**

In `models.py`, add `IMAGE = "image"` to the `ContentType` enum after the `SOCIAL_MEDIA` line (line 268):

```python
class ContentType(str, Enum):
    URL = "url"
    VIDEO = "video"
    AUDIO = "audio"
    TEXT = "text"
    YOUTUBE = "youtube"
    SOCIAL_MEDIA = "social_media"
    IMAGE = "image"
```

**Step 2: Add ImageData model**

Add after the `QueryRequest` class (after line 98):

```python
ALLOWED_IMAGE_MIMES = {"image/png", "image/jpeg", "image/gif", "image/webp"}


class ImageData(BaseModel):
    """A single base64-encoded image for multimodal analysis."""
    mime_type: str = Field(
        ...,
        description="MIME type of the image (image/png, image/jpeg, image/gif, image/webp).",
    )
    data: str = Field(
        ...,
        description="Base64-encoded image data.",
        min_length=1,
        max_length=15_000_000,  # ~10MB base64
    )


class ImageQueryRequest(BaseModel):
    """Request model for the `/api/v1/query/image` endpoint.

    Submit one or more images (screenshots, photos of documents) with an
    optional text question. The system will analyse the image content
    against UK discrimination law using Gemini 3 Flash multimodal vision.
    """
    query: Optional[str] = Field(
        None,
        description="Optional text question or context about the image(s).",
        max_length=10000,
    )
    images: List[ImageData] = Field(
        ...,
        description="List of base64-encoded images to analyse (1-5).",
        min_length=1,
        max_length=5,
    )
    include_viability_score: bool = Field(
        False,
        description="Set to `true` to request a litigation viability assessment.",
    )
    conversation_history: Optional[List[ConversationTurn]] = Field(
        None,
        description="Previous conversation turns for multi-turn context.",
        max_length=50,
    )

    model_config = ConfigDict(json_schema_extra={
        "examples": [
            {
                "query": "Is this message discriminatory under the Equality Act 2010?",
                "images": [{"mime_type": "image/png", "data": "<base64>"}],
                "include_viability_score": False,
            },
        ]
    })
```

**Step 3: Update the models import in `app.py`**

In `adil-rag-api/app.py` line 43-46, add the new models to the import:

```python
from models import (
    QueryRequest, QueryResponse, HealthResponse, StatsResponse,
    AnalyzeContentRequest, AnalyzeContentResponse, ExtractedContent, ContentType,
    ImageQueryRequest, ImageData, ALLOWED_IMAGE_MIMES,
)
```

**Step 4: Verify models parse correctly**

Run: `cd adil-rag-api && python -c "from models import ImageQueryRequest, ImageData; print('OK')"`
Expected: `OK`

**Step 5: Commit**

```bash
git add adil-rag-api/models.py adil-rag-api/app.py
git commit -m "feat: add ImageData and ImageQueryRequest models

New Pydantic models for multimodal image analysis endpoint.
Supports 1-5 base64-encoded images with optional text query."
```

---

### Task 3: Add `query_with_images()` to RAG Service

**Files:**
- Modify: `adil-rag-api/rag_service.py:485-492` (add vision model config to constructor)
- Modify: `adil-rag-api/rag_service.py` (add `query_with_images` method after the `query` method, after line 782)

**Step 1: Add vision model config to RAGService constructor**

Update the `__init__` method at line 485:

```python
def __init__(self, gemini_api_key: str, file_search_store_id: str):
    self.client = genai.Client(api_key=gemini_api_key)
    self.file_search_store_id = file_search_store_id
    self.model_name = "gemini-2.5-flash"
    self.vision_model_name = os.getenv("GEMINI_MODEL_VISION", "gemini-3-flash-preview")

    # Pricing (Gemini 2.5 Flash as of Jan 2026)
    self.price_per_1k_input_tokens = 0.00015
    self.price_per_1k_output_tokens = 0.0006
```

Also add `import os` and `import base64` at the top of `rag_service.py` if not already present. `os` is not currently imported. Add after line 17 (`import logging`):

```python
import os
import base64
```

**Step 2: Add `query_with_images` method**

Add after the `query` method (after line 782):

```python
async def query_with_images(
    self,
    images: list,
    query_text: Optional[str] = None,
    max_sources: int = 10,
    include_viability: bool = False,
    conversation_history: Optional[List[Dict[str, str]]] = None,
) -> Tuple[str, List[Source], TokenUsage, QueryMetadata]:
    """Execute multimodal RAG query with images using Gemini 3 Flash.

    Args:
        images: List of dicts with 'mime_type' and 'data' (base64 string).
        query_text: Optional text question alongside images.
        max_sources: Maximum number of legal sources to return.
        include_viability: Whether to include viability assessment.
        conversation_history: Previous conversation turns.

    Returns:
        Tuple of (answer, sources, usage, metadata).
    """
    from google.genai import types as genai_types

    start_time = time.time()

    # Build content parts: images first, then text
    parts = []
    for img in images:
        image_bytes = base64.b64decode(img["data"])
        parts.append(
            genai_types.Part.from_bytes(
                data=image_bytes,
                mime_type=img["mime_type"],
            )
        )

    # Add text query if provided, otherwise use a default prompt
    text = query_text or "Please analyse this image for any potential UK discrimination law issues."
    parts.append(genai_types.Part.from_text(text=text))

    # Build multi-turn contents with image parts on the current turn
    contents: list = []
    if conversation_history:
        for turn in conversation_history:
            contents.append({
                "role": turn["role"],
                "parts": [{"text": turn["content"]}],
            })
    # Current user turn with images + text
    contents.append({
        "role": "user",
        "parts": parts,
    })

    # Config: same system instruction and file search tool
    config = {
        "system_instruction": SYSTEM_INSTRUCTION,
        "tools": [
            {
                "file_search": {
                    "file_search_store_names": [self.file_search_store_id]
                }
            }
        ],
    }

    try:
        response = await asyncio.to_thread(
            self.client.models.generate_content,
            model=self.vision_model_name,
            contents=contents,
            config=config,
        )
    except Exception as e:
        logger.error(f"Gemini Vision API error: {e}")
        raise RuntimeError("Failed to generate response from AI model") from e

    # Extract answer
    try:
        answer = response.text or ""
    except (ValueError, AttributeError):
        logger.warning("Gemini vision response had no text (possibly safety-blocked)")
        answer = (
            "I apologise, but I was unable to analyse this image. "
            "Please try with a different image or describe the content in text."
        )

    # Extract sources from citations in the answer
    sources = self._extract_sources_from_answer(answer, max_sources)

    # Calculate usage
    usage = self._calculate_usage(response)

    processing_time = int((time.time() - start_time) * 1000)
    metadata = QueryMetadata(
        original_language="en",
        processing_time_ms=processing_time,
        model_used=self.vision_model_name,
    )

    return answer, sources, usage, metadata
```

**Step 3: Verify the service module loads**

Run: `cd adil-rag-api && python -c "from rag_service import RAGService; print('OK')"`
Expected: `OK`

**Step 4: Commit**

```bash
git add adil-rag-api/rag_service.py
git commit -m "feat: add query_with_images() to RAGService

Multimodal query method using Gemini 3 Flash with inline image
parts alongside the legal system prompt and file search tool."
```

---

### Task 4: Add `/api/v1/query/image` Endpoint

**Files:**
- Modify: `adil-rag-api/app.py` (add new endpoint after the `/api/v1/analyze` endpoint, before line 719)

**Step 1: Add the image query endpoint**

Add after the `analyze_content` function (after line 716), before the `if __name__` block:

```python
@app.post(
    "/api/v1/query/image",
    response_model=QueryResponse,
    tags=["Query"],
    summary="Analyse images for legal issues",
    responses={
        200: {"description": "Successful image analysis with legal guidance"},
        400: {"description": "Invalid image data or unsupported format"},
        401: {"description": "Missing API key"},
        403: {"description": "Invalid API key"},
        429: {"description": "Rate limit exceeded"},
        503: {"description": "RAG service not initialised"},
    },
)
@limiter.limit(RATE_LIMIT_QUERY)
async def query_image(
    request: Request,
    body: ImageQueryRequest,
    _api_key: str = Security(verify_api_key),
):
    """
    **Analyse uploaded images for potential UK discrimination law issues.**

    Submit one or more images (screenshots of messages, photos of letters,
    evidence of discrimination) with an optional text question. The system uses
    Gemini 3 Flash multimodal vision to:

    1. **Understand** the image content (text, context, visual evidence).
    2. **Analyse** against UK discrimination law using the legal knowledge base.
    3. **Return** structured legal guidance with statutory citations and sources.

    **Supported formats:** PNG, JPEG, GIF, WebP (max 10MB each, max 5 images).

    🔐 **Requires `X-API-Key` header.**
    """
    if not rag_service:
        raise HTTPException(status_code=503, detail="RAG service not initialized")

    # Validate image MIME types
    for i, img in enumerate(body.images):
        if img.mime_type not in ALLOWED_IMAGE_MIMES:
            raise HTTPException(
                status_code=400,
                detail=f"Image {i + 1}: unsupported format '{img.mime_type}'. "
                       f"Allowed: {', '.join(sorted(ALLOWED_IMAGE_MIMES))}",
            )

    try:
        # Convert conversation history
        history_dicts = None
        if body.conversation_history:
            history_dicts = [
                {"role": turn.role, "content": turn.content}
                for turn in body.conversation_history
            ]

        # Convert images to dicts for the RAG service
        images_data = [
            {"mime_type": img.mime_type, "data": img.data}
            for img in body.images
        ]

        answer, sources, usage, metadata = await rag_service.query_with_images(
            images=images_data,
            query_text=body.query,
            max_sources=10,
            include_viability=body.include_viability_score,
            conversation_history=history_dicts,
        )

        # Update stats
        async with _stats_lock:
            stats['total_queries'] += 1
            stats['total_tokens'] += usage.total_tokens
            stats['total_cost'] += usage.estimated_cost_usd or 0
            if body.include_viability_score:
                stats['viability_assessments'] += 1

        litigation_mentioned = _check_litigation_mentioned(answer)
        suggested_questions = _parse_suggested_questions(answer)

        return QueryResponse(
            answer=answer,
            sources=sources,
            viability=None,
            usage=usage,
            query_metadata=metadata,
            educational_content_provided=True,
            litigation_mentioned=litigation_mentioned,
            suggested_questions=suggested_questions,
        )

    except Exception as e:
        logger.error(f"Image query error: {e}")
        raise HTTPException(
            status_code=500,
            detail="An internal error occurred. Please try again later.",
        )
```

**Step 2: Verify the app module loads**

Run: `cd adil-rag-api && python -c "from app import app; print([r.path for r in app.routes])"`
Expected: Output includes `'/api/v1/query/image'`

**Step 3: Commit**

```bash
git add adil-rag-api/app.py
git commit -m "feat: add POST /api/v1/query/image endpoint

Accepts 1-5 base64-encoded images with optional text query.
Validates MIME types and delegates to RAGService.query_with_images()."
```

---

### Task 5: Update Frontend to Handle Image Uploads

**Files:**
- Modify: `adil-frontend/app.py:10-24` (add imports and constants)
- Modify: `adil-frontend/app.py:61` (update `_send_query` signature)
- Modify: `adil-frontend/app.py:221-224` (update `@cl.on_message` handler)

**Step 1: Add base64 import and image constants**

At line 10, add `import base64` after `import re`:

```python
import os
import re
import base64
import httpx
import chainlit as cl
from dotenv import load_dotenv
```

Add image constants after the `URL_PATTERN` line (after line 24):

```python
# Image upload constraints
ALLOWED_IMAGE_MIMES = {"image/png", "image/jpeg", "image/gif", "image/webp"}
MAX_IMAGES = 5
MAX_IMAGE_SIZE_MB = int(os.environ.get("MAX_IMAGE_SIZE_MB", "10"))
```

**Step 2: Update `_send_query` to accept images**

Change the `_send_query` function signature at line 61:

```python
async def _send_query(user_text: str, images: list = None):
```

Add image routing logic. Inside `_send_query`, after the URL detection block (after line 80), add image handling:

```python
        # Show processing indicator for images
        if images:
            count = len(images)
            await msg.stream_token(f"*📸 Analysing {count} image{'s' if count > 1 else ''}...*\n\n")
```

Then update the endpoint selection block (lines 93-116). Replace the entire `async with httpx.AsyncClient` block:

```python
        # Choose endpoint based on content type
        api_headers = {"X-API-Key": ADIL_API_KEY} if ADIL_API_KEY else {}
        async with httpx.AsyncClient(timeout=120.0) as client:
            if images:
                response = await client.post(
                    f"{RAG_API_URL}/api/v1/query/image",
                    headers=api_headers,
                    json={
                        "query": user_text or None,
                        "images": images,
                        "include_viability_score": include_viability,
                        "conversation_history": history_payload,
                    }
                )
            elif contains_urls:
                response = await client.post(
                    f"{RAG_API_URL}/api/v1/analyze",
                    headers=api_headers,
                    json={
                        "content": user_text,
                        "include_viability_score": include_viability,
                        "conversation_history": history_payload,
                    }
                )
            else:
                response = await client.post(
                    f"{RAG_API_URL}/api/v1/query",
                    headers=api_headers,
                    json={
                        "query": user_text,
                        "max_sources": 10,
                        "include_viability_score": include_viability,
                        "conversation_history": history_payload,
                    }
                )
            response.raise_for_status()
            data = response.json()
```

**Step 3: Update `@cl.on_message` handler to extract images**

Replace the `main` function at lines 221-224:

```python
@cl.on_message
async def main(message: cl.Message):
    """Handle incoming messages with URL, image, and conversation memory support"""
    images = None

    # Check for image attachments
    if message.elements:
        image_elements = [
            el for el in message.elements
            if el.mime and el.mime in ALLOWED_IMAGE_MIMES
        ]
        if image_elements:
            if len(image_elements) > MAX_IMAGES:
                await cl.Message(
                    content=f"Please upload a maximum of {MAX_IMAGES} images at a time."
                ).send()
                return

            images = []
            for el in image_elements:
                # Check file size
                file_size = os.path.getsize(el.path)
                if file_size > MAX_IMAGE_SIZE_MB * 1024 * 1024:
                    await cl.Message(
                        content=f"Image '{el.name}' exceeds {MAX_IMAGE_SIZE_MB}MB limit."
                    ).send()
                    return

                # Read and base64 encode
                with open(el.path, "rb") as f:
                    image_bytes = f.read()
                images.append({
                    "mime_type": el.mime,
                    "data": base64.b64encode(image_bytes).decode("utf-8"),
                })

    await _send_query(message.content, images=images)
```

**Step 4: Update welcome message to mention image support**

In `start_chat()` at line 50-52, update the capabilities list:

```python
            "💡 **You can also:**\n"
            "- Upload **screenshots or photos** of messages, letters, or documents for legal analysis\n"
            "- Paste **YouTube / Facebook video / Twitter / Instagram / news article links** for legal analysis (video transcripts extracted automatically)\n"
            "- Ask **follow-up questions** — I remember our conversation\n"
            "- Get **actionable next steps** with real links to organisations like Tell MAMA, ACAS, Citizens Advice, and more\n\n"
```

**Step 5: Verify frontend loads**

Run: `cd adil-frontend && python -c "import app; print('OK')"`
Expected: `OK`

**Step 6: Commit**

```bash
git add adil-frontend/app.py
git commit -m "feat: handle image uploads in Chainlit frontend

Read image attachments from message.elements, validate size/type,
base64-encode and send to /api/v1/query/image backend endpoint.
Updated welcome message to mention image upload capability."
```

---

### Task 6: Add GEMINI_MODEL_VISION to Environment Config

**Files:**
- Modify: `adil-rag-api/.env.example` (add GEMINI_MODEL_VISION and MAX_IMAGE_SIZE_MB)

**Step 1: Add new env vars to .env.example**

Add after the existing GEMINI_MODEL entries:

```env
# Vision model for image analysis (default: gemini-3-flash-preview)
GEMINI_MODEL_VISION=gemini-3-flash-preview

# Max image upload size in MB (default: 10)
MAX_IMAGE_SIZE_MB=10
```

**Step 2: Add to actual .env file if it exists**

Add the same variables to the project's `.env` file (if present).

**Step 3: Commit**

```bash
git add adil-rag-api/.env.example
git commit -m "docs: add GEMINI_MODEL_VISION to .env.example"
```

---

### Task 7: End-to-End Manual Test

**Step 1: Start the backend**

Run: `cd adil-rag-api && python app.py`
Expected: Server starts on port 8000, logs show "Project Adil RAG API started successfully"

**Step 2: Test the image endpoint with curl**

Create a small test image and send it:

```bash
# Create a tiny 1x1 PNG (base64)
TEST_IMG="iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="

curl -X POST http://localhost:8000/api/v1/query/image \
  -H "Content-Type: application/json" \
  -H "X-API-Key: $ADIL_API_KEY" \
  -d "{\"query\": \"What is in this image?\", \"images\": [{\"mime_type\": \"image/png\", \"data\": \"$TEST_IMG\"}]}"
```

Expected: JSON response with `answer`, `sources`, `usage`, and `query_metadata` fields. `query_metadata.model_used` should be `gemini-3-flash-preview`.

**Step 3: Test validation — bad MIME type**

```bash
curl -X POST http://localhost:8000/api/v1/query/image \
  -H "Content-Type: application/json" \
  -H "X-API-Key: $ADIL_API_KEY" \
  -d "{\"query\": \"test\", \"images\": [{\"mime_type\": \"application/pdf\", \"data\": \"dGVzdA==\"}]}"
```

Expected: 400 error with "unsupported format" message

**Step 4: Start the frontend**

Run: `cd adil-frontend && chainlit run app.py`
Expected: Chainlit starts on port 8080

**Step 5: Test in browser**

1. Open http://localhost:8080
2. Verify the welcome message mentions image upload capability
3. Verify the attach button (paperclip icon) appears in the chat input
4. Upload a screenshot of a discriminatory message
5. Optionally type a question alongside it
6. Verify the response includes legal analysis with sources

**Step 6: Commit any fixes**

```bash
git add -A
git commit -m "fix: address issues found during manual testing"
```

---

### Summary of All Changed Files

| File | Change |
|------|--------|
| `adil-frontend/.chainlit/config.toml` | Add `[features.spontaneous_file_upload]` section |
| `adil-rag-api/models.py` | Add `IMAGE` to `ContentType`, add `ImageData`, `ImageQueryRequest`, `ALLOWED_IMAGE_MIMES` |
| `adil-rag-api/rag_service.py` | Add `import os, base64`, `vision_model_name` to constructor, `query_with_images()` method |
| `adil-rag-api/app.py` | Import new models, add `POST /api/v1/query/image` endpoint |
| `adil-frontend/app.py` | Add `import base64`, image constants, update `_send_query` for images, update `main()` handler, update welcome message |
| `adil-rag-api/.env.example` | Add `GEMINI_MODEL_VISION`, `MAX_IMAGE_SIZE_MB` |
