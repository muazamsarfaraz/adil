import os

import httpx
from langchain_core.tools import tool


_SERPER_URL = "https://google.serper.dev/search"
_TIMEOUT = 10.0
_MAX_OUTPUT_CHARS = 3000


@tool
async def search_web(query: str) -> str:
    """Search the web for recent news, awards, and information about a person or firm.

    Args:
        query: The search query string.

    Returns:
        Search results with titles, snippets, and URLs.
    """
    search_provider = os.environ.get("SEARCH_PROVIDER", "serper")

    if search_provider == "serper":
        return await _search_serper(query)
    else:
        return f"Unknown search provider '{search_provider}'. Web search is unavailable."


async def _search_serper(query: str) -> str:
    """Execute a search using the Serper API (Google search)."""
    api_key = os.environ.get("SERPER_API_KEY")
    if not api_key:
        return (
            "Web search is unavailable: SERPER_API_KEY environment variable is not set. "
            "Proceeding without web search results."
        )

    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            response = await client.post(
                _SERPER_URL,
                headers={
                    "X-API-KEY": api_key,
                    "Content-Type": "application/json",
                },
                json={"q": query},
            )

        if response.status_code != 200:
            return f"Error: Serper API returned HTTP {response.status_code}. Web search unavailable."

        data = response.json()
        organic = data.get("organic", [])

        if not organic:
            return f"No search results found for '{query}'."

        # Format top 5 results
        results = []
        for item in organic[:5]:
            title = item.get("title", "No title")
            snippet = item.get("snippet", "No description")
            link = item.get("link", "")
            results.append(f"- {title}\n  {snippet}\n  URL: {link}")

        output = f"Search results for '{query}':\n\n" + "\n\n".join(results)

        # Truncate to stay within limits
        if len(output) > _MAX_OUTPUT_CHARS:
            output = output[:_MAX_OUTPUT_CHARS] + "\n... [truncated]"

        return output

    except httpx.TimeoutException:
        return f"Error: Search API timed out after {_TIMEOUT}s. Web search unavailable."
    except httpx.ConnectError:
        return "Error: Could not connect to search API. Web search unavailable."
    except Exception as e:
        return f"Error performing web search: {type(e).__name__}: {e}"
