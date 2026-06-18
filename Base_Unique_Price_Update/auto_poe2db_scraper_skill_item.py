# poe2_skill_ids.json 에 있는 목록중에 이름과 skill id를 매칭해서 poe2_item_to_skill.json 에 저장
# 셉터, 마법봉, 지팡이만 검색함

import os
import json
import urllib.request
import time
from bs4 import BeautifulSoup

def main():
    base_dir = os.path.dirname(os.path.abspath(__file__))
    skill_ids_path = os.path.join(base_dir, 'poe2_skill_ids.json')
    output_path = os.path.join(base_dir, 'poe2_item_to_skill.json')

    if not os.path.exists(skill_ids_path):
        print(f"[오류] '{skill_ids_path}' 파일이 없습니다. 먼저 update_skill_ids.py를 실행하세요.")
        return

    with open(skill_ids_path, 'r', encoding='utf-8') as f:
        skill_data = json.load(f)

    # "스킬 부여: #레벨 주문투척" -> "주문투척"을 키로 추출
    skill_name_to_id = {}
    for text, skill_id in skill_data.items():
        # "#레벨 " 뒷부분의 스킬 이름 추출
        parts = text.split('#레벨 ')
        if len(parts) > 1:
            skill_name = parts[1].strip()
            skill_name_to_id[skill_name] = skill_id

    urls_to_scrape = [
        'https://poe2db.tw/kr/Wands',
        'https://poe2db.tw/kr/Staves',
        'https://poe2db.tw/kr/Sceptres'
    ]

    item_to_skill = {}
    print("PoEDB에서 무기/방어구 정보를 긁어오는 중입니다...")

    headers = {'User-Agent': 'Mozilla/5.0'}

    for url in urls_to_scrape:
        print(f"탐색 중: {url}")
        try:
            req = urllib.request.Request(url, headers=headers)
            res = urllib.request.urlopen(req)
            html = res.read().decode('utf-8')
            soup = BeautifulSoup(html, 'html.parser')
            
            for a_tag in soup.find_all('a'):
                item_name = a_tag.text.strip()
                if not item_name: continue
                
                # a 태그 주변 텍스트 긁어오기
                full_text = a_tag.parent.parent.text if a_tag.parent and a_tag.parent.parent else ""
                
                # 해당 텍스트에 "스킬 부여: [스킬이름]" 패턴이 있는지 검사
                for sk_name, sk_id in skill_name_to_id.items():
                    if f"스킬 부여: {sk_name}" in full_text:
                        item_to_skill[item_name] = sk_id
                        break
        except Exception as e:
            print(f"[오류] {url} 처리 중 에러: {e}")
            
        time.sleep(1) # 서버에 무리가 가지 않도록 1초 대기

    print("\n총 발견된 아이템 및 태그 수:", len(item_to_skill))
    
    # 2.5 공식 API에서 실제 아이템 목록을 불러와 더미 데이터 필터링
    print("공식 아이템 API와 대조하여 더미 데이터를 제거합니다...")
    try:
        items_req = urllib.request.Request('https://poe.kakaogames.com/api/trade2/data/items', headers=headers)
        items_res = urllib.request.urlopen(items_req)
        items_data = json.loads(items_res.read().decode('utf-8'))
        
        valid_item_names = set()
        for category in items_data.get('result', []):
            for entry in category.get('entries', []):
                if 'name' in entry: valid_item_names.add(entry['name'])
                if 'type' in entry: valid_item_names.add(entry['type'])
                if 'text' in entry: valid_item_names.add(entry['text'])
                
        # 실제 아이템 이름에 포함된 것만 남기기
        item_to_skill = {k: v for k, v in item_to_skill.items() if k in valid_item_names}
        print(f"더미 필터링 완료! 최종적으로 {len(item_to_skill)}개의 실제 아이템만 남았습니다.")
    except Exception as e:
        print(f"[경고] 공식 아이템 대조 중 오류 발생: {e}")

    # 기존 파일이 있다면 불러와서 합치기 (수동 추가분 보존)
    if os.path.exists(output_path):
        with open(output_path, 'r', encoding='utf-8') as f:
            try:
                existing_data = json.load(f)
                existing_data.update(item_to_skill)
                item_to_skill = existing_data
            except:
                pass

    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(item_to_skill, f, indent=4, ensure_ascii=False)
        
    print(f"완료! '{output_path}' 파일이 최신화되었습니다.")

if __name__ == '__main__':
    main()
