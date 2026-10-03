"""Team-name normalization between The Odds API, ESPN and nflverse."""
import json, os, re, unicodedata
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NFL = {"Arizona Cardinals":"ARI","Atlanta Falcons":"ATL","Baltimore Ravens":"BAL","Buffalo Bills":"BUF","Carolina Panthers":"CAR",
"Chicago Bears":"CHI","Cincinnati Bengals":"CIN","Cleveland Browns":"CLE","Dallas Cowboys":"DAL","Denver Broncos":"DEN","Detroit Lions":"DET",
"Green Bay Packers":"GB","Houston Texans":"HOU","Indianapolis Colts":"IND","Jacksonville Jaguars":"JAX","Kansas City Chiefs":"KC",
"Las Vegas Raiders":"LV","Los Angeles Chargers":"LAC","Los Angeles Rams":"LA","Miami Dolphins":"MIA","Minnesota Vikings":"MIN",
"New England Patriots":"NE","New Orleans Saints":"NO","New York Giants":"NYG","New York Jets":"NYJ","Philadelphia Eagles":"PHI",
"Pittsburgh Steelers":"PIT","San Francisco 49ers":"SF","Seattle Seahawks":"SEA","Tampa Bay Buccaneers":"TB","Tennessee Titans":"TEN",
"Washington Commanders":"WAS"}
ALIAS = {"appalachianstatemountaineers":"appstatemountaineers","hawaiirainbowwarriors":"hawaiirainbowwarriors",
"louisianaragincajuns":"louisianaragincajuns","southernmississippigoldeneagles":"southernmissgoldeneagles",
"samhoustonstatebearkats":"samhoustonbearkats","umassminutemen":"massachusettsminutemen","sanjosestatespartans":"sanjosestatespartans",
"citadelbulldogs":"thecitadelbulldogs","youngstownstpenguins":"youngstownstatepenguins","liusharks":"longislanduniversitysharks",
"mcneesestatecowboys":"mcneesecowboys","nichollsstatecolonels":"nichollscolonels","gramblingstatetigers":"gramblingtigers",
"gardnerwebbrunninbulldogs":"gardnerwebbrunninbulldogs","southernuniversityjaguars":"southernjaguars","williamandmarytribe":"williammarytribe",
"stfrancispaedflash":"saintfrancisredflash","stfrancisparedflash":"saintfrancisredflash","houstonbaptisthuskies":"houstonchristianhuskies",
"utriograndevalleyvaqueros":"utrgvvaqueros","southeasternlouisianalions":"selouisianalions"}

def norm(s):
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    s = re.sub(r"[^a-z0-9]", "", s.lower())
    return ALIAS.get(s, s)

_ESPN = None
def espn_cfb_id_to_norm():
    global _ESPN
    if _ESPN is None:
        d = json.load(open(os.path.join(ROOT, "data/history/espn_cfb_teams_all.json")))
        _ESPN = {t["team"]["id"]: norm(t["team"]["displayName"]) for t in d["sports"][0]["leagues"][0]["teams"]}
    return _ESPN
