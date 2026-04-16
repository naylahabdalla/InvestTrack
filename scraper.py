import urllib.request
import re

url = "https://www.pexels.com/search/videos/stock%20market/"
req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
try:
    html = urllib.request.urlopen(req).read().decode('utf-8')
    links = re.findall(r'https://videos.pexels.com/video-files/[^"]+', html)
    print(list(set(links))[:5])
except Exception as e:
    print(e)
