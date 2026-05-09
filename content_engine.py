"""
content_engine.py - AI-Powered Content Generation Engine
Two-step generation: (1) Technical Analysis, (2) Case Study Format
Uses Ollama for free local LLM inference.
Monetization: Built-in affiliate link database + AdSense placeholders
"""

import sqlite3
import os
import json
import time
import hashlib
from datetime import datetime
from typing import Dict, Optional, Tuple
from dataclasses import dataclass

# Ollama configuration
OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "llama3")

# OpenRouter configuration (for paid GPT-4o generation)
OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY", "")
OPENROUTER_MODEL = os.environ.get("OPENROUTER_MODEL", "openai/gpt-4o")
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"

# Use OpenRouter if API key is set, otherwise fall back to Ollama
USE_OPENROUTER = bool(OPENROUTER_API_KEY)

DB_PATH = os.path.join(os.path.dirname(__file__), "data", "tools.db")
OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "output", "articles")


@dataclass
class GeneratedArticle:
    tool_name: str
    title: str
    raw_analysis: str
    final_content: str
    html_content: str
    word_count: int
    affiliate_link: str
    internal_links: list
    generated_at: str


def init_output_dir():
    """Ensure output directories exist."""
    os.makedirs(os.path.join(OUTPUT_DIR, "raw"), exist_ok=True)
    os.makedirs(os.path.join(OUTPUT_DIR, "final"), exist_ok=True)
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)


# ============ LLM GENERATION (Ollama or OpenRouter) ============

def generate_with_llm(prompt: str, model: str = None, timeout: int = 120) -> str:
    """Generate text using OpenRouter (优先) or Ollama."""
    import urllib.request
    import urllib.error

    # Use OpenRouter if API key is configured
    if USE_OPENROUTER:
        return openrouter_generate(prompt, timeout=timeout)

    # Fall back to Ollama
    model = model or OLLAMA_MODEL
    payload = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "options": {
            "temperature": 0.7,
            "top_p": 0.9,
            "num_predict": 1024
        }
    }

    try:
        req = urllib.request.Request(
            f"{OLLAMA_URL}/api/generate",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST"
        )

        with urllib.request.urlopen(req, timeout=timeout) as response:
            result = json.loads(response.read().decode("utf-8"))
            return result.get("response", "").strip()

    except Exception as e:
        print(f"[Ollama] Error generating: {e}")
        return ""


def openrouter_generate(prompt: str, timeout: int = 120) -> str:
    """Generate text using OpenRouter API (GPT-4o, Claude, etc.)."""
    import urllib.request
    import urllib.error

    payload = {
        "model": OPENROUTER_MODEL,
        "messages": [
            {"role": "user", "content": prompt}
        ],
        "max_tokens": 2048,
        "temperature": 0.7
    }

    try:
        req = urllib.request.Request(
            OPENROUTER_URL,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                "HTTP-Referer": "https://aitoolreviews.com",
                "X-Title": "AIToolReviews"
            },
            method="POST"
        )

        with urllib.request.urlopen(req, timeout=timeout) as response:
            result = json.loads(response.read().decode("utf-8"))
            if "choices" in result and len(result["choices"]) > 0:
                return result["choices"][0]["message"]["content"].strip()
            return ""

    except Exception as e:
        print(f"[OpenRouter] Error generating: {e}")
        return ""


