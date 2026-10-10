from bs4 import BeautifulSoup
from dotenv import load_dotenv
import requests, time, random, json, os
from google import genai
from google.genai import types


HEADERS = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36'}
MAX_RETRIES = 2
BACKOFF_SECONDS = 3
OVERLOAD_WAIT_SECONDS = 5
USE_SELECTION_BACKUP = False
WORLD_HEADLINES_TO_SEND = 8
model = 'gemini-3.1-flash-lite'
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, 'data')
os.makedirs(DATA_DIR, exist_ok=True)
SELECTION_BACKUP_FILE = os.path.join(DATA_DIR, 'selected_headlines_backup.json')
FETCHED_ARTICLES_BACKUP_FILE = os.path.join(DATA_DIR, 'fetched_articles_backup.json')

os.makedirs(DATA_DIR, exist_ok=True)
load_dotenv()


# ERROR HANDLING
def is_overloaded_error(e):
    """True if the error looks like a 503 / high-demand response."""
    if getattr(e, 'code', None) == 503:
        return True
    message = str(e).lower()
    return any(term in message for term in ('503', 'unavailable', 'high demand', 'overloaded'))


def is_daily_quota_error(e):
    """True for a 429 that won't clear by waiting a few seconds."""
    message = str(e)
    return '429' in message and 'PerDay' in message


def call_with_retry(func, max_retries=2, backoff_seconds=5):
    for attempt in range(1, max_retries + 2):
        try:
            return func()
        
        except Exception as e:
            print(f'Attempt {attempt}: Gemini call failed -> {e}')

            if is_daily_quota_error(e):
                print('Daily quota exhausted - retrying is pointless. Try again later or switch model.')
                return None
            
            if attempt <= max_retries:
                if is_overloaded_error(e):
                    # 5, 10, 20, 30, 30... plus up to 2s of jitter
                    wait_time = min(OVERLOAD_WAIT_SECONDS * (2 ** (attempt - 1)), 30)
                    wait_time += random.uniform(0, 2)
                else:
                    wait_time = backoff_seconds * attempt  # unchanged for other errors
                print(f'Waiting {wait_time:.1f} seconds before retrying...')
                time.sleep(wait_time)
                
    print('GIVING UP: Gemini call failed after all retries')
    return None


def fetch_with_retry(url):
    for attempt in range(1, MAX_RETRIES + 2):
        
        try:
            response = requests.get(url, headers=HEADERS, timeout=15)
            response.raise_for_status()
            return response
        
        except requests.exceptions.Timeout:
            print(f'Attempt {attempt}: {url} took too long to respond')
            
        except requests.exceptions.RequestException as e:
            print(f'Attempt {attempt}: request failed for {url} -> {e}')

            if getattr(e.response, 'status_code', None) == 403:
                print(f'GIVING UP: {url} returned 403 Forbidden - the site is refusing this request, so retrying will not help')
                return None
            
        if attempt <= MAX_RETRIES:
            wait_time = BACKOFF_SECONDS * attempt
            print(f'Waiting {wait_time} seconds before retrying...')
            time.sleep(wait_time)
            
    print(f'GIVING UP: {url} is unreachable after {MAX_RETRIES + 1} attempts')
    return None


def get_headline_list(listing_url):
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
        print(f'No ItemList JSON-LD found on {listing_url} - page structure may have changed')
        return None

    results = []
    for item in headline_list:
        headline = item.get('name', '').strip()
        url = item.get('url', '')
        
        if headline and url:
            results.append({'headline': headline, 'url': url})

    if not results:
        print(f'ItemList was found but contained no usable entries on {listing_url}')
        return None
    
    return results


