from bs4 import BeautifulSoup
import requests
import re
from flask import Flask, render_template, url_for


def scraping_of_companies(url):
    
    companies = []

    try:
        # html content stored in companies
        response = requests.get(url, timeout=15) #wait till 15 seconds for the server to respond, then raise a TIMEOUT exception, if it doesnt respond
        
        response.raise_for_status() #checks the status code and prevents the scraper from parsing an error page as if it were data 
        
        soup = BeautifulSoup(response.content, 'lxml')
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

                companies.append({
                    'name': name,
                    'price': price,
                    'change': price_change,
                } 
                )

    except requests.exceptions.Timeout:
        print("This website took too long to respond")
        
    except requests.exceptions.RequestException as e:
        print("Request failed: ", e)
        
    return companies


def nifty_and_sensex(url):
    indices = []
    response = requests.get(url, timeout=15)
    soup = BeautifulSoup(response.content, 'lxml')
    items= soup.find_all('div', class_=re.compile(r'^IndicesTicker_web_flexItm'))
    
    for item in items:
        name_tag = item.find('span')
        value_tag = item.find('span', class_=re.compile(r'^IndicesTicker_web_hl'))
        change_tag = item.find('span', class_=re.compile(r'^IndicesTicker_web_upDnVal'))
        
    if name_tag and value_tag and change_tag:
        name = name_tag.get_text(strip=True)
        value = value_tag.get_text(strip=True)
        change = change_tag.get_text(strip=True)
        
    indices.append({
        'name': name,
        'value': value,
        'change': change,
    })

    return indices