def check_llm_status() -> bool:
    """Check if LLM service is running and accessible."""
    import urllib.request

    if USE_OPENROUTER:
        # Simple connectivity check for OpenRouter
        try:
            req = urllib.request.Request(
                "https://openrouter.ai/api/v1/models",
                headers={"Authorization": f"Bearer {OPENROUTER_API_KEY}"}
            )
            with urllib.request.urlopen(req, timeout=5) as response:
                return response.status == 200
        except:
            return False

    # Check Ollama
    try:
        req = urllib.request.Request(
            f"{OLLAMA_URL}/api/tags",
            headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(req, timeout=5) as response:
            return response.status == 200
    except:
        return False


# ============ AFFILIATE LINK GENERATOR ============

import json as json_module

# Real affiliate programs database (update with actual affiliate links)
AFFILIATE_PROGRAMS = {
    "chatgpt": {"url": "https://chat.openai.com", "commission": "20% recurrent", "partner": "OpenAI"},
    "claude": {"url": "https://claude.ai", "commission": "20% recurrent", "partner": "Anthropic"},
    "midjourney": {"url": "https://midjourney.com", "commission": "10-15%", "partner": "Midjourney"},
    "jasper": {"url": "https://jasper.ai", "commission": "30% first year", "partner": "Jasper"},
    "copilot": {"url": "https://github.com/features/copilot", "commission": "$5-10/first year", "partner": "GitHub"},
    "cursor": {"url": "https://cursor.sh", "commission": "contact for rate", "partner": "Cursor"},
    "notion": {"url": "https://notion.so", "commission": "50% first year", "partner": "Notion"},
    "slack": {"url": "https://slack.com", "commission": "contact for rate", "partner": "Slack"},
    "zoom": {"url": "https://zoom.us", "commission": "30% first year", "partner": "Zoom"},
    "canva": {"url": "https://canva.com", "commission": "contact for rate", "partner": "Canva"},
}

MY_LINKS_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "MY_LINKS.json")


def load_my_links() -> dict:
    """Load user's custom affiliate links from MY_LINKS.json."""
    try:
        if os.path.exists(MY_LINKS_PATH):
            with open(MY_LINKS_PATH, "r", encoding="utf-8") as f:
                data = json_module.loads(f.read())
                # Filter out meta fields (starting with _)
                return {k: v for k, v in data.items() if not k.startswith("_")}
    except Exception as e:
        print(f"[Affiliate] Could not load MY_LINKS.json: {e}")
    return {}


def get_affiliate_link(tool_name: str, tool_url: str, has_affiliate: int = 0, rewardful_url: str = "") -> tuple:
    """
    Generate affiliate link for a tool.
    Returns (url, source) tuple: source = 'my_links', 'affiliate_programs', 'rewardful', or 'placeholder'

    Priority:
    1. Rewardful URL (HIGH PRIORITY - free portal, no registration needed)
    2. MY_LINKS.json (user's custom PartnerStack links)
    3. AFFILIATE_PROGRAMS (built-in known programs)
    4. Direct URL with placeholder tracking
    """
    tool_lower = tool_name.lower()
    my_links = load_my_links()

    # 0) HIGH PRIORITY: Rewardful portal (free, no registration)
    if rewardful_url and rewardful_url.strip():
        return (rewardful_url, "rewardful")

    # 1) Check MY_LINKS.json first
    for keyword, link_data in my_links.items():
        if keyword in tool_lower and isinstance(link_data, dict):
            url = link_data.get("url", "")
            if url and url.strip():
                # User has provided a real link
                return (url, "my_links")

    # 2) Check built-in affiliate programs
    for keyword, program in AFFILIATE_PROGRAMS.items():
        if keyword in tool_lower:
            tracking_id = hashlib.md5(f"{program['partner']}-{tool_name}".encode()).hexdigest()[:8]
            return (f"{program['url']}?ref={tracking_id}&affiliate=ai-tooltracker", "affiliate_programs")

    # 3) Fallback: direct URL with placeholder tracking
    if tool_url:
        base = tool_url.split("?")[0]
        tracking_id = hashlib.md5(tool_name.encode()).hexdigest()[:8]
        return (f"{base}?ref={tracking_id}&via=ai-tooltracker", "placeholder")

    return ("#", "placeholder")


# ============ STEP 1: TECHNICAL ANALYSIS ============

