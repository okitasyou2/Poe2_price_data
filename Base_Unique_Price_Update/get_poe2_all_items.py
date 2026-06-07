# 공식 홈페이지 거래소 API에서 전체 아이템(베이스, 유니크 등) 목록을 가져와 텍스트 파일로 저장하는 스크립트
import urllib.request
import json
import os

def fetch_poe2_items():
    print("Fetching data from Path of Exile Official API...")
    url = "https://www.pathofexile.com/api/trade2/data/items?language=en"
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36',
        'Accept': 'application/json',
        'Accept-Language': 'en-US,en;q=0.9',
        'Referer': 'https://www.pathofexile.com/'
    }
    req = urllib.request.Request(url, headers=headers)
    
    try:
        with urllib.request.urlopen(req) as response:
            data = json.loads(response.read().decode('utf-8'))
            
            uniques = set()
            bases = set()
            
            # Base items usually belong to these categories
            target_base_categories = {"weapons", "armour", "accessories", "flasks", "jewels", "foci", "shields", "quivers", "waystones"}
            
            for category in data.get('result', []):
                cat_id = category.get('id', '')
                is_equipment = cat_id in target_base_categories or cat_id.startswith("weapon") or cat_id.startswith("armour") or cat_id.startswith("accessory")
                
                for entry in category.get('entries', []):
                    # 1. Unique Items
                    if entry.get('flags', {}).get('unique', False):
                        if 'name' in entry:
                            uniques.add(entry['name'])
                    
                    # 2. Base Items (White items)
                    elif is_equipment:
                        item_type = entry.get('type') or entry.get('text')
                        if item_type:
                            bases.add(item_type)
            
            current_dir = os.path.dirname(os.path.abspath(__file__))
            
            # Save Unique items
            unique_output = os.path.join(current_dir, "poe2_unique_items_latest.txt")
            with open(unique_output, "w", encoding="utf-8") as f:
                for item_name in sorted(uniques):
                    f.write(item_name + "\n")
                    
            # Save Base items
            base_output = os.path.join(current_dir, "poe2_base_items_latest.txt")
            with open(base_output, "w", encoding="utf-8") as f:
                for item_name in sorted(bases):
                    f.write(item_name + "\n")
                    
            print(f"Success! Saved {len(uniques)} unique items to '{unique_output}'.")
            print(f"Success! Saved {len(bases)} base items to '{base_output}'.")
            
    except Exception as e:
        print(f"An error occurred: {e}")

if __name__ == "__main__":
    fetch_poe2_items()
    input("Press Enter to exit...")
