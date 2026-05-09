"""
publish.py - GitHub Pages Publishing Module
Converts generated HTML articles and publishes to /docs folder for GitHub Pages.
"""

import os
import sqlite3
import json
import re
from datetime import datetime
from typing import List, Dict, Optional

# Paths
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DOCS_DIR = os.path.join(BASE_DIR, "docs")
ARTICLES_SRC = os.path.join(BASE_DIR, "output", "articles", "final")
ARTICLES_OUT = os.path.join(DOCS_DIR, "articles")
DB_PATH = os.path.join(BASE_DIR, "data", "tools.db")


def ensure_dirs():
    """Ensure output directories exist."""
    os.makedirs(ARTICLES_OUT, exist_ok=True)
    os.makedirs(os.path.join(DOCS_DIR, "js"), exist_ok=True)


# ============ ADSENSE PLACEHOLDER ============

def add_adsense_placeholder(html: str) -> str:
    """
    Add AdSense placeholder slots to article HTML.
    Placeholders are marked with comments for easy replacement with real ad code.
    """
    # AdSense placeholder - replace comment with actual ad code when approved
    in_article_ad = '''
    <!-- ADVERTISEMENT SLOT 1 (in-article) -->
    <div class="ad-slot in-article-ad" style="margin: 2rem 0; text-align: center;">
        <div class="ad-placeholder" style="background: #f3f4f6; padding: 1rem; border-radius: 8px; min-height: 100px;">
            <span style="color: #9ca3af; font-size: 0.75rem;">ADVERTISEMENT</span>
        </div>
    </div>
    '''

    bottom_ad = '''
    <!-- ADVERTISEMENT SLOT 2 (after article) -->
    <div class="ad-slot bottom-ad" style="margin: 2rem 0; text-align: center;">
        <div class="ad-placeholder" style="background: #f3f4f6; padding: 1rem; border-radius: 8px; min-height: 100px;">
            <span style="color: #9ca3af; font-size: 0.75rem;">ADVERTISEMENT</span>
        </div>
    </div>
    '''

    # Insert in-article ad after second paragraph
    paragraphs = html.split('</p>')
    if len(paragraphs) > 4:
        insert_pos = len(paragraphs) // 2
        paragraphs.insert(insert_pos, in_article_ad)
        html = '</p>'.join(paragraphs)
    else:
        # Add before related tools section
        html = html.replace('<div class="related-tools">', bottom_ad + '<div class="related-tools">')

    # Add CSS for ad slots if not present
    if 'ad-placeholder' not in html:
        ad_css = '''
        <style>
        .ad-slot { margin: 2rem 0; }
        .ad-placeholder { border: 1px dashed #d1d5db; }
        </style>
        '''
        html = html.replace('</head>', ad_css + '</head>')

    return html


# ============ INTERNAL LINKING (PBN) ============

def get_internal_links_for_article(tool_name: str, category: str, limit: int = 3) -> list:
    """
    Get existing articles from database for internal linking.
    Returns list of {name, url} dicts for related articles.
    """
    if not os.path.exists(DB_PATH):
        return []

    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    # Get previously generated articles (same category first, then any)
    c.execute("""
        SELECT tool_name, category
        FROM generated_content
        WHERE tool_name != ?
        ORDER BY
            CASE WHEN category = ? THEN 0 ELSE 1 END,
            generated_at DESC
        LIMIT ?
    """, (tool_name, category, limit))

    rows = c.fetchall()
    conn.close()

    links = []
    for row in rows:
        slug = row[0].lower().replace(" ", "-")
        links.append({
            "name": row[0],
            "url": f"../articles/{slug}.html",
            "category": row[1]
        })

    return links


def inject_internal_links(html: str, tool_name: str, category: str) -> str:
    """Inject internal links into the related tools section."""
    links = get_internal_links_for_article(tool_name, category)

    if not links:
        return html

    # Build the related tools HTML
    links_html = '\n    <div class="related-tools">\n        <h3>Related AI Tools</h3>\n        <ul>'
    for link in links:
        links_html += f'\n            <li><a href="{link["url"]}">{link["name"]}</a></li>'
    links_html += '\n        </ul>\n    </div>'

    # Replace existing related-tools section or add new one
    if 'related-tools' in html:
        # Find and replace existing section
        import re
        pattern = r'<div class="related-tools">.*?</div>\s*</div>'
        if re.search(pattern, html, re.DOTALL):
            html = re.sub(pattern, links_html + '\n    </div>', html, flags=re.DOTALL)
    else:
        # Add before affiliate disclosure
        html = html.replace(
            '<p class="affiliate-disclosure">',
            links_html + '\n\n    <p class="affiliate-disclosure">'
        )

    return html


# ============ HTML CLEANUP AND OPTIMIZATION ============

def cleanup_html_for_pages(html: str, tool_name: str, affiliate_link: str, category: str) -> str:
    """
    Clean and optimize generated HTML for GitHub Pages.
    - Remove absolute paths (use relative)
    - Fix internal links
    - Ensure proper base URLs
    """
    # Replace absolute /css/ and /js/ paths with relative paths
    # Since articles are in /articles/, we need ../css/ and ../js/
    html = html.replace('href="/css/', 'href="../css/')
    html = html.replace('src="/js/', 'src="../js/')

    # Add category to the article if not present
    if 'class="category-tag"' not in html and category in html:
        html = html.replace(
            '<h1>',
            f'<span class="category-tag">{category}</span>\n            <h1>'
        )

    # Update affiliate link with proper tracking
    if affiliate_link:
        html = re.sub(
            r'href="[^"]*" class="tool-link"',
            f'href="{affiliate_link}" class="tool-link"',
            html
        )

    return html