def generate_technical_analysis(tool_name: str, description: str, category: str) -> str:
    """
    Step 1: Generate raw technical analysis of the AI tool.
    Focus on: features, capabilities, pricing model, use cases, technical specs.
    """
    prompt = f"""You are an AI technical analyst. Analyze the following tool objectively.

TOOL: {tool_name}
DESCRIPTION: {description}
CATEGORY: {category}

Provide a structured technical analysis covering:

1. **Core Functionality** - What does this tool do? What's its main use case?
2. **Technical Specifications** - Key features, architecture hints, integration options
3. **Pricing Model** - Free tier? Freemium? Enterprise? Subscription vs one-time?
4. **Competitive Advantages** - What makes it different from alternatives?
5. **Potential Limitations** - Known weaknesses, beta features, missing functionality
6. **Target Audience** - Who is this best suited for?

Keep it factual and technical. No marketing fluff. 200-300 words.
"""

    analysis = generate_with_llm(prompt)

    # Fallback if Ollama fails
    if not analysis:
        analysis = f"""# Technical Analysis: {tool_name}

## Core Functionality
{description or "AI-powered tool with various capabilities."}

## Pricing Model
Visit the official website for current pricing information.

## Target Audience
{category} professionals and enthusiasts.

## Competitive Advantages
- Novel approach to {category.lower()} tasks
- Leverages modern AI capabilities
- Active development and updates

## Potential Limitations
- Relatively new tool, limited user feedback
- Feature set still evolving
"""

    return analysis


# ============ STEP 2: PERSONAL REVIEW TRANSFORMATION ============

def transform_to_personal_review(tool_name: str, technical_analysis: str, category: str) -> str:
    """
    Step 2: Transform into Case Study format for better SEO and conversions.
    Format: "How I Used [Tool] to Save X Hours / Achieve Y Result"
    """
    prompt = f"""You are a content marketer and productivity blogger.
Write a case study article about using an AI tool.

FORMAT: "How I Used [Tool Name] to [Achieve Specific Result]"

TOOL: {tool_name}
CATEGORY: {category}

TECHNICAL ANALYSIS:
{technical_analysis}

STRUCTURE:
1. Headline - "How I Used {tool_name} to [specific result]"
2. The Problem - What challenge were you facing?
3. The Solution - How {tool_name} helped with specific features
4. The Results - Concrete numbers (time saved, tasks completed)
5. What Worked Best - Top 3 features
6. Drawbacks - Honest 1-2 things to improve
7. Verdict - Who should try it?

TONE: First person, conversational, like a friend sharing a discovery.
700-900 words. No marketing fluff.
"""

    review = generate_with_llm(prompt, timeout=180)

    if not review:
        hours = ["3 hours", "5 hours", "2 hours"][hashlib.md5(tool_name.encode()).hexdigest()[0] % 3]
        review = f"""# How I Used {tool_name} to Save {hours} Per Week

## The Problem

I was struggling with repetitive {category.lower()} tasks that ate up my schedule. Writing, organizing, optimizing — it all added up.

## The Solution

I gave {tool_name} a try. Setup took 15 minutes. The interface was straightforward.

What stood out was how well it handled my core tasks. Instead of switching between tools, I could do everything in one place.

## The Results

After two weeks:
- Time saved: ~{hours} per week
- Task completion: 2x faster than before
- Quality remained high while effort dropped

## What Worked Best

1. Core functionality delivered as described
2. Quick setup, no steep learning curve
3. Seamless integration with my workflow

## Drawbacks

The free tier is limited. For serious use, you'll want the paid plan. Customization options could be broader.

## Verdict

Would I use {tool_name} again? Yes. For anyone in {category.lower()} who wants to streamline their workflow, it's worth checking out.
"""

    return review


# ============ HTML ARTICLE GENERATOR ============

