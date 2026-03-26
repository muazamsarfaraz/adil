import httpx
from langchain_core.tools import tool


_SRA_API_BASE = "https://www.sra.org.uk/consumers/register/search/"
_TIMEOUT = 10.0


@tool
async def search_sra_register(name: str, firm: str = "") -> str:
    """Search the SRA (Solicitors Regulation Authority) register for a solicitor or firm.

    Args:
        name: The solicitor or firm name to search for.
        firm: Optional firm name to narrow results.

    Returns:
        SRA registration details including SRA number and regulatory status.
    """
    try:
        params: dict[str, str] = {"Words": name}
        if firm:
            params["Firm"] = firm

        async with httpx.AsyncClient(timeout=_TIMEOUT, follow_redirects=True) as client:
            response = await client.get(_SRA_API_BASE, params=params)

        if response.status_code != 200:
            return (
                f"Error: SRA API returned HTTP {response.status_code}. "
                f"Unable to verify registration for {name}. "
                "Proceeding without SRA verification."
            )

        # The SRA website returns HTML — parse for results
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(response.text, "html.parser")

        # Look for result rows
        results = []
        result_items = soup.find_all("div", class_="search-result") or soup.find_all("li", class_="result")

        if not result_items:
            # Try a broader search for table rows or any structured results
            result_items = (
                soup.find_all("tr", class_=lambda c: c and "result" in c.lower()) if soup.find("table") else []
            )

        if not result_items:
            return f"No SRA registration found for {name}" + (f" at {firm}" if firm else "")

        for item in result_items[:3]:  # Limit to top 3 results
            text = item.get_text(separator=" | ", strip=True)
            # Try to extract SRA number (typically 6-digit number)
            import re

            sra_numbers = re.findall(r"\b\d{6}\b", text)
            sra_num = sra_numbers[0] if sra_numbers else "N/A"

            results.append(f"SRA Number: {sra_num}\n" f"Details: {text[:300]}")

        if results:
            header = f"SRA Register results for '{name}'" + (f" at '{firm}'" if firm else "") + ":\n\n"
            return header + "\n---\n".join(results)

        return f"No SRA registration found for {name}" + (f" at {firm}" if firm else "")

    except httpx.TimeoutException:
        return (
            f"Error: SRA API timed out after {_TIMEOUT}s. "
            f"Unable to verify registration for {name}. "
            "Proceeding without SRA verification."
        )
    except httpx.ConnectError:
        return (
            "Error: Could not connect to the SRA register. "
            f"Unable to verify registration for {name}. "
            "Proceeding without SRA verification."
        )
    except Exception as e:
        return f"Error querying SRA register: {type(e).__name__}: {e}. " "Proceeding without SRA verification."
