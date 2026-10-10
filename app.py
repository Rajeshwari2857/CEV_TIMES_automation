from flask import Flask, render_template, request
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


@app.route('/latest-news', methods=['GET', 'POST'])
def latest_news():
    data = {
        "business_headlines": [],
        "two_national_headlines": [],
        "world_headlines": [],
        "bulletin": {},
        "error_message": None
    }

    if request.method == 'POST':
        data = main.generate_daily_news()

    return render_template("latest_news.html", **data)


if __name__ == '__main__':
    app.run(debug=True)