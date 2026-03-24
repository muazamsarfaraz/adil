"""
Pydantic models for Project Adil RAG API.

Request / response models for the /query and /analyze endpoints,
plus supporting types for citations, metadata, and legal assessment.

Key models:
    - QueryRequest, QueryResponse           - /api/v1/query
    - AnalyzeContentRequest/Response        - /api/v1/analyze
    - ConversationTurn                      - multi-turn conversation history
    - Source, SourceType                    - citation tracking (statute / case law)
    - TokenUsage, QueryMetadata             - token and timing telemetry
    - ViabilityAssessment, VentoBand        - litigation viability scoring

Input validation enforces max_length constraints on all user-supplied strings.
All models include OpenAPI examples for comprehensive Swagger documentation.
"""
from typing import List, Optional
from pydantic import BaseModel, ConfigDict, Field
from enum import Enum


class SourceType(str, Enum):
    """Type of legal source referenced in the response.

    - **statute** — UK Act of Parliament (e.g., Equality Act 2010)
    - **case_law** — Court or tribunal judgment (e.g., Eweida v UK)
    - **guidance** — Official guidance (e.g., ACAS Code, Vento Guidelines)
    - **tribunal_decision** — Employment Tribunal decision
    - **echr_judgment** — European Court of Human Rights judgment
    """
    STATUTE = "statute"
    CASE_LAW = "case_law"
    GUIDANCE = "guidance"
    TRIBUNAL = "tribunal_decision"
    ECHR = "echr_judgment"


class VentoBand(str, Enum):
    """Vento compensation bands for injury to feelings (2025/26 update).

    These bands are used by Employment Tribunals to assess compensation
    for discrimination claims under the Equality Act 2010.

    - **lower** — £1,200 – £12,000 (less serious one-off incidents)
    - **middle** — £12,000 – £36,500 (sustained campaign or serious incident)
    - **upper** — £36,500 – £61,000 (prolonged campaign of discrimination)
    - **exceptional** — £61,000+ (only the most extreme cases)
    """
    LOWER = "lower"
    MIDDLE = "middle"
    UPPER = "upper"
    EXCEPTIONAL = "exceptional"


class ConversationTurn(BaseModel):
    """A single turn in a conversation history.

    Used to provide multi-turn context so the AI can maintain
    continuity across messages in the same chat session.
    """
    role: str = Field(..., description="The role of the speaker: `user` or `model`. Note: AskAdil uses `model` (not `assistant`) to match Gemini's convention.", pattern="^(user|model)$")
    content: str = Field(..., description="The text content of this conversation turn.", min_length=1, max_length=20000)


class QueryRequest(BaseModel):
    """Request model for the `/api/v1/query` endpoint.

    Submit a natural-language question about UK discrimination law.
    The system will search the legal knowledge base and return an
    AI-generated answer grounded in legislation and case law.

    Optionally include `conversation_history` for multi-turn context.
    """
    query: str = Field(..., description="The user's question about UK discrimination law.", min_length=1, max_length=10000)
    max_sources: int = Field(10, description="Maximum number of legal sources to return (1–20).", ge=1, le=20)
    include_viability_score: bool = Field(False, description="Set to `true` to request a preliminary litigation viability assessment with Vento band estimation.")
    conversation_history: Optional[List[ConversationTurn]] = Field(None, description="Previous conversation turns for multi-turn context. Each turn has a `role` ('user' or 'model') and `content`.", max_length=50)

    model_config = ConfigDict(json_schema_extra={
        "examples": [
            {
                "query": "My employer refused to let me take time off for Eid. What are my rights?",
                "max_sources": 5,
                "include_viability_score": False,
            },
            {
                "query": "A colleague made Islamophobic comments about my hijab in a team meeting. Can I claim compensation?",
                "max_sources": 10,
                "include_viability_score": True,
                "conversation_history": [
                    {"role": "user", "content": "What is the Equality Act 2010?"},
                    {"role": "model", "content": "The Equality Act 2010 is the primary UK legislation..."},
                ],
            },
        ]
    })


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


