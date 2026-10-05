from flask import Flask, render_template
from POSTS import views
from LATEST_NEWS import main 
from pathlib import Path

app = Flask(__name__)

gainers_url = 'https://www.moneycontrol.com/stocks/market-stats/top-gainers-nse'
losers_url = 'https://www.moneycontrol.com/stocks/market-stats/top-losers-nse'

BASE_DIR = Path(__file__).resolve().parent.parent
FILES_DIR = BASE_DIR / "files"
FILES_DIR.mkdir(exist_ok=True)

@app.route('/posts')
def home():
    gainers = views.scraping_of_companies(gainers_url)
    losers = views.scraping_of_companies(losers_url)
    indices = views.nifty_and_sensex(gainers_url)

    views.save_to_csv(gainers, FILES_DIR / "gainers.csv")
    views.save_to_csv(losers, FILES_DIR / "losers.csv")
    
    return render_template(
        ('templates/dashboard.html'),
        gainers=gainers,
        losers=losers,
        indices=indices,
    )


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