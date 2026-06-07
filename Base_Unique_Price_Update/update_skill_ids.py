# 공식 거래소 API에서 skill 부여하는 항목들 스크랩해서 poe2_skill_ids.json에 저장
import urllib.request
import urllib.error
import json
import os

def update_skill_ids():
    url = 'https://poe.game.daum.net/api/trade2/data/stats'
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)',
        'Accept': 'application/json',
    }
    
    print("공식 거래소 API에서 능력치 데이터를 불러오는 중...")
    
    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req) as response:
            data = json.loads(response.read().decode('utf-8'))
            
        skill_dict = {}
        # 전체 능력치 중에서 ID에 'skill.'이 포함된 것만 추출 (주로 "스킬 부여: #레벨 XXX")
        for category in data.get('result', []):
            for entry in category.get('entries', []):
                stat_id = entry.get('id', '')
                if 'skill.' in stat_id:
                    # 키: 사용자에게 보이는 텍스트(예: "스킬 부여: #레벨 화염구")
                    # 값: 내부 API ID(예: "skill.fireball")
                    skill_dict[entry['text']] = stat_id
                    
        output_file = 'poe2_skill_ids.json'
        # 스크립트가 실행되는 폴더에 저장되도록 절대 경로 구성
        base_dir = os.path.dirname(os.path.abspath(__file__))
        output_path = os.path.join(base_dir, output_file)
        
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(skill_dict, f, indent=4, ensure_ascii=False)
            
        print(f"완료! 총 {len(skill_dict)}개의 스킬 ID를 성공적으로 추출하여 '{output_file}'에 저장했습니다.")
        print(f"저장 경로: {output_path}")

    except Exception as e:
        print(f"오류가 발생했습니다: {e}")

if __name__ == "__main__":
    update_skill_ids()
