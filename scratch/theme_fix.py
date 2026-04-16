import os
import re

def replace_in_file(filepath):
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()

    # Replacements for adaptive theme classes
    content = content.replace('text-muted', 'text-body-secondary')
    content = content.replace('bg-light', 'bg-body-tertiary')
    content = content.replace('text-dark', 'text-body')
    # Remove bg-white from cards to let base.html card style handle it
    content = content.replace('bg-white', '')

    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(content)

templates_dir = 'templates'
target_files = [
    'currency.html', 
    'feedback.html', 
    'add_investment.html', 
    'login.html', 
    'signup.html',
    'quiz.html'
]

for filename in target_files:
    path = os.path.join(templates_dir, filename)
    if os.path.exists(path):
        print(f"Updating {path}...")
        replace_in_file(path)
    else:
        print(f"File not found: {path}")