# ============ ARTICLES.JSON GENERATOR ============

def generate_articles_index(articles: List[Dict]) -> str:
    """
    Generate articles.json index file for the front-end JS.
    Format: [{name, url, category, date, excerpt}, ...]
    """
    index = []
    for article in articles:
        # Read the HTML to extract excerpt
        html_path = os.path.join(ARTICLES_OUT, article["slug"] + ".html")
        excerpt = ""

        if os.path.exists(html_path):
            with open(html_path, "r", encoding="utf-8") as f:
                content = f.read()
                # Extract first paragraph as excerpt
                p_match = re.search(r'<p>(.*?)</p>', content, re.DOTALL)
                if p_match:
                    excerpt = re.sub(r'<[^>]+>', '', p_match.group(1))[:150]

        index.append({
            "name": article["name"],
            "url": f"/articles/{article['slug']}.html",
            "category": article.get("category", "AI Tools"),
            "date": article.get("date", datetime.now().strftime("%Y-%m-%d")),
            "excerpt": excerpt
        })

    return json.dumps(index, indent=2, ensure_ascii=False)


def update_articles_json(new_articles: List[Dict]):
    """Update the articles.json index file."""
    json_path = os.path.join(DOCS_DIR, "js", "articles.json")

    # Read existing index
    existing = []
    if os.path.exists(json_path):
        with open(json_path, "r", encoding="utf-8") as f:
            try:
                existing = json.loads(f.read())
            except:
                existing = []

    # Merge with new articles (avoid duplicates by name)
    existing_names = {a["name"] for a in existing}
    for article in new_articles:
        if article["name"] not in existing_names:
            existing.insert(0, article)  # Add new articles at top

    # Write updated index
    with open(json_path, "w", encoding="utf-8") as f:
        f.write(json.dumps(existing, indent=2, ensure_ascii=False))

    return len(new_articles)


# ============ PUBLISH FROM GENERATED CONTENT ============

def publish_generated_articles() -> int:
    """
    Find and publish articles from output/articles/final folder.
    Returns number of articles published.
    """
    ensure_dirs()

    if not os.path.exists(ARTICLES_SRC):
        print("[Publish] No generated articles found in output/articles/final")
        return 0

    published = []
    files = os.listdir(ARTICLES_SRC)

    for filename in files:
        if not filename.endswith(".html"):
            continue

        src_path = os.path.join(ARTICLES_SRC, filename)

        # Read generated article
        with open(src_path, "r", encoding="utf-8") as f:
            content = f.read()

        # Extract tool name from filename or content
        tool_name = filename.replace(".html", "").replace("-", " ").title()

        # Extract category from content
        category_match = re.search(r'class="category-tag">([^<]+)</span>', content)
        category = category_match.group(1) if category_match else "AI Tools"

        # Extract affiliate link
        affiliate_match = re.search(r'href="([^"]*)" class="tool-link"', content)
        affiliate_link = affiliate_match.group(1) if affiliate_match else ""

        # Clean for GitHub Pages
        cleaned = cleanup_html_for_pages(content, tool_name, affiliate_link, category)

        # Add internal links for PBN
        cleaned = inject_internal_links(cleaned, tool_name, category)

        # Add AdSense placeholders
        cleaned = add_adsense_placeholder(cleaned)

        # Write to docs/articles/
        dst_path = os.path.join(ARTICLES_OUT, filename)
        with open(dst_path, "w", encoding="utf-8") as f:
            f.write(cleaned)

        slug = filename.replace(".html", "")
        published.append({
            "name": tool_name,
            "slug": slug,
            "category": category,
            "date": datetime.now().strftime("%Y-%m-%d"),
            "source": src_path
        })

        print(f"[Publish] {tool_name} → /articles/{filename}")

    # Update articles.json
    if published:
        count = update_articles_json(published)
        print(f"[Publish] Updated articles.json with {count} articles")

    return len(published)


# ============ STANDALONE ARTICLE GENERATION ============

def generate_single_article(tool: Dict) -> str:
    """
    Generate and publish a single article for a tool.
    Returns the output file path.
    """
    from content_engine import generate_article

    ensure_dirs()

    # Generate article using content engine
    article = generate_article(tool)
    if not article:
        return None

    # Clean and publish
    cleaned = cleanup_html_for_pages(
        article.html_content,
        article.tool_name,
        article.affiliate_link,
        article.tool_name
    )

    slug = article.tool_name.lower().replace(" ", "-")
    output_path = os.path.join(ARTICLES_OUT, f"{slug}.html")

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(cleaned)

    # Update index
    update_articles_json([{
        "name": article.tool_name,
        "slug": slug,
        "category": article.tool_name,
        "date": article.generated_at
    }])

    print(f"[Publish] Published: {output_path}")
    return output_path


# ============ MAIN ============

def main():
    print("=" * 50)
    print("AI Tool Reviews - GitHub Pages Publisher")
    print("=" * 50)

    ensure_dirs()

    # Publish any generated articles
    count = publish_generated_articles()

    if count > 0:
        print(f"\n[SUCCESS] Published {count} articles to /docs/")
        print("[NEXT] Commit and push to GitHub to deploy")
    else:
        print("\n[INFO] No new articles to publish")
        print("[TIP] Run 'python scrapper.py' to discover tools, then generate content")


if __name__ == "__main__":
    main()