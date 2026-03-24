# Image/Screenshot Support via Gemini 3 Flash

## Problem

The Chainlit app is text-only. Users cannot upload screenshots of discriminatory messages, social media posts, workplace communications, or photos of legal documents/letters for analysis.

## Solution

Add multimodal image support using Gemini 3 Flash. Images are sent directly to the model alongside the legal system prompt and file search tool in a single combined call — no separate OCR/vision step.

## Constraints

- Max 5 images per message
- Accepted formats: PNG, JPG/JPEG, WebP, GIF
- Max 10MB per image
- Text is optional alongside images (both modes supported)
- Model: `gemini-3-flash-preview`

## Component Changes

### 1. Frontend (`adil-frontend/app.py`)

- Update `@cl.on_message` to check `message.elements` for image attachments
- Validate image count (max 5), MIME types, file size
- Read image files as base64
- Send to new backend endpoint alongside text and conversation history
- Show "Analyzing image(s)..." processing indicator

### 2. Backend Models (`adil-rag-api/models.py`)

- New `ImageData` model: `mime_type: str`, `data: str` (base64)
- New `ImageQueryRequest`: mirrors `QueryRequest` with added `images: List[ImageData]` (max 5)
- Add `IMAGE` to `ContentType` enum

### 3. Backend API (`adil-rag-api/app.py`)

- New endpoint: `POST /api/v1/query/image`
- Accepts optional text + images + conversation history
- Delegates to RAG service with image data
- Returns existing `QueryResponse` structure

### 4. RAG Service (`adil-rag-api/rag_service.py`)

- New method: `query_with_images()` — builds multimodal content parts (text + inline image data)
- Uses `gemini-3-flash-preview` model
- Same system instruction, file search tool, citation extraction
- Falls back to text-only `query()` if no images provided

## Data Flow

```
User attaches screenshot + types question
  → Chainlit reads image elements as base64
  → POST /api/v1/query/image { query?, images[], conversation_history[] }
  → RAG service builds multimodal Gemini request
  → Gemini 3 Flash: sees image + system prompt + file search tool
  → Response parsed for answer, citations, sources (same as today)
  → Formatted response returned to user
```

## What stays the same

- System instruction (legal prompt)
- File search tool integration
- Citation extraction and source building
- Response format
- Existing text-only and URL-analyze flows

## Configuration

- `GEMINI_MODEL_VISION`: default `gemini-3-flash-preview`
- `MAX_IMAGE_SIZE_MB`: default 10
