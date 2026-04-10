"""
Amenify Website Scraper
Crawls key pages from amenify.com and extracts clean text content
for use as a knowledge base in the AI support bot.
"""

import requests
from bs4 import BeautifulSoup
import json
import time
import os
import re

# Pages to scrape from amenify.com
AMENIFY_PAGES = [
    ("https://amenify.com", "Homepage"),
    ("https://amenify.com/about-us", "About Us"),
    ("https://amenify.com/resident-services", "Resident Services"),
    ("https://amenify.com/cleaningservices1", "Cleaning Services"),
    ("https://amenify.com/choreservices1", "Chores Services"),
    ("https://amenify.com/handymanservices1", "Handyman Services"),
    ("https://amenify.com/professional-moving-services", "Moving Services"),
    ("https://amenify.com/movingoutservices1", "Move Out Cleaning"),
    ("https://amenify.com/groceryservices1", "Food & Grocery Services"),
    ("https://amenify.com/dog-walking-services", "Dog Walking Services"),
    ("https://amenify.com/acommerce", "ACommerce / Home Shopping"),
    ("https://amenify.com/resident-protection-plan", "Resident Protection Plan"),
    ("https://amenify.com/property-managers-2", "Property Managers"),
    ("https://amenify.com/autogifts", "Resident Gifts"),
    ("https://amenify.com/leasing-concession", "Leasing Concession"),
    ("https://amenify.com/commercialcleaning1", "Commercial Cleaning"),
    ("https://amenify.com/providers-1", "Service Pros"),
    ("https://amenify.com/amenify-platform", "API Partners / Platform"),
    ("https://amenify.com/amenify-technology", "Amenify Technology"),
]

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
}


def clean_text(text: str) -> str:
    """Remove excessive whitespace and clean up extracted text."""
    # Replace multiple newlines with double newline
    text = re.sub(r"\n{3,}", "\n\n", text)
    # Replace multiple spaces with single space
    text = re.sub(r" {2,}", " ", text)
    # Strip each line
    lines = [line.strip() for line in text.split("\n")]
    # Remove empty consecutive lines
    cleaned_lines = []
    prev_empty = False
    for line in lines:
        if not line:
            if not prev_empty:
                cleaned_lines.append("")
            prev_empty = True
        else:
            cleaned_lines.append(line)
            prev_empty = False
    return "\n".join(cleaned_lines).strip()


def extract_content(html: str, url: str) -> str:
    """Extract meaningful text content from HTML, removing nav/header/footer noise."""
    soup = BeautifulSoup(html, "html.parser")

    # Remove unwanted elements
    for tag in soup.find_all(["script", "style", "noscript", "iframe"]):
        tag.decompose()

    # Try to find main content area
    main_content = soup.find("main") or soup.find("article") or soup.find(
        "div", {"id": "page"}
    )

    if main_content:
        text = main_content.get_text(separator="\n")
    else:
        # Fallback: get body content but try to skip obvious nav/footer
        body = soup.find("body")
        if body:
            # Remove nav and footer elements
            for nav in body.find_all(["nav", "header"]):
                nav.decompose()
            # Remove elements that look like repeated navigation
            for el in body.find_all(attrs={"role": ["navigation", "banner"]}):
                el.decompose()
            text = body.get_text(separator="\n")
        else:
            text = soup.get_text(separator="\n")

    return clean_text(text)


def scrape_page(url: str, page_name: str) -> dict | None:
    """Scrape a single page and return structured document."""
    try:
        response = requests.get(url, headers=HEADERS, timeout=15)
        if response.status_code == 200:
            content = extract_content(response.text, url)
            if len(content) > 50:  # Skip nearly empty pages
                print(f"  [+] {page_name}: {len(content)} chars")
                return {
                    "url": url,
                    "page_name": page_name,
                    "content": content,
                }
            else:
                print(f"  [!] {page_name}: too little content ({len(content)} chars)")
                return None
        else:
            print(f"  [X] {page_name}: HTTP {response.status_code}")
            return None
    except Exception as e:
        print(f"  [X] {page_name}: {str(e)}")
        return None


def scrape_amenify(delay: float = 2.0) -> list[dict]:
    """
    Scrape all configured Amenify pages.

    Args:
        delay: Seconds to wait between requests to avoid rate-limiting.

    Returns:
        List of document dicts with url, page_name, and content.
    """
    print("[SCRAPER] Scraping amenify.com...")
    documents = []

    for i, (url, page_name) in enumerate(AMENIFY_PAGES):
        doc = scrape_page(url, page_name)
        if doc:
            documents.append(doc)

        # Delay between requests (skip after last)
        if i < len(AMENIFY_PAGES) - 1:
            time.sleep(delay)

    print(f"\n[DONE] Scraped {len(documents)} pages successfully.")
    return documents


def save_documents(documents: list[dict], output_path: str = None):
    """Save scraped documents to a JSON file."""
    if output_path is None:
        output_path = os.path.join(os.path.dirname(__file__), "knowledge_base.json")

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(documents, f, indent=2, ensure_ascii=False)

    print(f"[SAVED] {output_path}")
    return output_path


def load_documents(path: str = None) -> list[dict]:
    """Load previously scraped documents from JSON file."""
    if path is None:
        path = os.path.join(os.path.dirname(__file__), "knowledge_base.json")

    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


if __name__ == "__main__":
    docs = scrape_amenify()
    save_documents(docs)
