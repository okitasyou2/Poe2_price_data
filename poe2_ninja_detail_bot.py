# poe.ninja API에서 화폐 및 아이템 시세를 가져와서 구글 시트의 지정된 셀에 최신 시세를 기록(업데이트)하는 봇 스크립트
import urllib.request
import urllib.error
import json
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
import pytz

# 검색할 리그명 설정 (리그가 바뀔 때 이 변수만 수정하세요)
# url에 쓰이는 형태 그대로 적어주세요. (예: "Runes+of+Aldur" 또는 "Standard")
LEAGUE_NAME = "Runes+of+Aldur"

# [핵심 1] 인터넷에서 JSON 데이터를 안전하게 긁어오는 함수
# 통신 실패나 429(서버 차단) 에러가 발생하면 지정된 횟수(retries)만큼 재시도하거나 대기합니다.
def fetch_json(url, retries=7):
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(req, timeout=10) as response:
                return json.loads(response.read().decode('utf-8'))
        except urllib.error.HTTPError as e:
            if e.code == 429:
                wait_time = int(e.headers.get('Retry-After', 5 * (attempt + 1)))
                for i in range(wait_time, 0, -1):
                    print(f"Rate limited (429) on {url}. Waiting {i}s...", end="\r")
                    time.sleep(1)
            else:
                return None
        except Exception as e:
            return None
    return None

# [핵심 2] 카테고리별 아이템 "전체 목록"을 가져오는 API 호출 (이름과 ID만 긁어옴)
def fetch_overview(league, item_type):
    url = f"https://poe.ninja/poe2/api/economy/exchange/current/overview?league={league}&type={item_type}"
    return fetch_json(url)

# [핵심 3] 특정 아이템 하나의 "상세 시세(비율/거래량)"를 가져오는 API 호출
def fetch_detail(league, item_type, details_id):
    url = f"https://poe.ninja/poe2/api/economy/exchange/current/details?league={league}&type={item_type}&id={details_id}"
    time.sleep(0.5) # ninja fetch limit 고려
    data = fetch_json(url)
    return item_type, details_id, data

