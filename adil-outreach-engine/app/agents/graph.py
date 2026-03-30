"""Main outreach graph assembly — wires all nodes into a LangGraph StateGraph."""

from __future__ import annotations

import logging

from langgraph.graph import END, START, StateGraph

from app.agents.nodes.classify import classify_node
from app.agents.nodes.compose import compose_node
from app.agents.nodes.evaluate import evaluate_node, evaluate_router
from app.agents.nodes.research import research_node
from app.agents.nodes.send import send_node
from app.agents.state import OutreachState

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Gate node — human approval gate
# ---------------------------------------------------------------------------


async def gate_node(state: OutreachState) -> dict:
    """
    Human approval gate.

    If campaign.auto_send is True, passes through immediately.
    If False, interrupts the graph for human approval via /approve-draft endpoint.

    Reads: state["campaign"]
    Writes: state["current_step"]
    """
    campaign = state.get("campaign", {})
    if campaign.get("auto_send", False):
        logger.info("Gate: auto_send enabled — approving automatically")
        return {"current_step": "gate_approved"}
    else:
        logger.info("Gate: auto_send disabled — awaiting human approval")
        return {"current_step": "gate_pending"}


def gate_router(state: dict) -> str:
    """Route from gate node. Auto-send or wait for approval."""
    if state.get("current_step") == "gate_approved":
        return "send"
    else:
        return END  # Paused for human approval; resume via /approve-draft


# ---------------------------------------------------------------------------
# Classify router — routes based on classification result
# ---------------------------------------------------------------------------


def classify_router(state: dict) -> str:
    """Route from classify node based on classification result."""
    classification = state.get("classification", "question")
    if classification == "interested":
        return "convert"
    elif classification == "declined":
        return "close"
    elif classification == "question":
        return "compose"  # compose a reply to the question
    elif classification == "out_of_office":
        return "close"  # will be rescheduled by arq
    elif classification == "bounce":
        return "close"
    else:
        return "close"  # safe default


# ---------------------------------------------------------------------------
# Terminal nodes — convert and close (placeholders for Plan 3)
# ---------------------------------------------------------------------------


async def convert_node(state: OutreachState) -> dict:
    """Mark contact as converted. Actual conversion handling in Plan 3."""
    logger.info(
        "Convert: contact %s marked as converted",
        state.get("contact", {}).get("name", "unknown"),
    )
    return {"current_step": "convert"}


async def close_node(state: OutreachState) -> dict:
    """Mark contact as closed (declined/unresponsive). Cleanup in Plan 3."""
    logger.info(
        "Close: contact %s marked as closed",
        state.get("contact", {}).get("name", "unknown"),
    )
    return {"current_step": "close"}


# ---------------------------------------------------------------------------
# Graph builder
# ---------------------------------------------------------------------------


def build_outreach_graph(entry_point: str = "research") -> StateGraph:
    """
    Build the outreach LangGraph StateGraph.

    Args:
        entry_point: The starting node for the graph.
            - ``"research"`` (default) — initial outreach flow:
              START -> research -> compose -> gate -> send -> END
            - ``"evaluate"`` — follow-up / reply-handling flow (invoked by arq):
              START -> evaluate -> classify/compose/close -> END

    Graph flow (from Section 5.1 of design spec):

    START --> research --> compose --> gate --> send --> END (wait for arq)
                                                        |
                           evaluate <--- (arq deferred task)
                              |
                     +--------+--------+
                     |                 |
                reply_exists      no_reply
                     |                 |
                  classify      follow_up_or_close
                     |                 |
              +------+------+    (compose or close)
              |      |      |
          interested declined question/ooo
              |      |      |
           convert  close  compose (reply)

    Returns:
        An uncompiled StateGraph ready for .compile().
    """
    graph = StateGraph(OutreachState)

    # --- Add nodes ---
    graph.add_node("research", research_node)
    graph.add_node("compose", compose_node)
    graph.add_node("gate", gate_node)
    graph.add_node("send", send_node)
    graph.add_node("evaluate", evaluate_node)
    graph.add_node("classify", classify_node)
    graph.add_node("convert", convert_node)
    graph.add_node("close", close_node)

    # --- Entry point (configurable) ---
    if entry_point == "evaluate":
        graph.add_edge(START, "evaluate")
    else:
        graph.add_edge(START, "research")

    # --- Linear flow: research -> compose -> gate ---
    graph.add_edge("research", "compose")
    graph.add_edge("compose", "gate")

    # --- Conditional: gate -> send or END (interrupt for approval) ---
    graph.add_conditional_edges(
        "gate",
        gate_router,
        {
            "send": "send",
            END: END,  # paused for human approval
        },
    )

    # --- send -> END (wait period handled by arq, not the graph) ---
    graph.add_edge("send", END)

    # --- Evaluate routing ---
    # Conditional: evaluate -> classify or compose or close
    graph.add_conditional_edges(
        "evaluate",
        evaluate_router,
        {
            "classify": "classify",
            "compose": "compose",
            "close": "close",
        },
    )

    # --- Conditional: classify -> convert or close or compose ---
    graph.add_conditional_edges(
        "classify",
        classify_router,
        {
            "convert": "convert",
            "close": "close",
            "compose": "compose",
        },
    )

    # --- Terminal nodes ---
    graph.add_edge("convert", END)
    graph.add_edge("close", END)

    return graph


def compile_outreach_graph(entry_point: str = "research") -> "CompiledGraph":  # noqa: F821
    """Build and compile the outreach graph, returning a ready-to-invoke CompiledGraph."""
    return build_outreach_graph(entry_point=entry_point).compile()
