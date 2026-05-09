"""
scrapper.py - AI Tool Discovery Module
Sources: Product Hunt, There's An AI For That, Hacker News
"""

import requests
from bs4 import BeautifulSoup
import sqlite3
import hashlib
import time
import re
from datetime import datetime, timezone
from typing import List, Dict, Optional
import os

DB_PATH = os.path.join(os.path.dirname(__file__), "data", "tools.db")


def init_db():
    """Initialize SQLite database for tracking discovered tools."""
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS discovered_tools (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tool_name TEXT UNIQUE NOT NULL,
            source TEXT NOT NULL,
            source_url TEXT,
            description TEXT,
            category TEXT,
            discovered_at TEXT,
            status TEXT DEFAULT 'pending',
            has_affiliate_program INTEGER DEFAULT 0,
            raw_data TEXT
        )
    """)
    # Add column if it doesn't exist (for existing databases)
    try:
        c.execute("ALTER TABLE discovered_tools ADD COLUMN has_affiliate_program INTEGER DEFAULT 0")
    except:
        pass
    conn.commit()
    return conn


def is_already_scraped(conn, tool_name: str) -> bool:
    """Check if tool was already discovered."""
    c = conn.cursor()
    c.execute("SELECT 1 FROM discovered_tools WHERE tool_name = ?", (tool_name,))
    return c.fetchone() is not None


def check_affiliate_program(tool_url: str) -> int:
    """Check if tool's website has an affiliate/partners page."""
    if not tool_url or not tool_url.startswith("http"):
        return 0

    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        }
        response = requests.get(tool_url, headers=headers, timeout=10, allow_redirects=True)

        # Look for affiliate/partner indicators in footer
        footer_text = ""

        # Try to get footer section
        soup = BeautifulSoup(response.text, "html.parser")
        footer = soup.find("footer")
        if footer:
            footer_text = footer.get_text().lower()
        else:
            # Fallback: search entire page
            footer_text = soup.get_text().lower()

        # Check for affiliate-related keywords
        affiliate_keywords = [
            "affiliate", "partners", "partner program", "referral program",
            "become a partner", "affiliate program", "partner portal"
        ]

        for keyword in affiliate_keywords:
            if keyword in footer_text:
                print(f"    [Affiliate] Found '{keyword}' on {tool_url}")
                return 1

    except Exception as e:
        print(f"    [Affiliate Check] Error checking {tool_url}: {e}")

    return 0


def insert_tool(conn, tool: Dict):
    """Insert new tool if not duplicate."""
    if is_already_scraped(conn, tool["name"]):
        return False

    # Check for affiliate program on tool's website
    has_affiliate = check_affiliate_program(tool.get("url", ""))

    c = conn.cursor()
    c.execute("""
        INSERT INTO discovered_tools
        (tool_name, source, source_url, description, category, discovered_at, has_affiliate_program, raw_data)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        tool["name"],
        tool["source"],
        tool.get("url"),
        tool.get("description"),
        tool.get("category"),
        datetime.now(timezone.utc).isoformat(),
        has_affiliate,
        str(tool.get("raw", ""))
    ))
    conn.commit()
    return True


# ============ PRODUCT HUNT SCRAPER ============

def scrape_product_hunt(limit: int = 20) -> List[Dict]:
    """Scrape trending AI tools from Product Hunt via RSS feed."""
    tools = []

    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        }

        # Product Hunt ATOM feed
        response = requests.get(
            "https://producthunt.com/feed",
            headers=headers,
            timeout=15
        )

        if response.status_code == 200:
            soup = BeautifulSoup(response.text, "xml")  # Use XML parser for ATOM

            # Find all entry items
            entries = soup.find_all("entry")
            print(f"[Product Hunt] Found {len(entries)} entries in feed")

            for entry in entries[:limit]:
                title_elem = entry.find("title")
                link_elem = entry.find("link")
                id_elem = entry.find("id")
                summary_elem = entry.find("summary")

                if title_elem and title_elem.get_text(strip=True):
                    name = title_elem.get_text(strip=True)
                    # Clean up the name
                    name = re.sub(r"\s+", " ", name).strip()

                    url = ""
                    if link_elem:
                        url = link_elem.get("href", "")

                    description = ""
                    if summary_elem:
                        description = summary_elem.get_text(strip=True)[:200]

                    tools.append({
                        "name": name,
                        "source": "producthunt",
                        "url": url,
                        "description": description,
                        "category": detect_product_category(name, description)
                    })

    except Exception as e:
        print(f"[Product Hunt] Error: {e}")

    return tools


def detect_product_category(name: str, description: str) -> str:
    """Detect category from Product Hunt tool name/description."""
    text = (name + " " + description).lower()

    categories = {
        "LLM/AI": ["gpt", "llm", "claude", "ai model", "chatbot", "assistant"],
        "Image": ["image", "photo", "generator", "art", "visual", "dall"],
        "Video": ["video", "animation", "motion", "sora", "runway"],
        "Code": ["code", "github", "programming", "developer", "cursor", "codeium"],
        "Audio": ["audio", "voice", "speech", "podcast", "music"],
        "Writing": ["writing", "content", "copy", "text", "blog", "seo"],
        "Productivity": ["productivity", "workspace", "notes", "docs", "email"],
        "Analytics": ["analytics", "data", "metrics", "dashboard", "bi"],
    }

    for cat, keywords in categories.items():
        if any(kw in text for kw in keywords):
            return cat

    return "AI Tools"


# ============ THERESANAIFORTHAT SCRAPER ============

def scrape_theresanaiforthat(limit: int = 20) -> List[Dict]:
    """Scrape AI tools from There's An AI For That."""
    tools = []

    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        }

        # Try the main page and new tools page
        urls_to_try = [
            "https://theresanaiforthat.com/",
            "https://theresanaiforthat.com/new/"
        ]

        seen_names = set()
        for url in urls_to_try:
            if len(tools) >= limit:
                break

            response = requests.get(url, headers=headers, timeout=15)

            if response.status_code == 200:
                soup = BeautifulSoup(response.text, "html.parser")

                # Look for links to individual tool pages
                for a in soup.find_all("a", href=True):
                    href = a.get("href", "")

                    # Tools pages are typically /ai-for/something
                    if "/ai-for/" in href:
                        name = a.get_text(strip=True)
                        if name and 1 < len(name) < 100 and name not in seen_names:
                            # Skip navigation links
                            if any(skip in name.lower() for skip in ["home", "about", "contact", "login", "sign", "search"]):
                                continue

                            seen_names.add(name)
                            full_url = "https://theresanaiforthat.com" + href if not href.startswith("http") else href

                            tools.append({
                                "name": name,
                                "source": "theresanaiforthat",
                                "url": full_url,
                                "description": "",
                                "category": "AI"
                            })

                            if len(tools) >= limit:
                                break

    except Exception as e:
        print(f"[There's An AI For That] Error: {e}")

    return tools


