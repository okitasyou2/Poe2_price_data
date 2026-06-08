import urllib.request
import json
import os

# GGG 공식 영문 트리 데이터 (또는 poe2db us 데이터)
OFFICIAL_TREE_JSON_URL = "https://raw.githubusercontent.com/grindinggear/poe2-skilltree-export/master/data.json"
# 유저님이 찾아주신 PoE2DB 한국어 트리 데이터!
KR_TREE_JSON_URL = "https://poe2db.tw/data/passive-skill-tree/4.5/data_kr.json?3"

OUTPUT_DICT_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "poe2_kr_translation_dict.json")

def fetch_json(url):
    print(f"다운로드 중: {url}")
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req) as response:
            data = json.loads(response.read().decode('utf-8'))
            return data
    except Exception as e:
        print(f"다운로드 실패 ({url}): {e}")
        return None

def build_translation_dict(en_data, kr_data):
    translation_dict = {}
    en_nodes = en_data.get('nodes', {})
    kr_nodes = kr_data.get('nodes', {})
    
    print(f"영문 노드 {len(en_nodes)}개, 한글 노드 {len(kr_nodes)}개 병합 중...")
    
    for node_id, en_node in en_nodes.items():
        if 'name' in en_node:
            eng_name = en_node['name'].strip()
            if not eng_name:
                continue
                
            eng_name_lower = eng_name.lower()
            kr_name = eng_name  # 기본값은 영문
            
            # 한국어 JSON에서 동일한 노드 ID(node_id)를 찾습니다.
            if node_id in kr_nodes and 'name' in kr_nodes[node_id]:
                kr_name_candidate = kr_nodes[node_id]['name'].strip()
                if kr_name_candidate:
                    kr_name = kr_name_candidate
            
            # 사전에 저장
            translation_dict[eng_name_lower] = kr_name
            # 아포스트로피 무시 버전도 저장
            translation_dict[eng_name_lower.replace("'", "")] = kr_name

    return translation_dict

def main():
    en_data = fetch_json(OFFICIAL_TREE_JSON_URL)
    kr_data = fetch_json(KR_TREE_JSON_URL)
    
    if not en_data or not kr_data:
        print("데이터를 불러오지 못해 종료합니다.")
        return
        
    passive_dict = build_translation_dict(en_data, kr_data)
    
    # 기존 사전 불러오기 (아이템 사전 등과 병합)
    combined_dict = {}
    if os.path.exists(OUTPUT_DICT_PATH):
        try:
            with open(OUTPUT_DICT_PATH, 'r', encoding='utf-8') as f:
                combined_dict = json.load(f)
            print(f"기존 번역 사전({len(combined_dict)}개)을 불러왔습니다.")
        except Exception as e:
            print(f"기존 사전을 불러오는 중 오류 발생: {e}")
            
    # 새로운 패시브 스킬 번역 데이터를 기존 사전에 덮어쓰기/추가
    combined_dict.update(passive_dict)
    
    with open(OUTPUT_DICT_PATH, 'w', encoding='utf-8') as f:
        json.dump(combined_dict, f, indent=4, ensure_ascii=False)
        
    print(f"\n[성공] 패시브 스킬 번역 데이터 {len(passive_dict)}개가 'poe2_kr_translation_dict.json'에 추가/병합되었습니다!")
    print(f"총 누적 단어 수: {len(combined_dict)}개")
    print(f"저장 경로: {OUTPUT_DICT_PATH}")

if __name__ == "__main__":
    main()
