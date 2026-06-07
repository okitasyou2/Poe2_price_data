# PoEDB 사이트의 각 카테고리별 아이템 페이지를 크롤링하여 영어-한국어 아이템 이름 번역 매핑(Dict)을 생성하는 스크립트
# 여기서 생성된 poe2_kr_translation_dict.json 파일을 구글드라이버에 업로드하고 스프레드시트에서 번역할수있음
import asyncio
import aiohttp
import json
import re
import os

# PoE2DB에서 스크래핑할 카테고리 목록
URLS_CAT = [
    "https://poe2db.tw/kr/Claws", "https://poe2db.tw/kr/Daggers", "https://poe2db.tw/kr/Wands",
    "https://poe2db.tw/kr/One_Hand_Swords", "https://poe2db.tw/kr/One_Hand_Axes", "https://poe2db.tw/kr/One_Hand_Maces",
    "https://poe2db.tw/kr/Sceptres", "https://poe2db.tw/kr/Spears", "https://poe2db.tw/kr/Flails",
    "https://poe2db.tw/kr/Bows", "https://poe2db.tw/kr/Staves", "https://poe2db.tw/kr/Two_Hand_Swords",
    "https://poe2db.tw/kr/Two_Hand_Axes", "https://poe2db.tw/kr/Two_Hand_Maces", "https://poe2db.tw/kr/Quarterstaves",
    "https://poe2db.tw/kr/Crossbows", "https://poe2db.tw/kr/Traps", "https://poe2db.tw/kr/Quivers",
    "https://poe2db.tw/kr/Shields", "https://poe2db.tw/kr/Bucklers", "https://poe2db.tw/kr/Foci",
    "https://poe2db.tw/kr/Gloves", "https://poe2db.tw/kr/Boots", "https://poe2db.tw/kr/Body_Armours", "https://poe2db.tw/kr/Helmets",
    "https://poe2db.tw/kr/Amulets", "https://poe2db.tw/kr/Rings", "https://poe2db.tw/kr/Belts", "https://poe2db.tw/kr/Talismans",
    "https://poe2db.tw/kr/Life_Flasks", "https://poe2db.tw/kr/Mana_Flasks", "https://poe2db.tw/kr/Charms",
    "https://poe2db.tw/kr/Stackable_Currency", "https://poe2db.tw/kr/Waystones", "https://poe2db.tw/kr/Relics",
    "https://poe2db.tw/kr/Jewels", "https://poe2db.tw/kr/Unique_weapon", "https://poe2db.tw/kr/Unique_armour",
    "https://poe2db.tw/kr/Unique_accessory", "https://poe2db.tw/kr/Unique_jewel",
    # 추가: 룬, 에센스, 영혼핵, 아이돌, 파편, 오멘
    "https://poe2db.tw/kr/Runes", "https://poe2db.tw/kr/Essences", "https://poe2db.tw/kr/Soul_Cores",
    "https://poe2db.tw/kr/Idols", "https://poe2db.tw/kr/Fragments", "https://poe2db.tw/kr/Omens"
]

HEADERS = {'User-Agent': 'Mozilla/5.0'}

# 기본 수동 추가 단어들
dictionary = {
  "items": "아이템", "gem": "젬", "skill gems": "스킬 젬", "support gems": "보조 젬", "waystones": "경로석"
}

