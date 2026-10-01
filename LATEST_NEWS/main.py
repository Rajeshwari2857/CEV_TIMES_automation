from bs4 import BeautifulSoup
import requests
import time
import random
import json

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
}

MAX_RETRIES = 2          
BACKOFF_SECONDS = 3       


def fetch_with_retry(url):
    """
    Fetches a URL, retrying with a longer wait each time it fails.
    Returns the response object if successful, or None if it never worked.
    """
    for attempt in range(1, MAX_RETRIES + 2): 
        try:
            response = requests.get(url, headers=HEADERS, timeout=15)
            response.raise_for_status()
            return response

        except requests.exceptions.Timeout:
            print(f"Attempt {attempt}: {url} took too long to respond")

        except requests.exceptions.RequestException as e:
            print(f"Attempt {attempt}: request failed for {url} -> {e}")

        if attempt <= MAX_RETRIES:
            wait_time = BACKOFF_SECONDS * attempt
            print(f"Waiting {wait_time} seconds before retrying...")
            time.sleep(wait_time)

    print(f"GIVING UP: {url} is unreachable after {MAX_RETRIES + 1} attempts")
    return None


def get_headline_list(listing_url, count=4):
    """
    Moneycontrol embeds a hidden JSON block (JSON-LD, meant for search engines)
    on its news listing pages, containing every headline + article URL on the
    page in order. This is far more reliable than hunting for the right <a>
    tag in the visible HTML, since it rarely changes even if the page's visual
    design does.

    Returns a list of {"headline": ..., "url": ...} dicts, or None on failure.
    """
    listing_response = fetch_with_retry(listing_url)
    if listing_response is None:
        return None

    soup = BeautifulSoup(listing_response.content, 'lxml')

    script_tags = soup.find_all('script', type='application/ld+json')

    headline_list = None
    for tag in script_tags:
        try:
            data = json.loads(tag.string)
        except (json.JSONDecodeError, TypeError):
            continue 

        if isinstance(data, dict):
            candidates = [data]
        elif isinstance(data, list):
            candidates = data
        else:
            continue

        for candidate in candidates:
            if isinstance(candidate, dict) and candidate.get('@type') == 'ItemList':
                headline_list = candidate.get('itemListElement', [])
                break

        if headline_list:
            break

    if not headline_list:
        print(f"No ItemList JSON-LD found on {listing_url} - page structure may have changed")
        return None

    results = []
    for item in headline_list[:count]:
        headline = item.get('name', '').strip()
        url = item.get('url', '')
        if headline and url:
            results.append({"headline": headline, "url": url})

    if not results:
        print(f"ItemList was found but contained no usable entries on {listing_url}")
        return None

    return results


def get_articles(listing_url, count=4):
    """
    Gets the top `count` headlines + URLs from a Moneycontrol listing page
    (via JSON-LD), then visits each article page to extract its date and
    full body text.

    Returns None if the listing page itself could not be reached or had
    no usable headlines.
    """
    headline_entries = get_headline_list(listing_url, count=count)
    if headline_entries is None:
        return None 

    articles = []

    for entry in headline_entries:
        headline = entry["headline"]
        link = entry["url"]

        time.sleep(random.uniform(2, 5))

        article_response = fetch_with_retry(link)
        if article_response is None:
            print(f"Skipping article (could not fetch): {headline}")
            continue  

        article_soup = BeautifulSoup(article_response.content, 'lxml')

        date_tag = article_soup.find('div', class_='article_schedule')
        date = date_tag.get_text(strip=True) if date_tag else "Date not found"

        content_div = article_soup.find('div', class_='content_wrapper')
        if content_div:
            paragraphs = content_div.find_all('p')
            body = " ".join(p.get_text(strip=True) for p in paragraphs)
        else:
            body = ""

        if not body or len(body.strip()) < 200:
            print(f"Skipping article (no usable content extracted): {headline}")
            continue

        articles.append({
            "headline": headline,
            "date": date,
            "url": link,
            "body": body
        })

    if not articles:
        print(f"No usable articles extracted from {listing_url}")
        return None

    return articles


national_articles = get_articles('https://www.moneycontrol.com/news/india/', count=4)
print("\n--- NATIONAL ARTICLES ---")
print(national_articles)

world_articles = get_articles('https://www.moneycontrol.com/world/', count=4)
print("\n--- WORLD ARTICLES ---")
print(world_articles)