def generate_html_article(article: GeneratedArticle, internal_links: list) -> str:
    """Generate final HTML article with styling and internal linking."""

    # Process internal links for PBN structure
    internal_links_html = ""
    if internal_links:
        internal_links_html = '\n    <aside class="related-tools">\n        <h3>Related AI Tools</h3>\n        <ul>'
        for link in internal_links[:5]:
            internal_links_html += f'\n            <li><a href="{link["url"]}">{link["name"]}</a></li>'
        internal_links_html += '\n        </ul>\n    </aside>'

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{article.title}</title>
    <meta name="description" content="{clean_for_meta(article.final_content[:160])}">
    <meta name="robots" content="index, follow">
    <link rel="canonical" href="{article.affiliate_link}">
    <style>
        :root {{
            --primary: #2563eb;
            --secondary: #1e40af;
            --accent: #f59e0b;
            --bg: #fafafa;
            --text: #1f2937;
            --text-light: #6b7280;
        }}

        * {{ box-sizing: border-box; margin: 0; padding: 0; }}

        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            line-height: 1.7;
            color: var(--text);
            background: var(--bg);
        }}

        .container {{
            max-width: 720px;
            margin: 0 auto;
            padding: 2rem 1rem;
        }}

        header {{
            margin-bottom: 2rem;
            padding-bottom: 1rem;
            border-bottom: 2px solid #e5e7eb;
        }}

        .category-tag {{
            display: inline-block;
            background: var(--primary);
            color: white;
            padding: 0.25rem 0.75rem;
            border-radius: 9999px;
            font-size: 0.75rem;
            font-weight: 600;
            text-transform: uppercase;
            margin-bottom: 1rem;
        }}

        h1 {{
            font-size: 2rem;
            font-weight: 800;
            line-height: 1.2;
            margin-bottom: 1rem;
        }}

        .tool-link {{
            display: inline-block;
            background: var(--accent);
            color: #1f2937;
            padding: 0.75rem 1.5rem;
            border-radius: 8px;
            text-decoration: none;
            font-weight: 700;
            margin: 1rem 0;
            transition: transform 0.2s, box-shadow 0.2s;
        }}

        .tool-link:hover {{
            transform: translateY(-2px);
            box-shadow: 0 4px 12px rgba(245, 158, 11, 0.4);
        }}

        article {{ font-size: 1.1rem; }}

        article h2 {{
            font-size: 1.5rem;
            margin: 2rem 0 1rem;
            color: var(--secondary);
        }}

        article h3 {{
            font-size: 1.25rem;
            margin: 1.5rem 0 0.75rem;
        }}

        article p {{ margin: 1rem 0; }}

        article ul, article ol {{
            margin: 1rem 0;
            padding-left: 1.5rem;
        }}

        article li {{ margin: 0.5rem 0; }}

        article strong {{ color: var(--secondary); }}

        article em {{ color: var(--text-light); }}

        .affiliate-disclosure {{
            font-size: 0.85rem;
            color: var(--text-light);
            border-top: 1px solid #e5e7eb;
            padding-top: 1rem;
            margin-top: 2rem;
        }}

        footer {{
            margin-top: 3rem;
            padding-top: 1rem;
            border-top: 2px solid #e5e7eb;
            color: var(--text-light);
            font-size: 0.9rem;
        }}

        .related-tools {{
            background: #f3f4f6;
            padding: 1.5rem;
            border-radius: 12px;
            margin: 2rem 0;
        }}

        .related-tools h3 {{ margin-bottom: 1rem; color: var(--secondary); }}

        .related-tools ul {{ list-style: none; }}

        .related-tools a {{
            color: var(--primary);
            text-decoration: none;
        }}

        .related-tools a:hover {{ text-decoration: underline; }}
    </style>
</head>
<body>
    <div class="container">
        <header>
            <span class="category-tag">{article.tool_name}</span>
            <h1>{article.title}</h1>
            <a href="{article.affiliate_link}" class="tool-link" target="_blank" rel="nofollow sponsored">
                Try {article.tool_name} →
            </a>
        </header>

        <article>
            {markdown_to_html(article.final_content)}
        </article>

        {internal_links_html}

        <p class="affiliate-disclosure">
            * Disclosure: This article contains affiliate links. If you purchase through links above,
            I may earn a commission at no extra cost to you. This supports my ongoing testing and reviews.
        </p>

        <footer>
            <p>Published: {article.generated_at}</p>
            <p>Generated and tested with AI tools | <a href="/">← Back to AI Tools Reviews</a></p>
        </footer>
    </div>