def main():
    print("====================================")
    print(" poe.ninja PoE2 초정밀 상세 시세 봇")
    print("====================================")
    
    # [1단계] 인증 정보(credentials.json)를 읽어와서 구글 시트에 프로그램 로그인
    print("구글 시트 연동 중...")
    try:
        scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
        
        # GitHub Actions에 등록할 시크릿 환경변수가 있는지 확인
        google_creds_json = os.environ.get('GOOGLE_CREDENTIALS_JSON')
        
        if google_creds_json:
            # 깃허브 액션 환경: 환경변수에서 텍스트로 읽어오기
            creds_dict = json.loads(google_creds_json)
            creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
        else:
            # 로컬 PC 환경: 파일에서 읽어오기
            base_dir = os.path.dirname(os.path.abspath(__file__))
            cred_path = os.path.join(base_dir, 'credentials.json')
            creds = ServiceAccountCredentials.from_json_keyfile_name(cred_path, scope)
            
        client = gspread.authorize(creds)  # type: ignore
    except Exception as e:
        print(f"\n[오류] 인증 정보를 읽을 수 없습니다.\n{e}")
        return

    sheet_id = "1Qlc8YBPTPvz6y2xgaxlNeFm7xKOB7UQTI_H07BqMxDM"
    try:
        sheet = client.open_by_key(sheet_id)
    except Exception as e:
        print(f"\n[오류] 시트에 접근할 수 없습니다.\n{e}")
        return
        
    # [2단계] 연결된 구글 스프레드시트 안의 '하단 탭(워크시트)' 목록을 불러오고 사용자에게 번호로 선택받기
    worksheets = sheet.worksheets()
    
    # 깃허브 액션 환경(자동화)인지 확인
    if os.environ.get('GITHUB_ACTIONS') == 'true':
        # 자동화 환경에서는 묻지 않고 3번 시트(인덱스 2) 자동 선택
        worksheet = worksheets[2]
        print(f"\n[자동화 모드] 세 번째 시트 [{worksheet.title}]를 자동으로 선택했습니다.")
    else:
        # 로컬 PC 환경에서는 사용자에게 입력받기
        print("")
        for idx, ws in enumerate(worksheets):
            print(f"{idx + 1}. {ws.title}")
            
        try:
            sel = int(input("\n작업할 시트 번호를 선택하세요 (예: 1): ")) - 1
            worksheet = worksheets[sel]
            print(f"[{worksheet.title}] 시트를 선택했습니다.")
        except:
            print("잘못된 입력입니다.")
            return

    # [3단계] 닌자에서 수집할 카테고리들 (커런시, 조각, 에센스, 룬 등)
    league = LEAGUE_NAME
    types = ['Currency', 'Fragments', 'Essences', 'SoulCores', 'Runes', 'Idols', 'Delirium', 'UncutGems', 'Breach', 'Abyss', 'Ritual', 'LineageSupportGems', 'Expedition', 'Verisium']
    
    print(f"\n1단계: 전체 아이템 목록(Overview) 수집 중...")
    
    # 닌자에 등록된 아이템들의 '카테고리, 이름, 상세 검색용 고유 ID'를 1차로 모아둘 빈 바구니
    items_to_fetch = [] # list of (type, name, details_id)
    
    # 각 카테고리별로 overview API를 쏴서 어떤 아이템들이 있는지 파악
    for t in types:
        data = fetch_overview(league, t)
        time.sleep(1) # API Rate Limit 방지
        if not data:
            continue
            
        items_map = {item['id']: (item.get('name', item['id']), item.get('detailsId', item['id'])) for item in data.get('items', [])}
        for line in data.get('lines', []):
            line_id = line.get('id')
            if line_id in items_map:
                name, details_id = items_map[line_id]
                items_to_fetch.append((t, name, details_id)) # 1차 바구니에 담기
                
    print(f"-> 총 {len(items_to_fetch)}개의 아이템 발견! 상세 데이터(Details) 추출 시작...")

    all_rows = []
    
    # 2행 헤더 (1행은 나중에 KST 업데이트 시간 추가)
    all_rows.append(["", "", "", "", "", "", "", ""])
    all_rows.append([
        "카테고리", "아이템명", 
        "Divine 가격", "Exalted 가격", "Chaos 가격", 
        "Divine 거래량(Div)", "Exalted 거래량(Div)", "Chaos 거래량(Div)"
    ])
    
    results_map = {}
    
    # [4단계] 위에서 모은 아이템 리스트를 바탕으로 상세 시세(Details) 병렬 수집
    # max_workers=50 : 50명의 작업자가 동시에 API를 호출함 (서버 공격방지를 위한 갯수 조절)
    with ThreadPoolExecutor(max_workers=5) as executor:
        try:
            # 50명의 작업자에게 각각 어떤 아이템을 검색할지 일거리를 할당
            future_to_item = {
                executor.submit(fetch_detail, league, t, details_id): (t, name, details_id)
                for t, name, details_id in items_to_fetch
            }
            
            completed = 0
            # 작업자가 하나씩 상세 정보를 들고 올 때마다(완료될 때마다) 아래 코드 실행
            for future in as_completed(future_to_item):
                t, name, details_id = future_to_item[future]
                try:
                    # 결과값(디바인, 엑잘, 카오스와의 교환 비율 등)을 받아서 results_map 에 저장
                    item_type, d_id, data = future.result()
                    if data and "pairs" in data:
                        results_map[details_id] = data["pairs"]
                except Exception as e:
                    pass
                completed += 1
                print(f"[{completed}/{len(items_to_fetch)}] {name} 수집 완료")
        except KeyboardInterrupt:
            # 사용자가 중간에 Ctrl+C를 눌렀을 때, 남은 스레드를 기다리지 않고 봇을 즉시 강제 종료
            print("\n[알림] 강제 종료(Ctrl+C)가 감지되었습니다. 진행 중인 요청을 무시하고 즉시 종료합니다.")
            os._exit(1)
                
    # [5단계] 수집된 거대한 데이터들(results_map)을 엑셀(시트)에 이쁘게 적어넣기 위해 형태 가공
    for t, name, details_id in items_to_fetch:
        pairs = results_map.get(details_id, [])
        
        divine_rate = 0.0
        exalted_rate = 0.0
        chaos_rate = 0.0
        divine_vol = 0.0
        exalted_vol = 0.0
        chaos_vol = 0.0
        
        for p in pairs:
            pid = p.get("id")
            rate = p.get("rate", 0)
            vol = p.get("volumePrimaryValue", 0)
            
            if pid == "divine":
                divine_rate = rate
                divine_vol = vol
            elif pid == "exalted":
                exalted_rate = rate
                exalted_vol = vol
            elif pid == "chaos":
                chaos_rate = rate
                chaos_vol = vol
                
        # 시트의 각 열(카테고리, 아이템명, 가격 3종, 거래량 3종)에 맞게 가공된 데이터를 1줄씩 추가
        all_rows.append([
            t,
            name,
            round(divine_rate, 4) if divine_rate else "",
            round(exalted_rate, 4) if exalted_rate else "",
            round(chaos_rate, 4) if chaos_rate else "",
            round(divine_vol, 2) if divine_vol else "",
            round(exalted_vol, 2) if exalted_vol else "",
            round(chaos_vol, 2) if chaos_vol else ""
        ])

    # 1행 시간 입력
    kst = pytz.timezone('Asia/Seoul')
    now_kst = datetime.now(kst)
    all_rows[0][0] = f"업데이트 KST: {now_kst.strftime('%Y-%m-%d %H:%M:%S')}"

    # [6단계] 가공이 끝난 거대한 표(all_rows)를 구글 시트에 한방에 덮어쓰기 (Bulk Update)
    print(f"\n데이터 처리가 완료되었습니다. 구글 시트에 Bulk Update 중...")
    worksheet.batch_clear(["A:H"]) # 기존 데이터 삭제
    worksheet.update(values=all_rows, range_name=f"A1:H{len(all_rows)}")
    
    print("성공적으로 시트가 덮어씌워졌습니다!")

if __name__ == "__main__":
    main()