def extract_category_ai4t(card) -> str:
    """Extract category from There's An AI For That card."""
    category_elem = card.select_one(".category, .tag, [class*='category']")
    if category_elem:
        return category_elem.get_text(strip=True)
    return "AI"


# ============ HACKER NEWS SCRAPER ============

def scrape_hacker_news(limit: int = 20) -> List[Dict]:
    """Scrape AI/ML related posts from Hacker News.
    Only collects actual products/tools with their own website (not news/articles).
    """
    tools = []

    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (compatible; AI-Monitor/1.0)"
        }

        # HN Algolia API for searching AI-related posts
        search_terms = ["AI", "artificial intelligence", "machine learning", "GPT", "LLM", "neural"]

        for term in search_terms[:3]:  # Limit searches
            response = requests.get(
                "https://hn.algolia.com/api/v1/search",
                params={"query": term, "tags": "story", "hitsPerPage": limit},
                headers=headers,
                timeout=15
            )

            if response.status_code == 200:
                data = response.json()
                hits = data.get("hits", [])

                for hit in hits:
                    title = hit.get("title", "")
                    url = hit.get("url", "")

                    # FILTER: Skip if no URL (only HN comments, not products)
                    # FILTER: Skip news articles, opinions, blog posts
                    # Product indicators = has actual product URL, not just a news article
                    if not url or not url.startswith("http"):
                        # No product website, skip (this is likely just a HN discussion)
                        continue

                    # FILTER: Check if it looks like a product/tool, not a news article
                    if not is_ai_product_title(title):
                        continue

                    tools.append({
                        "name": clean_hn_title(title),
                        "source": "hackernews",
                        "url": url,
                        "description": hit.get("excerpt", ""),
                        "category": detect_ai_category(title),
                        "points": hit.get("points", 0),
                        "raw": {"hn_id": hit.get("objectID"), "author": hit.get("author")}
                    })

            time.sleep(0.5)  # Rate limit

    except Exception as e:
        print(f"[Hacker News] Error: {e}")

    return tools


def is_ai_product_title(title: str) -> bool:
    """
    Filter: Is this an AI product/tool, not a news article or opinion?
    Products have: specific names, launch/release patterns
    News have: 'is the path', 'why we need', 'how to', opinions
    """
    title_lower = title.lower()

    # Skip obvious news/opinion patterns
    news_patterns = [
        "is the path", "why we need", "how to", "opinion", "analysis",
        "what i learned", "my experience", "lessons from", "what we learned",
        "the future of", "should we", "can ai", "will ai", "is ai",
        "research", "study", "paper", "arxiv", "interview", "podcast",
        "announces", "raises", "acquires", "acquisition"
    ]

    for pattern in news_patterns:
        if pattern in title_lower:
            return False

    # Must have AI context
    ai_keywords = ["ai", "gpt", "llm", "claude", "gemini", "openai", "anthropic", "llama", "mistral"]
    has_ai = any(word in title_lower for word in ai_keywords)

    # Must suggest a specific product/tool (not just general topic)
    product_indicators = [
        "launches", "releases", "introduces", "new", "open source",
        "tool", "app", "platform", "library", "framework", "api",
        "assistant", "bot", "generator", "cloner", "writer", "coder",
        "studio", "hub", "lab", "forge", "base", "cloud"
    ]
    has_product = any(word in title_lower for word in product_indicators)

    # High-score posts often indicate popular products
    points = 0  # Points not available here but kept for future use

    return has_ai and has_product and len(title) < 120