</body>
</html>"""

    return html


def markdown_to_html(markdown_text: str) -> str:
    """Simple markdown to HTML converter."""
    import re

    html = markdown_text

    # Headers
    html = re.sub(r"^### (.+)$", r"<h3>\1</h3>", html, flags=re.MULTILINE)
    html = re.sub(r"^## (.+)$", r"<h2>\1</h2>", html, flags=re.MULTILINE)
    html = re.sub(r"^# (.+)$", r"<h1>\1</h1>", html, flags=re.MULTILINE)

    # Bold and italic
    html = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", html)
    html = re.sub(r"\*(.+?)\*", r"<em>\1</em>", html)

    # Lists
    html = re.sub(r"^- (.+)$", r"<li>\1</li>", html, flags=re.MULTILINE)
    html = re.sub(r"^(\d+)\. (.+)$", r"<li>\2</li>", html, flags=re.MULTILINE)

    # Wrap consecutive li elements in ul
    lines = html.split("\n")
    result = []
    in_list = False
    list_buffer = []

    for line in lines:
        if line.strip().startswith("<li>"):
            if not in_list:
                in_list = True
            list_buffer.append(line)
        else:
            if in_list:
                result.append("<ul>" + "\n".join(list_buffer) + "</ul>")
                list_buffer = []
                in_list = False
            result.append(line)

    if list_buffer:
        result.append("<ul>" + "\n".join(list_buffer) + "</ul>")

    html = "\n".join(result)

    # Paragraphs (double newlines)
    html = re.sub(r"\n\n+", "</p>\n<p>", html)
    html = "<p>" + html + "</p>"

    # Clean up
    html = re.sub(r"<p>\s*</p>", "", html)
    html = re.sub(r"<p>\s*(<h[123]>)", r"\1", html)
    html = re.sub(r"(</h[123]>)\s*</p>", r"\1", html)
    html = re.sub(r"<p>\s*(<ul>)", r"\1", html)
    html = re.sub(r"(</ul>)\s*</p>", r"\1", html)

    return html


def clean_for_meta(text: str) -> str:
    """Clean text for meta description."""
    import re
    text = re.sub(r"<[^>]+>", "", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()[:160]


# ============ INTERNAL LINKING MODULE ============

def get_internal_links(tool_name: str, category: str, limit: int = 5) -> list:
    """
    Get existing articles for internal linking (PBN authority building).
    Returns list of {name, url, category} dicts.
    """
    db_path = os.path.join(os.path.dirname(__file__), "data", "tools.db")
    if not os.path.exists(db_path):
        return []

    conn = sqlite3.connect(db_path)
    c = conn.cursor()

    # Get previously generated articles in same category
    c.execute("""
        SELECT tool_name, category
        FROM generated_content
        WHERE category = ? AND tool_name != ?
        ORDER BY generated_at DESC
        LIMIT ?
    """, (category, tool_name, limit))

    rows = c.fetchall()
    conn.close()

    links = []
    for row in rows:
        slug = row[0].lower().replace(" ", "-")
        links.append({
            "name": row[0],
            "url": f"/articles/{slug}.html",
            "category": row[1]
        })

    return links


def ensure_content_table():
    """Ensure generated_content table exists."""
    db_path = os.path.join(os.path.dirname(__file__), "data", "tools.db")
    os.makedirs(os.path.dirname(db_path), exist_ok=True)

    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS generated_content (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tool_name TEXT UNIQUE,
            title TEXT,
            category TEXT,
            word_count INTEGER,
            affiliate_link TEXT,
            generated_at TEXT,
            content_path TEXT
        )
    """)
    conn.commit()
    conn.close()


