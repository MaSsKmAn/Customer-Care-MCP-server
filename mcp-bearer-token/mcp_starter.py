#!/usr/bin/env python3
"""
Puch AI MCP Multi-Agent Server
- Supervisor agent routes queries to Customer Care or Web Search.
- Human-in-the-loop escalation queue.
- Bearer token auth and validate() tool required by Puch AI.
"""

import asyncio
import os
import base64
import io
from typing import Annotated
from dotenv import load_dotenv
from pydantic import BaseModel, Field, AnyUrl

# MCP libs
from fastmcp import FastMCP
from fastmcp.server.auth.providers.bearer import BearerAuthProvider, RSAKeyPair
from mcp import ErrorData, McpError
from mcp.server.auth.provider import AccessToken
from mcp.types import TextContent, ImageContent, INVALID_PARAMS, INTERNAL_ERROR

# utils
import httpx
import markdownify
import readabilipy
from bs4 import BeautifulSoup

# load env
load_dotenv()
AUTH_TOKEN = os.environ.get("AUTH_TOKEN")
MY_NUMBER = os.environ.get("MY_NUMBER")

assert AUTH_TOKEN is not None, "Please set AUTH_TOKEN in .env"
assert MY_NUMBER is not None, "Please set MY_NUMBER in .env"

# --- Auth provider (Simple Bearer token) ---
class SimpleBearerAuthProvider(BearerAuthProvider):
    def __init__(self, token: str):
        k = RSAKeyPair.generate()
        super().__init__(public_key=k.public_key, jwks_uri=None, issuer=None, audience=None)
        self.token = token

    async def load_access_token(self, token: str) -> AccessToken | None:
        if token == self.token:
            return AccessToken(
                token=token,
                client_id="puch-client",
                scopes=["*"],
                expires_at=None,
            )
        return None

# --- Utility: fetch + simplify + search ---
class Fetch:
    USER_AGENT = "Puch/1.0 (MultiAgentMCP)"
    @classmethod
    async def fetch_url(cls, url: str, user_agent: str = None, force_raw: bool = False) -> tuple[str, str]:
        ua = user_agent or cls.USER_AGENT
        async with httpx.AsyncClient(timeout=30) as client:
            try:
                resp = await client.get(url, headers={"User-Agent": ua}, follow_redirects=True)
            except httpx.HTTPError as e:
                raise McpError(ErrorData(code=INTERNAL_ERROR, message=f"Failed to fetch {url}: {e!r}"))
            if resp.status_code >= 400:
                raise McpError(ErrorData(code=INTERNAL_ERROR, message=f"Failed to fetch {url} - status {resp.status_code}"))
            content_type = resp.headers.get("content-type","")
            text = resp.text
        is_html = "text/html" in content_type
        if is_html and not force_raw:
            simplified = cls.extract_content_from_html(text)
            return simplified, ""
        return text, f"Raw content with content-type: {content_type}\n"

    @staticmethod
    def extract_content_from_html(html: str) -> str:
        try:
            ret = readabilipy.simple_json.simple_json_from_html_string(html, use_readability=True)
            if not ret or not ret.get("content"):
                return "<error>Failed to simplify page</error>"
            content = markdownify.markdownify(ret["content"], heading_style=markdownify.ATX)
            return content
        except Exception:
            return "<error>Failed to simplify page</error>"

    @staticmethod
    async def duckduckgo_search_links(query: str, max_results: int = 6) -> list[str]:
        ddg = f"https://html.duckduckgo.com/html/?q={query.replace(' ', '+')}"
        links = []
        async with httpx.AsyncClient(timeout=20) as client:
            try:
                resp = await client.get(ddg, headers={"User-Agent": Fetch.USER_AGENT})
            except httpx.HTTPError:
                return ["<error>Search failed</error>"]
            if resp.status_code != 200:
                return ["<error>Search failed</error>"]
            soup = BeautifulSoup(resp.text, "html.parser")
            for a in soup.find_all("a", class_="result__a", href=True):
                href = a["href"]
                if href.startswith("http"):
                    links.append(href)
                if len(links) >= max_results:
                    break
        return links or ["<error>No results found</error>"]

# --- MCP Server instance ---
mcp = FastMCP("Puch MultiAgent MCP Server", auth=SimpleBearerAuthProvider(AUTH_TOKEN))

# --- Required validate tool ---
@mcp.tool
async def validate() -> str:
    """Return phone number in {country_code}{number} format (no plus)."""
    return MY_NUMBER

# --- In-memory escalation queue (simple) ---
# For production, persist in DB. Each item: {"id":int,"query":str,"from":str,"priority":int,"status": "open"|"resolved", "human_response": str|None}
ESCALATION_DB: list[dict] = []
NEXT_ESCALATION_ID = 1

def _push_escalation(item: dict) -> dict:
    global NEXT_ESCALATION_ID
    item["id"] = NEXT_ESCALATION_ID
    NEXT_ESCALATION_ID += 1
    ESCALATION_DB.append(item)
    return item

