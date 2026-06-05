"""Template-level legal disclaimer for adil-rag-api LLM Q&A responses.

This module exists to satisfy the cross-cutting "template-level emission" principle
from the portfolio AI-hallucination playbook (§2) and the adil-rag-api worked example
(§8.2). See `E:\\dev\\.services\\ai-hallucination-mitigation-playbook.md`.

THE DISCLAIMER IS INJECTED VIA A `model_serializer` ON THE PYDANTIC RESPONSE MODELS
(and via an SSE `disclaimer` event on the streaming endpoint). The LLM never sees it
in its prompt or context — therefore the LLM is structurally unable to paraphrase or
omit it.

Sister principle to "verifiers refute, not confirm" — both remove the LLM's ability
to undo its own safety floor.

Filed in response to mcbplatform cross-project ask (ClickUp 869dk095z, 2026-06-05).
"""

# The disclaimer string — exactly as specified in playbook §8.2 and ClickUp 869dk095z.
# Do NOT rephrase. Do NOT pass to the LLM. Do NOT include in any SYSTEM_PROMPT.
LEGAL_ADVICE_DISCLAIMER: str = (
    "Information only — not legal advice. " "We help you find a solicitor; we don't represent you."
)

# Structured form used by SSE streams + machine consumers.
LEGAL_ADVICE_DISCLAIMER_OBJECT: dict[str, str] = {
    "text": LEGAL_ADVICE_DISCLAIMER,
    "kind": "legal_advice_disclaimer",
    "rendered_by": "adapter",  # NOT 'llm' — this is the load-bearing fact
    "playbook_ref": "ai-hallucination-mitigation-playbook.md §2 + §8.2",
}
