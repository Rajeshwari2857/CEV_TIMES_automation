from flask import Flask, render_template
from POSTS import views
from LATEST_NEWS import main 
from pathlib import Path
import os

app = Flask(__name__)

gainers_url = 'https://www.moneycontrol.com/stocks/market-stats/top-gainers-nse'
losers_url = 'https://www.moneycontrol.com/stocks/market-stats/top-losers-nse'


@app.route('/posts')
def home():
    gainers = views.read_from_csv('POSTS/files/gainers.csv')
    losers = views.read_from_csv('POSTS/files/losers.csv')
    
    return render_template('posts.html', gainers=gainers, losers=losers)


# update button to update manually if someone wishes to
@app.route('/posts/update-market-data')
def update_market_data_button():
    views.update_market_data()
    
    gainers = views.read_from_csv('POSTS/files/gainers.csv')
    losers = views.read_from_csv('POSTS/files/losers.csv')
    
    return render_template('posts.html', gainers=gainers, losers=losers)


@app.route('/latest_news')
def latest_news():
    business_headlines = main.get_headline_list('https://www.moneycontrol.com/news/business/')
    world_headlines = main.get_headline_list('https://www.moneycontrol.com/world/')
    
    national_selected = main.selected.get('selected_national_headlines', [])
    international_selected = main.selected.get('selected_international_headlines', [])
    
    two_national_headlines = main.get_two_national_headlines(national_selected)
    national_articles = main.fetch_selected_articles(national_selected)
    international_articles = main.fetch_selected_articles(international_selected)
    bulletin_text = main.summarize_bulletin(national_articles, international_articles)
    
    return render_template(
        'latest_news.html', 
        business_headlines=business_headlines,
        world_headlines=world_headlines,
        two_national_headlines=two_national_headlines, 
        bulletin_text=bulletin_text,
        )


if __name__ == '__main__':
    app.run(debug=True)