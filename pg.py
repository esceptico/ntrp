from pathlib import Path

path = Path("/Users/escept1co/Library/Mobile Documents/iCloud~md~obsidian/Documents/vault")

# print all files in the path
for file in path.glob("**/*.md"):
    print(file)