class Source(BaseModel):
    """A legal source citation returned in query responses.

    Each source references a specific piece of UK legislation, case law,
    or guidance document, with links to official government sources.
    """
    document_id: str = Field(..., description="Unique document identifier from the knowledge base.")
    title: str = Field(..., description="Document or case title (e.g., 'Equality Act 2010' or 'Eweida v United Kingdom').")
    excerpt: str = Field(..., description="Relevant text excerpt from the source document.")

    # UK Legal specific fields
    source_type: SourceType = Field(SourceType.STATUTE, description="Type of legal source.")
    neutral_citation: Optional[str] = Field(None, description="Neutral case law citation, e.g., `[2013] ECHR 37`.")
    section: Optional[str] = Field(None, description="Statute section reference, e.g., `s.13` or `s.26(1)`.")
    act_name: Optional[str] = Field(None, description="Name of the Act, e.g., `Equality Act 2010`.")
    jurisdiction: str = Field("England and Wales", description="Legal jurisdiction (defaults to England and Wales).")
    url: Optional[str] = Field(None, description="Link to legislation.gov.uk or caselaw.nationalarchives.gov.uk.")

    relevance_score: Optional[float] = Field(None, ge=0.0, le=1.0, description="Relevance score (0.0–1.0) from the retrieval system.")

    model_config = ConfigDict(json_schema_extra={
        "examples": [{
            "document_id": "ea2010-s13",
            "title": "Equality Act 2010",
            "excerpt": "A person (A) discriminates against another (B) if, because of a protected characteristic, A treats B less favourably than A treats or would treat others.",
            "source_type": "statute",
            "section": "s.13",
            "act_name": "Equality Act 2010",
            "jurisdiction": "England and Wales",
            "url": "https://www.legislation.gov.uk/ukpga/2010/15/section/13",
            "relevance_score": 0.95,
        }]
    })


class ViabilityAssessment(BaseModel):
    """Preliminary litigation viability assessment.

    Evaluates the strength of a potential discrimination claim based on three
    key ingredients: statutory footing, case law precedent, and quantum potential.
    Includes a Vento band estimation for injury to feelings compensation.

    ⚠️ This is a preliminary AI assessment — always requires human-in-the-loop review.
    """
    score: int = Field(..., ge=0, le=100, description="Viability score 0–100 (higher = stronger case).")
    vento_band: Optional[VentoBand] = Field(None, description="Estimated Vento compensation band.")
    vento_range: Optional[str] = Field(None, description="Estimated compensation range, e.g., `£12,000 – £36,500`.")
    requires_hitl: bool = Field(True, description="Whether this case requires human attorney review (always `true`).")
    reasoning: str = Field(..., description="Plain-English explanation of the viability score.")

    # Three litigation ingredients
    statutory_footing: bool = Field(False, description="Whether a clear statutory basis has been identified (e.g., s.13 EA 2010).")
    case_law_precedent: bool = Field(False, description="Whether supporting case law precedent was found.")
    quantum_potential: bool = Field(False, description="Whether recoverable damages are likely.")

    model_config = ConfigDict(json_schema_extra={
        "examples": [{
            "score": 72,
            "vento_band": "middle",
            "vento_range": "£12,000 – £36,500",
            "requires_hitl": True,
            "reasoning": "Strong statutory basis under s.13 Equality Act 2010 (direct discrimination on grounds of religion). Supporting precedent in Eweida v UK. Sustained pattern of behaviour suggests middle Vento band.",
            "statutory_footing": True,
            "case_law_precedent": True,
            "quantum_potential": True,
        }]
    })


class TokenUsage(BaseModel):
    """Token usage and cost information for the Gemini API call."""
    prompt_tokens: int = Field(..., description="Number of tokens in the prompt.")
    completion_tokens: int = Field(..., description="Number of tokens in the completion.")
    total_tokens: int = Field(..., description="Total tokens consumed (prompt + completion).")
    estimated_cost_usd: Optional[float] = Field(None, description="Estimated cost in USD for this query.")


class QueryMetadata(BaseModel):
    """Metadata about how the query was processed."""
    original_language: str = Field("en", description="Detected language of the query.")
    processing_time_ms: int = Field(..., description="Total processing time in milliseconds.")
    model_used: str = Field("gemini-2.5-flash", description="Gemini model used for this query.")


