import urllib.request
import re

url = "https://www.youtube.com/results?search_query=abstract+finance+background+loop"
req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'})
try:
    html = urllib.request.urlopen(req).read().decode('utf-8')
    ids = re.findall(r'"videoId":"([^"]{11})"', html)
    print("Found IDs:")
    for vid in list(set(ids))[:10]:
        print(vid)
except Exception as e:
    print(e)
