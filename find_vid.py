import urllib.request, re

# "stock market chart background loop 16:9"
url = "https://www.youtube.com/results?search_query=stock+market+chart+background+loop+16%3A9"
req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
try:
    html = urllib.request.urlopen(req).read().decode('utf-8')
    ids = re.findall(r'"videoId":"([^"]{11})"', html)
    print("Found:", list(set(ids))[:10])
except Exception as e: print(e)
