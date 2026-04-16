import urllib.request
import re

try:
    req = urllib.request.Request("https://coverr.co/videos/stock-market-charts-animation-loop--47", headers={'User-Agent': 'Mozilla/5.0'})
    html = urllib.request.urlopen(req).read().decode('utf-8')
    links = re.findall(r'https://[^"]+\.mp4[^"]*', html)
    print(list(set(links))[:5])
except Exception as e:
    print(e)