def select_headlines(business_headlines, world_headlines):
    client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
    instructions = """
You will be given two JSON lists of news headlines, each item containing a
"headline" and a "url". Follow these steps exactly.

STEP 1 - For the BUSINESS list:
- Remove any headline that is about a country or economy other than India
  (for example, articles mainly about South Korea, the US, China, etc. with
  no India angle).
- From what remains, keep only headlines that are market-related: stock
  moves, indices, IPOs, earnings, RBI/economic policy, M&A, company results.
  Loosely related is acceptable.
- Exclude any headline that is an analyst recommendation or brokerage
  suggestion on a specific stock (for example, "Buy X; target of Rs Y:
  [Brokerage name]", or any headline naming a broker's buy/sell/hold call
  or price target). These are not genuine news events.
- Select up to 4 headlines from this filtered set. If fewer than 4 genuinely
  fit the criteria, select fewer rather than including a weak or unrelated
  match - but always select at least 2 if at all possible. Preserve the
  original "headline" and "url" fields exactly as given.

STEP 2 - For the WORLD list:
- Remove any headline that is completely unrelated to world affairs, such as
  human-interest or curiosity stories (for example, a story about an unusually
  old animal). Geopolitical, financial, economic, and other genuine global
  event news is acceptable and must be kept.
- From what remains, look at the headlines in order. Select up to 4 headlines
  such that no two selected headlines cover the same underlying story or topic.
  For example, "Multiple countries probing flydubai pilot..." and
  "flydubai pilot admits he was ready to crash the plane..." are the SAME
  topic (the flydubai incident) - only one of them should be selected, even
  if it means skipping ahead further down the list to find another unique topic.
- If fewer than 4 unique, relevant topics exist, select fewer rather than
  including a duplicate or unrelated headline - but always select at least 2
  if at all possible.
- Preserve the original "headline" and "url" fields exactly as given.

Return a single JSON object with exactly three keys:
"selected_national_headlines" (an array of the chosen business headline objects), "selected_international_headlines" (an array of the chosen
world headline objects), and "snapshot_headlines" (an array of exactly 5 strings). Each object in the first two arrays must contain exactly "headline" and "url". Each snapshot headline must be a rewritten one-liner
of 12 words or fewer, drawn from the selected headlines, mixing national and international stories, with every number taken exactly from the sourceheadline.
"""

    def do_call():
        response = client.models.generate_content(
            model=model, 
            contents=[
                instructions, 
                'Here is the BUSINESS headlines JSON:', 
                json.dumps(business_headlines), 
                'Here is the WORLD headlines JSON:', 
                json.dumps(world_headlines[:WORLD_HEADLINES_TO_SEND])
                ], 
            
            config=types.GenerateContentConfig(
                response_mime_type='application/json'
            ))
        
        return json.loads(response.text)
    
    return call_with_retry(do_call, max_retries=8, backoff_seconds=10)

selected_from_backup = None

ROUNDUP_HEADLINE_PATTERNS = [
    'trade setup',
    'top 10 things',
    'top 15 things',
    'things to know before',
    'before the opening bell',
    'stocks in news',
    'Q1 results',
    'Q2 results',
    'Q3 results',
    'Q4 results'
]


def get_two_national_headlines(selected_national_headlines):
    
    def is_roundup(headline):
        lowered = headline['headline'].lower()
        return any(pattern.lower() in lowered for pattern in ROUNDUP_HEADLINE_PATTERNS)

    usable = [h for h in selected_national_headlines if not is_roundup(h)]

    if len(usable) < 2:
        print('Fewer than 2 non-roundup national headlines available, falling back to include roundup-style ones')
        usable = selected_national_headlines

    return usable[:2]


def fetch_selected_articles(headline_entries):
    articles = []
    
    for entry in headline_entries:
        headline = entry['headline']
        link = entry['url']
        time.sleep(random.uniform(2, 5))
        article_response = fetch_with_retry(link)
        
        if article_response is None:
            print(f'Skipping article (could not fetch): {headline}')
            continue
        
        article_soup = BeautifulSoup(article_response.content, 'lxml')
        content_div = article_soup.find('div', class_='content_wrapper')
        
        if content_div:
            paragraphs = content_div.find_all('p')
            body = ' '.join(p.get_text(strip=True) for p in paragraphs)
            
        else:
            body = ''
            
        if len(body.strip()) < 200:
            print(f'Skipping article (no usable content extracted): {headline}')
            continue
        
        articles.append({'headline': headline, 'body': body})
        
    return articles