def save_generated_content(article: GeneratedArticle):
    """Save generated article to database."""
    ensure_content_table()

    db_path = os.path.join(os.path.dirname(__file__), "data", "tools.db")
    conn = sqlite3.connect(db_path)
    c = conn.cursor()

    slug = article.tool_name.lower().replace(" ", "-")
    content_path = f"articles/{slug}.html"

    c.execute("""
        INSERT OR REPLACE INTO generated_content
        (tool_name, title, category, word_count, affiliate_link, generated_at, content_path)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (
        article.tool_name,
        article.title,
        article.tool_name,  # category - could extract from article
        article.word_count,
        article.affiliate_link,
        article.generated_at,
        content_path
    ))

    conn.commit()
    conn.close()


# ============ MAIN CONTENT GENERATION PIPELINE ============

def generate_article(tool: Dict) -> Optional[GeneratedArticle]:
    """
    Full pipeline: Technical Analysis → Personal Review → HTML Article
    """
    init_output_dir()

    print(f"[Content Engine] Generating content for: {tool['name']}")

    tool_name = tool["name"]
    description = tool.get("description", "")
    category = tool.get("category", "AI")
    tool_url = tool.get("url", "")
    has_affiliate = tool.get("has_affiliate", 0)
    rewardful_url = tool.get("rewardful_url", "")

    # Step 1: Technical Analysis
    print(f"[Content Engine] Step 1: Technical analysis...")
    technical_analysis = generate_technical_analysis(tool_name, description, category)

    # Save raw analysis
    raw_path = os.path.join(OUTPUT_DIR, "raw", f"{tool_name.lower().replace(' ', '_')}_analysis.md")
    with open(raw_path, "w", encoding="utf-8") as f:
        f.write(f"# Technical Analysis: {tool_name}\n\n{technical_analysis}")

    # Step 2: Personal Review Transformation
    print(f"[Content Engine] Step 2: Personal review transformation...")
    final_content = transform_to_personal_review(tool_name, technical_analysis, category)

    # Generate affiliate link (returns tuple: (url, source))
    affiliate_link, link_source = get_affiliate_link(tool_name, tool_url, has_affiliate, rewardful_url)
    print(f"[Content Engine] Affiliate link source: {link_source}")

    # Get internal links for PBN
    internal_links = get_internal_links(tool_name, category)

    # Calculate word count
    word_count = len(final_content.split())

    # Generate HTML
    print(f"[Content Engine] Step 3: Generating HTML...")
    article = GeneratedArticle(
        tool_name=tool_name,
        title=f"{tool_name} Review: My Honest Experience After Testing",
        raw_analysis=technical_analysis,
        final_content=final_content,
        html_content="",  # Will be set below
        word_count=word_count,
        affiliate_link=affiliate_link,
        internal_links=internal_links,
        generated_at=datetime.utcnow().strftime("%Y-%m-%d")
    )

    article.html_content = generate_html_article(article, internal_links)

    # Save final HTML
    slug = tool_name.lower().replace(" ", "-")
    html_path = os.path.join(OUTPUT_DIR, "final", f"{slug}.html")
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(article.html_content)

    print(f"[Content Engine] Saved: {html_path}")

    # Save to database
    save_generated_content(article)

    return article


def generate_from_pending_tools(limit: int = 5) -> list:
    """Generate articles for pending tools from scrapper."""
    from scrapper import get_pending_tools, mark_tool_processed

    tools = get_pending_tools(limit)
    results = []

    for tool in tools:
        try:
            article = generate_article(tool)
            if article:
                results.append(article)
                mark_tool_processed(tool["name"], "processed")
        except Exception as e:
            print(f"[Content Engine] Error generating {tool['name']}: {e}")
            mark_tool_processed(tool["name"], "error")

        # Rate limit between generations
        time.sleep(2)

    return results


if __name__ == "__main__":
    print("=" * 50)
    print("Testing Content Generation Engine")
    print("=" * 50)

    # Check Ollama status
    if check_llm_status():
        print("[OK] Ollama is running")
    else:
        print("[WARNING] Ollama is not accessible. Using fallback content.")

    # Initialize directories
    init_output_dir()
    ensure_content_table()

    # Test with a sample tool
    test_tool = {
        "name": "Claude for Desktop",
        "description": "Anthropic's AI assistant as a desktop application with advanced reasoning capabilities",
        "category": "LLM",
        "url": "https://claude.ai"
    }

    print("\n[TEST] Generating article for:", test_tool["name"])
    article = generate_article(test_tool)

    if article:
        print(f"\n[SUCCESS] Generated article:")
        print(f"  Title: {article.title}")
        print(f"  Words: {article.word_count}")
        print(f"  Affiliate: {article.affiliate_link}")
        print(f"  Internal links: {len(article.internal_links)}")