class QueryResponse(BaseModel):
    """Response from the `/api/v1/query` endpoint.

    Contains the AI-generated legal answer, structured source citations,
    optional viability assessment, token usage, and Ad'l compliance flags.
    """
    answer: str = Field(..., description="The AI-generated legal answer, grounded in UK legislation and case law.")
    sources: List[Source] = Field(default_factory=list, description="Legal source citations with links to official sources.")
    viability: Optional[ViabilityAssessment] = Field(None, description="Litigation viability assessment (only if `include_viability_score` was `true`).")
    usage: TokenUsage = Field(..., description="Token usage and cost for this query.")
    query_metadata: QueryMetadata = Field(..., description="Processing metadata.")

    # Adil-specific flags
    educational_content_provided: bool = Field(True, description="FR1 compliance: confirms educational content was provided before any litigation guidance.")
    litigation_mentioned: bool = Field(False, description="Whether the response mentions litigation, tribunals, or solicitors.")

    # Suggested follow-up questions
    suggested_questions: Optional[List[str]] = Field(None, description="Suggested follow-up questions for the user to explore.")


class HealthResponse(BaseModel):
    """Health check response from the `/health` endpoint.

    Use this for load balancer probes and service monitoring.
    """
    status: str = Field(..., description="Service status: `healthy` or `degraded`.")
    version: str = Field(..., description="API version string.")
    gemini_connected: bool = Field(..., description="Whether the Gemini LLM connection is active.")
    document_count: Optional[int] = Field(None, description="Number of documents in the knowledge base (if available).")

    model_config = ConfigDict(json_schema_extra={
        "examples": [{
            "status": "healthy",
            "version": "1.1.0",
            "gemini_connected": True,
            "document_count": None,
        }]
    })


class StatsResponse(BaseModel):
    """Usage statistics from the `/stats` endpoint.

    Returns cumulative metrics since the last service restart.
    """
    total_queries: int = Field(..., description="Total number of queries processed.")
    total_tokens_used: int = Field(..., description="Cumulative token consumption.")
    total_cost_usd: float = Field(..., description="Cumulative estimated cost in USD.")
    average_tokens_per_query: float = Field(..., description="Average tokens per query.")
    uptime_seconds: int = Field(..., description="Seconds since last service restart.")
    viability_assessments_count: int = Field(0, description="Number of viability assessments requested.")

    model_config = ConfigDict(json_schema_extra={
        "examples": [{
            "total_queries": 142,
            "total_tokens_used": 284000,
            "total_cost_usd": 0.0568,
            "average_tokens_per_query": 2000.0,
            "uptime_seconds": 86400,
            "viability_assessments_count": 23,
        }]
    })


# ============================================================================
# Content Extraction Models
# ============================================================================


class ContentType(str, Enum):
    """Type of content submitted for analysis.

    - **url** — A web page URL
    - **video** — A video file or stream
    - **audio** — An audio file or stream
    - **text** — Plain text description
    - **youtube** — A YouTube video URL
    - **social_media** — A social media post (Twitter/X, Facebook, etc.)
    - **image** — An uploaded image file (screenshot, photo of document)
    """
    URL = "url"
    VIDEO = "video"
    AUDIO = "audio"
    TEXT = "text"
    YOUTUBE = "youtube"
    SOCIAL_MEDIA = "social_media"
    IMAGE = "image"


class ExtractedContent(BaseModel):
    """Details of content extracted from a URL or media source."""
    content_type: ContentType = Field(..., description="Type of content that was extracted.")
    source_url: Optional[str] = Field(None, description="Original URL that was analysed.")
    raw_text: str = Field(..., description="The extracted/transcribed text content.")
    title: Optional[str] = Field(None, description="Title of the content (page title, video title, etc.).")
    platform: Optional[str] = Field(None, description="Platform source, e.g., `youtube`, `twitter`, `facebook`.")
    extraction_method: str = Field(..., description="Method used: `web_scrape`, `youtube_transcript`, `nitter_fallback`, or `whisper`.")
    confidence: Optional[float] = Field(None, ge=0.0, le=1.0, description="Confidence score of the extraction (0.0–1.0).")


