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
    gainers = views.read_from_csv('files/gainers.csv')
    losers = views.read_from_csv('files/losers.csv')
    
    return render_template('templates/posts.html', gainers=gainers, losers=losers)


@app.route('/latest_news')
def latest_news():
    national_articles = main.get_articles('https://www.moneycontrol.com/news/india/', count=4)
    world_articles = main.get_articles('https://www.moneycontrol.com/world/', count=4)
    
    return render_template(
        ('templates/dashboard.html'),
        national_articles=national_articles,
        world_articles=world_articles
    )


if __name__ == '__main__':
    app.run(debug=True)