def summarize_bulletin(national_articles, international_articles):
    client = genai.Client()
    instructions = """
You will be given two JSON lists: "national_articles" and
"international_articles". Each item has a "headline" and a "body".

For every article in both lists, write exactly one concise bullet point
summarising it. Do not include the headline or any title for the article
anywhere in the output. Each bullet must be self-contained, naming the key
subject (person, company, country or institution) so it makes sense without
a headline above it.

The combined length of ALL bullet points across both sections must be 240
words in total, and must never exceed 240 words. Distribute the words
according to the content: an article with more substance may take a longer
bullet and a thinner article a shorter one, so individual bullet lengths
need not be equal.

Format the ENTIRE output as plain text (not JSON), structured exactly like
this:

National News

- [Bullet summary of national article 1]
- [Bullet summary of national article 2]

(...continue with one bullet for every national article actually provided -
there may be anywhere from 2 to 4 of them, do not assume there are always 4)

International News

- [Bullet summary of international article 1]
- [Bullet summary of international article 2]

(...continue with one bullet for every international article actually
provided)

Do not add any commentary, introduction, or conclusion outside this
structure. Do not wrap the output in JSON or markdown code blocks.
"""

    def do_call():
        response = client.models.generate_content(
            model=model, contents=[
                instructions, 
                'Here are the national articles:', 
                json.dumps(national_articles), 
                'Here are the international articles:', 
                json.dumps(international_articles)
            ],
            config=types.GenerateContentConfig(
                response_mime_type='application/json'
            ))
        return json.loads(response.text)

    return call_with_retry(do_call, max_retries=8, backoff_seconds=10)


def generate_daily_news():
    result = {
        "business_headlines": [],
        "two_national_headlines": [],
        "world_headlines": [],
        "bulletin": {},
        "error_message": None
    }

    # Load saved selection or scrape fresh headlines.
    if USE_SELECTION_BACKUP and os.path.exists(SELECTION_BACKUP_FILE):
        with open(SELECTION_BACKUP_FILE, "r", encoding="utf-8") as f:
            selected = json.load(f)
    else:
        business_headlines = get_headline_list(
            "https://www.moneycontrol.com/news/business/"
        )
        world_headlines = get_headline_list(
            "https://www.moneycontrol.com/world/"
        )

        if not business_headlines or not world_headlines:
            result["error_message"] = (
                "Could not fetch headlines. Please try again."
            )
            return result

        selected = select_headlines(business_headlines, world_headlines)

        if not isinstance(selected, dict):
            result["error_message"] = (
                "Could not select headlines. Please try again later."
            )
            return result

        with open(SELECTION_BACKUP_FILE, "w", encoding="utf-8") as f:
            json.dump(selected, f)

    if not isinstance(selected, dict):
        result["error_message"] = "Saved headline data is invalid."
        return result

    national_selected = selected.get("selected_national_headlines", [])
    international_selected = selected.get(
        "selected_international_headlines", []
    )

    result["business_headlines"] = national_selected
    result["two_national_headlines"] = get_two_national_headlines(
        national_selected
    )
    result["world_headlines"] = international_selected

    # Fetch full article text.
    national_articles = fetch_selected_articles(national_selected)
    international_articles = fetch_selected_articles(
        international_selected
    )

    # Save fetched articles for later summarisation retries.
    with open(FETCHED_ARTICLES_BACKUP_FILE, "w", encoding="utf-8") as f:
        json.dump({
            "national_articles": national_articles,
            "international_articles": international_articles
        }, f)

    # Generate the bulletin.
    bulletin = summarize_bulletin(
        national_articles, international_articles
    )
    
    print("Bulletin return type:", type(bulletin).__name__)
    print("Bulletin returned:", repr(bulletin)[:1500])

    if isinstance(bulletin, dict):
        result["bulletin"] = bulletin

    elif isinstance(bulletin, str) and bulletin.strip():
        result["bulletin"] = {
            "Generated Bulletin": bulletin
        }
    else:
        result["error_message"] = (
            "The summaries could not be generated. Please try again."
        )
    return result

def retry_summarization_from_backup():
    with open(FETCHED_ARTICLES_BACKUP_FILE, 'r') as f:
        backup = json.load(f)
        
    bulletin_text = summarize_bulletin(
        backup['national_articles'], 
        backup['international_articles']
        )
    
    if bulletin_text is None:
        print('Summarization failed again.')
        
    else:
        print('\n--- FINAL BULLETIN ---')
        print(bulletin_text)
        
    return bulletin_text