class AnalyzeContentRequest(BaseModel):
    """Request model for the `/api/v1/analyze` endpoint.

    Submit a URL or plain text describing an incident. The system will
    extract content, analyse it against UK discrimination law, and return
    legal guidance with platform-specific advice.

    Optionally include `conversation_history` for multi-turn context.
    """
    content: str = Field(..., description="Text content or URL to analyse for potential legal issues.", min_length=1, max_length=50000)
    content_type: Optional[ContentType] = Field(None, description="Hint for the type of content being submitted (auto-detected if omitted).")
    include_viability_score: bool = Field(False, description="Set to `true` to request a litigation viability assessment.")
    conversation_history: Optional[List[ConversationTurn]] = Field(None, description="Previous conversation turns for multi-turn context.", max_length=50)

    model_config = ConfigDict(json_schema_extra={
        "examples": [
            {
                "content": "https://www.youtube.com/watch?v=example — is this hate speech under UK law?",
                "include_viability_score": False,
            },
            {
                "content": "A colleague posted Islamophobic comments on the company Slack channel targeting me during Ramadan.",
                "content_type": "text",
                "include_viability_score": True,
            },
        ]
    })


class AnalyzeContentResponse(BaseModel):
    """Response from the `/api/v1/analyze` endpoint.

    Extends the standard query response with content extraction details
    and platform-specific advice (e.g., Online Safety Act 2023 reporting).
    """
    answer: str = Field(..., description="The AI-generated legal analysis.")
    sources: List[Source] = Field(default_factory=list, description="Legal source citations.")
    viability: Optional[ViabilityAssessment] = Field(None, description="Litigation viability assessment (if requested).")
    usage: TokenUsage = Field(..., description="Token usage and cost.")
    query_metadata: QueryMetadata = Field(..., description="Processing metadata.")

    # Adil-specific flags
    educational_content_provided: bool = Field(True, description="FR1 compliance: educational content provided first.")
    litigation_mentioned: bool = Field(False, description="Whether the response mentions litigation.")

    # Suggested follow-up questions
    suggested_questions: Optional[List[str]] = Field(None, description="Suggested follow-up questions for the user to explore.")

    # Content extraction specific fields
    extracted_content: Optional[ExtractedContent] = Field(None, description="Details of the extracted content (URL, transcript, etc.).")
    content_summary: Optional[str] = Field(None, description="Summary of what was analysed, e.g., 'Analyzed 2 URL(s).'.")
    platform_specific_advice: Optional[str] = Field(None, description="Platform-specific advice, e.g., how to report under the Online Safety Act 2023.")


# ============================================================================
# Report Submission Models
# ============================================================================


class ReporterInfo(BaseModel):
    """Personal details of the person filing the report.
    WARNING: PII — never log, never persist."""
    first_name: str = Field(..., min_length=1, max_length=100)
    surname: str = Field(..., min_length=1, max_length=100)
    dob: dict = Field(..., description="Date of birth: {day, month, year}.")
    gender: str = Field(..., min_length=1, max_length=50)
    email: str = Field(..., min_length=5, max_length=200)
    phone: Optional[str] = Field(None, max_length=30)
    address: Optional[str] = Field(None, max_length=500)


class IncidentInfo(BaseModel):
    """Incident details extracted from the AskAdil conversation."""
    details: str = Field(..., min_length=10, max_length=50000)
    location: str = Field(..., min_length=1, max_length=1000)
    date_time: str = Field(..., min_length=1, max_length=500)
    suspect_description: Optional[str] = Field(None, max_length=5000)
    role: str = Field("victim", description="victim, witness, or third_party.")


class SubmitReportRequest(BaseModel):
    """Request to submit a hate crime report via the bridge service."""
    target: str = Field(..., description="Target form ID, e.g. 'police-uk'.")
    consent_confirmed: bool = Field(..., description="The user has explicitly confirmed consent to submit this report. Must be true — API rejects if false.")
    reporter: ReporterInfo
    incident: IncidentInfo
    evidence_urls: Optional[List[str]] = Field(default_factory=list)
    conversation_history: Optional[List[ConversationTurn]] = Field(
        None,
        description="Used ONLY for fallback report generation if bridge fails. Not sent to bridge.",
        max_length=50,
    )


class SubmitReportResponse(BaseModel):
    """Response from report submission."""
    success: bool
    target: str
    reference_number: Optional[str] = None
    confirmation_screenshot: Optional[str] = None
    message: Optional[str] = None
    submitted_at: Optional[str] = None
    error: Optional[str] = None
    fallback_report: Optional[str] = None
    target_url: Optional[str] = None
    form_guide: Optional[str] = None

