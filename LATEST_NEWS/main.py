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
SELECTION_BACKUP_FILE = os.path.join(DATA_DIR, 'selected_headlines_backup.json')
FETCHED_ARTICLES_BACKUP_FILE = os.path.join(DATA_DIR, 'fetched_articles_backup.json')

os.makedirs(DATA_DIR, exist_ok=True)


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
    load_dotenv()
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

Return a single JSON object with exactly two keys:
"selected_national_headlines" (an array of the chosen business headline
objects) and "selected_international_headlines" (an array of the chosen
world headline objects). Each object in both arrays must contain exactly
"headline" and "url".
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

if USE_SELECTION_BACKUP and os.path.exists(SELECTION_BACKUP_FILE):
    with open(SELECTION_BACKUP_FILE, 'r') as f:
        selected_from_backup = json.load(f)
    print(f'Loaded headline selection from {SELECTION_BACKUP_FILE} - skipping scrape and selection')
    business_headlines = None
    world_headlines = None

else:
    business_headlines = get_headline_list('https://www.moneycontrol.com/news/business/')
    world_headlines = get_headline_list('https://www.moneycontrol.com/world/')

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

    return [h['headline'] for h in usable[:2]]


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
            body = ' '.join((p.get_text(strip=True) for p in paragraphs))
            
        else:
            body = ''
            
        if not body or len(body.strip()) < 200:
            print(f'Skipping article (no usable content extracted): {headline}')
            continue
        
        articles.append({'headline': headline, 'body': body})
        
    return articles


def summarize_bulletin(national_articles, international_articles):
    load_dotenv()
    client = genai.Client()
    instructions = """
You will be given two JSON lists: "national_articles" and
"international_articles". Each item has a "headline" and a "body".

For every article in both lists, write a summary of no more than 50 words.
Never exceed 50 words for any single summary.

Format the ENTIRE output as plain text (not JSON), structured exactly like
this:

National News

[Headline 1]
[Summary of 50 words or fewer]

[Headline 2]
[Summary of 50 words or fewer]

(...continue for every national article actually provided - there may be
anywhere from 2 to 4 of them, do not assume there are always 4)

International News

[Headline 1]
[Summary of 50 words or fewer]

(...continue for every international article actually provided)

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
                ]
            )
        
        return response.text

    return call_with_retry(do_call, max_retries=8, backoff_seconds=10)

if selected_from_backup or (business_headlines and world_headlines):
    if selected_from_backup:
        selected = selected_from_backup
    else:
        selected = select_headlines(business_headlines, world_headlines)
        
        if selected:
            with open(SELECTION_BACKUP_FILE, 'w') as f:
                json.dump(selected, f)
            print(f'Headline selection saved to {SELECTION_BACKUP_FILE}')

    if selected is None:
        print('FATAL: Gemini headline selection failed after all retries.')
        exit()

    if selected:
        national_selected = selected.get('selected_national_headlines', [])
        international_selected = selected.get('selected_international_headlines', [])

        two_national_headlines = get_two_national_headlines(national_selected)
        print('\n--- TWO NATIONAL HEADLINES (for frontend) ---')
        print(two_national_headlines)

        national_articles = fetch_selected_articles(national_selected)
        international_articles = fetch_selected_articles(international_selected)
        print(f'\nFetched {len(national_articles)} national article(s), {len(international_articles)} international article(s)')

        with open(FETCHED_ARTICLES_BACKUP_FILE, 'w') as f:
            json.dump({
                'national_articles': national_articles, 
                'international_articles': international_articles
                }, f)

        bulletin_text = summarize_bulletin(national_articles, international_articles)
        
        if bulletin_text is None:
            print('Summarization failed, but your fetched articles are saved in fetched_articles_backup.json')
            print('You can retry just the summarization step without re-scraping.')
            
        else:
            print('\n--- FINAL BULLETIN ---')
            print(bulletin_text)
            
    else:
        print('Skipping article fetch - Gemini selection step failed')
else:
    print('Skipping Gemini selection - one or both headline lists failed to scrape')


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