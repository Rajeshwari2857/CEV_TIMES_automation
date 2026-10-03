from flask import Flask, render_template, url_for
from POSTS import views
from LATEST_NEWS import main

app = Flask(__name__)

gainers_url = 'https://www.moneycontrol.com/stocks/market-stats/top-gainers-nse'
losers_url = 'https://www.moneycontrol.com/stocks/market-stats/top-losers-nse'

@app.route('/posts')
def home():
    gainers = views.scraping_of_companies(gainers_url)
    losers = views.scraping_of_companies(losers_url)
    indices = views.nifty_and_sensex(gainers_url)

    return render_template(
        url_for('templates/dashboard.html'),
        gainers=gainers,
        losers=losers,
        indices=indices,
    )


@app.route('/latest_news')
def latest_news():
    national_articles = main.get_articles('https://www.moneycontrol.com/news/india/', count=4)
    world_articles = main.get_articles('https://www.moneycontrol.com/world/', count=4)
    
    return render_template(
        url_for('templates/dashboard.html'),
        national_articles=national_articles,
        world_articles=world_articles
    )


if __name__ == '__main__':
    app.run(debug=True)