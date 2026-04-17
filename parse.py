import json

with open('videos.json', 'r', encoding='utf-8') as f:
    for line in f:
        v = json.loads(line)
        print(f"ID: {v.get('id')}, W: {v.get('width')}, H: {v.get('height')}, Title: {v.get('title')}")