async def fetch_category_items(session, url):
    """카테고리 리스트 페이지에서 영문-한글 매칭 데이터를 추출합니다."""
    try:
        async with session.get(url, timeout=10) as response:
            if response.status == 200:
                html = await response.text()
                # whiteitem, uniqueitem, currencyitem, gemitem 클래스를 가진 링크 추출
                matches = re.findall(r'<a[^>]*class="(?:whiteitem|uniqueitem|currencyitem|gemitem|item_currency|StackableCurrency)[^"]*"[^>]*href="([^"]+)"[^>]*>(.*?)</a>', html)
                for eng_url, inner_html in matches:
                    # 태그 (예: <img ...>) 제거
                    kor_name = re.sub(r'<[^>]+>', '', inner_html).strip()
                    if eng_url and kor_name and not eng_url.startswith("?"):
                        # URL에서 영문명 추출 (예: /kr/Heavy_Belt -> Heavy Belt)
                        eng_name = eng_url.replace("/kr/", "").replace("_", " ").strip()
                        if eng_name and kor_name:
                            # 소문자로 변환하여 저장
                            dictionary[eng_name.lower()] = kor_name
                            # 아포스트로피(')를 완전히 무시한 버전도 추가 저장 (예: cadigans epiphany)
                            dictionary[eng_name.lower().replace("'", "")] = kor_name
    except Exception as e:
        print(f"[{url}] 가져오기 실패: {e}")

async def fetch_individual_unique(session, eng_name):
    """개별 아이템 페이지에서 한글명을 정확히 가져옵니다. (유니크 아이템용)"""
    # 띄어쓰기는 '_', 아포스트로피는 제거하여 URL 생성
    url_name = eng_name.replace("'", "").replace(" ", "_")
    url = f"https://poe2db.tw/kr/{url_name}"
    try:
        async with session.get(url, timeout=10) as response:
            if response.status == 200:
                html = await response.text()
                # 고유 아이템의 경우, 베이스 아이템 이름이 붙는 것을 방지하기 위해 HTML 태그 분석
                # 예: <div class="itemName"><span class="lc">아도니아의 자아</span></div>
                match = re.search(r'<div class="itemName">\s*<span class="lc">([^<]+)</span>', html)
                if not match:
                    # 만약 찾지 못하면 기존 title 방식(전체 이름)으로 폴백
                    match = re.search(r'<title>(.*?)\s*-', html, re.IGNORECASE)
                    
                if match:
                    kor_name = match.group(1).strip()
                    # 번역되지 않은 그대로의 영문명이나 사이트 제목이 아닌 경우만 추가
                    if kor_name.lower() != eng_name.lower() and "poe2db" not in kor_name.lower():
                        dictionary[eng_name.lower()] = kor_name
                        dictionary[eng_name.lower().replace("'", "")] = kor_name
    except Exception:
        pass

async def main():
    print("PoE2DB 영문-한글 번역 데이터 스크래핑을 시작합니다 (약 5~10초 소요)...")
    async with aiohttp.ClientSession(headers=HEADERS) as session:
        # 1. 38개의 카테고리 페이지에서 대량으로 긁어오기 (일반템/유니크 일부)
        print("1/2 카테고리별 아이템 번역 데이터 수집 중...")
        tasks_cat = [fetch_category_items(session, url) for url in URLS_CAT]
        await asyncio.gather(*tasks_cat)
        
        # 2. 유니크 아이템 리스트 텍스트 파일이 있다면, 누락 방지를 위해 개별 페이지 직접 긁어오기
        current_dir = os.path.dirname(os.path.abspath(__file__))
        uniques_file = os.path.join(os.path.dirname(current_dir), "Base_Unique_Price_Update", "poe2_unique_items_latest.txt")
        if os.path.exists(uniques_file):
            print(f"2/2 '{uniques_file}' 기반으로 유니크 아이템 누락 번역 데이터 정밀 수집 중...")
            with open(uniques_file, "r", encoding="utf-8") as f:
                uniques = [line.strip() for line in f if line.strip()]
            
            tasks_uniques = [fetch_individual_unique(session, u) for u in uniques]
            await asyncio.gather(*tasks_uniques)
            
    # 최종 수집된 딕셔너리를 JSON 파일로 저장
    output_file = os.path.join(current_dir, "poe2_kr_translation_dict.json")
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(dictionary, f, ensure_ascii=False, indent=2)
        
    print(f"완료! 총 {len(dictionary)}개의 번역 데이터가 '{output_file}' 파일로 저장되었습니다.")

if __name__ == "__main__":
    asyncio.run(main())
    input("종료하려면 Enter 키를 누르세요...")
