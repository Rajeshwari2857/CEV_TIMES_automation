from bs4 import BeautifulSoup
import requests
import re


def scraping_of_companies(url):
    
    companies_names = []
    companies_prices = []
    companies_price_change = []

    try:
        # html content stored in companies
        companies = requests.get(url, timeout=15) #wait till 15 seconds for the server to respond, then raise a TIMEOUT exception, if it doesnt respond
        
        companies.raise_for_status() #checks the status code and prevents the scraper from parsing an error page as if it were data 
        
        soup = BeautifulSoup(companies.content, 'lxml')
        # companies.content -> raw bytes 
        # lxml -> parser
        
        table = soup.find(
            'table',
            class_=re.compile(r'^MarketStatsTableWeb_tableEl')
        )

        rows = table.select('tbody tr')
        
        for row in rows[:5]:
            cells = row.select('td')

            # First column: company name
            name_tag = cells[0].select_one('h4 a')

            # Third column: current price
            price_tag = cells[2].select_one('p[class*="stkVal"]')
            
            # Inside third column: price change
            price_change_tag = cells[2].select_one('span')

            if name_tag and price_tag:
                name = name_tag.get_text(strip=True)
                price = price_tag.find(string=True, recursive=False).strip() # Extract only the direct text, excluding nested daily change
                price_change = price_change_tag.get_text(' ', strip=True)

                companies_names.append(name)
                companies_prices.append(price)
                companies_price_change.append(price_change)

    except requests.exceptions.Timeout:
        print("This website took too long to respond")
        
    except requests.exceptions.RequestException as e:
        print("Request failed: ", e)
        
    return companies_names, companies_prices, companies_price_change