# --- Customer Care Agent (FAQ + fallback) ---
async def customer_care_agent(query: str) -> str:
    # Simple FAQ mapping
    faq = {
        "refund": "Our refund policy: please request within 14 days at https://example.com/refund. Refunds processed in 5-7 business days.",
        "tracking": "To track your order use the tracking link emailed to you, or visit https://example.com/track and enter order id.",
        "cancel": "Orders can be cancelled within 2 hours of purchase from your orders page.",
        "warranty": "All electronics have a 1-year limited warranty (see https://example.com/warranty)."
    }
    q_lower = query.lower()
    for k, v in faq.items():
        if k in q_lower:
            return f"📞 Customer Care: {v}"

    # If no rule matched, escalate to human
    escalated = _push_escalation({"query": query, "from": "user", "priority": 3, "status": "open", "human_response": None})
    return f"📞 Customer Care: I couldn't confidently answer — I've created an escalation (id={escalated['id']}) for a human operator to handle."

# --- Web Search Agent (engine-specific: DuckDuckGo by default) ---
async def web_search_agent(query: str, engine: str = "duckduckgo") -> str:
    if engine.lower() in ("duckduckgo", "ddg"):
        links = await Fetch.duckduckgo_search_links(query, max_results=6)
        # For each link, return top 3 or so
        results = []
        for link in links[:4]:
            # only fetch summary for top 1-2 to avoid long latency; otherwise return URLs
            results.append(f"- {link}")
        return f"🔎 Web Search ({engine}) results for: {query}\n\n" + "\n".join(results)
    else:
        raise McpError(ErrorData(code=INVALID_PARAMS, message=f"Unsupported engine: {engine}"))

# --- Supervisor agent tool (routes and decides human involvement) ---
SupervisorDesc = {
    "description": "Supervisor routes requests between customer care and web search, and decides escalation to human operator.",
    "use_when": "Use when you want a single entrypoint for support/search tasks.",
    "side_effects": "May create escalation tickets for human operators."
}

@mcp.tool(description=SupervisorDesc)
async def supervisor(
    query: Annotated[str, Field(description="User query or problem")],
    intent: Annotated[str | None, Field(description="Optional intent hint (e.g., 'search' or 'support')")] = None,
    priority: Annotated[int, Field(description="Priority 1-5 (5 urgent)")] = 3,
    search_engine: Annotated[str | None, Field(description="Which search engine to use (default: duckduckgo)")] = None,
) -> str:
    # Immediate escalation for high priority
    if priority >= 5:
        ticket = _push_escalation({"query": query, "from": "user", "priority": priority, "status": "open", "human_response": None})
        return f"Supervisor: Urgent issue — escalated to human operator with id={ticket['id']}."

    # Intent-based routing
    il = intent.lower() if intent else ""
    ql = query.lower()
    if "search" in il or il == "web" or il == "search" or "find" in ql or "look for" in ql:
        engine = search_engine or "duckduckgo"
        return await web_search_agent(query, engine=engine)
    elif "support" in il or il == "support" or "refund" in ql or "tracking" in ql or "cancel" in ql:
        return await customer_care_agent(query)
    else:
        # default: try customer care first, if not answered it'll create an escalation automatically
        return await customer_care_agent(query)

# --- MCP tool for human operators to list/open escalations ---
HumanListDesc = {
    "description": "List current escalations (human operators only).",
    "use_when": "Use to view open escalations and their details.",
}

@mcp.tool(description=HumanListDesc)
async def list_escalations(status: Annotated[str | None, Field(description="Filter by status: open|resolved")] = None) -> str:
    rows = [e for e in ESCALATION_DB if (status is None or e["status"] == status)]
    if not rows:
        return "No escalations."
    out = []
    for e in rows:
        out.append(f"id={e['id']} | priority={e['priority']} | status={e['status']} | query={e['query']}")
    return "\n".join(out)

# --- MCP tool for human to respond to an escalation ---
HumanRespondDesc = {
    "description": "Provide a human response to an escalation ticket (resolves ticket).",
    "use_when": "Human operator uses this to reply/resolve escalations.",
}

@mcp.tool(description=HumanRespondDesc)
async def respond_escalation(ticket_id: Annotated[int, Field(description="Escalation ticket id")], human_response: Annotated[str, Field(description="Human's reply text")]) -> str:
    for e in ESCALATION_DB:
        if e["id"] == ticket_id:
            e["human_response"] = human_response
            e["status"] = "resolved"
            return f"Escalation id={ticket_id} marked resolved. Human response:\n\n{human_response}"
    raise McpError(ErrorData(code=INVALID_PARAMS, message=f"Ticket id {ticket_id} not found."))

# --- Optional: summarize_url (re-use Fetch.extract) ---
SummDesc = {
    "description": "Summarize a web page (uses readability + simple summarization by trimming).",
    "use_when": "Quick overview of article or page content.",
}
@mcp.tool(description=SummDesc)
async def summarize_url(url: Annotated[AnyUrl, Field(description="URL to summarize")], sentences: Annotated[int, Field(description="Approx. sentences")] = 3) -> str:
    content, _ = await Fetch.fetch_url(str(url))
    if content.startswith("<error>"):
        raise McpError(ErrorData(code=INTERNAL_ERROR, message="Failed to fetch content."))
    # very simple summarization: split paragraphs -> take first N sentences
    text = content.replace("\n", " ").strip()
    # naive sentence split
    sentences_list = [s.strip() for s in text.split(". ") if s.strip()]
    return ". ".join(sentences_list[:sentences]) + ("." if len(sentences_list) >= sentences else "")

# --- Run server ---
async def main():
    print("🚀 Starting Puch MultiAgent MCP server on http://0.0.0.0:8086")
    await mcp.run_async("streamable-http", host="0.0.0.0", port=8086)

if __name__ == "__main__":
    asyncio.run(main())