def clean_hn_title(title: str) -> str:
    """Clean HN title to get tool name."""
    # Remove common prefixes
    clean = re.sub(r"^(Show HN:|Ask HN:|Launch HN:)\s*", "", title)

    # Remove parenthetical company names
    clean = re.sub(r"\s*\([^)]*\)\s*$", "", clean)

    # Remove "introduces X" patterns
    clean = re.sub(r"(introduces|releases|launches)\s+", "", clean, flags=re.IGNORECASE)

    return clean.strip()[:80]  # Limit length


def detect_ai_category(title: str) -> str:
    """Detect AI tool category from title."""
    title_lower = title.lower()

    categories = {
        "LLM": ["gpt", "llm", "claude", "gemini", "openai", "anthropic", "mistral", "llama"],
        "Image": ["image", "photo", "stable diffusion", "midjourney", "dall-e", "generator"],
        "Video": ["video", "sora", "runway", "animation"],
        "Code": ["code", "github", "copilot", "cursor", "programming", "developer"],
        "Audio": ["audio", "voice", "speech", "elevenlabs", "podcast"],
        "Writing": ["writing", "text", "content", "copy", "article"],
        "Research": ["research", "paper", "arxiv", "study", "science"]
    }

    for cat, keywords in categories.items():
        if any(kw in title_lower for kw in keywords):
            return cat

    return "AI"


# ============ MAIN DISCOVERY FUNCTION ============

def discover_all_tools(limit_per_source: int = 15) -> List[Dict]:
    """Run all scrapers and return new tools."""
    conn = init_db()
    all_tools = []

    print("[Discovery] Starting AI tool discovery...")

    # Product Hunt
    print("[Discovery] Scraping Product Hunt...")
    ph_tools = scrape_product_hunt(limit_per_source)
    new_count = 0
    for tool in ph_tools:
        if insert_tool(conn, tool):
            all_tools.append(tool)
            new_count += 1
    print(f"[Discovery] Product Hunt: found {len(ph_tools)}, new: {new_count}")

    # There's An AI For That
    print("[Discovery] Scraping There's An AI For That...")
    ai4t_tools = scrape_theresanaiforthat(limit_per_source)
    new_count = 0
    for tool in ai4t_tools:
        if insert_tool(conn, tool):
            all_tools.append(tool)
            new_count += 1
    print(f"[Discovery] There's An AI For That: found {len(ai4t_tools)}, new: {new_count}")

    # Hacker News
    print("[Discovery] Scraping Hacker News...")
    hn_tools = scrape_hacker_news(limit_per_source)
    new_count = 0
    for tool in hn_tools:
        if insert_tool(conn, tool):
            all_tools.append(tool)
            new_count += 1
    print(f"[Discovery] Hacker News: found {len(hn_tools)}, new: {new_count}")

    conn.close()

    print(f"[Discovery] Total new tools discovered: {len(all_tools)}")
    return all_tools


def get_pending_tools(limit: int = 10) -> List[Dict]:
    """Get tools pending content generation."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        SELECT tool_name, source, source_url, description, category, has_affiliate_program
        FROM discovered_tools
        WHERE status = 'pending'
        ORDER BY discovered_at DESC
        LIMIT ?
    """, (limit,))
    rows = c.fetchall()
    conn.close()

    return [
        {
            "name": row[0],
            "source": row[1],
            "url": row[2],
            "description": row[3],
            "category": row[4],
            "has_affiliate": row[5]
        }
        for row in rows
    ]


def mark_tool_processed(tool_name: str, status: str = "processed"):
    """Mark tool as processed."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        UPDATE discovered_tools
        SET status = ?
        WHERE tool_name = ?
    """, (status, tool_name))
    conn.commit()
    conn.close()


if __name__ == "__main__":
    # Test scrapers
    print("=" * 50)
    print("Testing AI Tool Discovery")
    print("=" * 50)

    tools = discover_all_tools(limit_per_source=10)

    print(f"\nDiscovered {len(tools)} new tools:")
    for tool in tools:
        print(f"  - [{tool['source']}] {tool['name']}")
        print(f"    URL: {tool.get('url', 'N/A')}")