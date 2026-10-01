from bs4 import BeautifulSoup
import requests
import re


# FOR GAINERS
gainers_url = 'https://www.moneycontrol.com/stocks/market-stats/top-gainers-nse/'


try:
    # html content stored in gainers
    gainers = requests.get(gainers_url, timeout=15) #wait till 15 seconds for the server to respond, then raise a TIMEOUT exception
    
    gainers.raise_for_status() #checks the status code and prevents the scraper from parsing an error page as if it were data 
    
    soup = BeautifulSoup(gainers.content, 'lxml')
    gainers_names = [] 
    # gainers.content -> raw bytes 
    # lxml -> parser
    
    table = soup.find('table', class_=re.compile(r'^MarketStatsTableWeb_tableEl'))
    gainers_name_tags = table.select('tbody h4 a')
    
    for tag in gainers_name_tags[:5]:
        name = tag.get_text(strip=True)
        gainers_names.append(name)
        
    print(gainers_names)
        
        
except requests.exceptions.Timeout:
    print("This website took too long to respond")
    
    
except requests.exceptions.RequestException as e:
    print("Request failed: ", e)
    

# FOR LOSERS
losers_url = 'https://www.moneycontrol.com/stocks/market-stats/top-losers-nse/'


try:
    # html content stored in losers
    losers = requests.get(losers_url, timeout=15) #wait till 15 seconds for the server to respond, then raise a TIMEOUT exception
    
    losers.raise_for_status() #checks the status code and prevents the scraper from parsing an error page as if it were data 
    
    soup = BeautifulSoup(losers.content, 'lxml')
    losers_names = [] 
    # losers.content -> raw bytes 
    # lxml -> parser
    
    table = soup.find('table', class_=re.compile(r'^MarketStatsTableWeb_tableEl'))
    # r'' -> raw string
    # ^ -> anchors tht matc to the start of the class name
    losers_name_tags = table.select('tbody h4 a')
    
    for tag in losers_name_tags[:5]:
        name = tag.get_text(strip=True)
        losers_names.append(name)
        
    print(losers_names)
        
        
except requests.exceptions.Timeout:
    print("This website took too long to respond")
    
    
except requests.exceptions.RequestException as e:
    print("Request failed: ", e)
    