# 구글 시트에 등록된 아이템/스킬 목록을 읽고, PoE 공식 거래소 API를 통해 실시간 최저가를 검색하여 다시 시트에 기록해주는 메인 자동화 봇
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import urllib.request
import urllib.error
import json
import time
import math
import sys
import pytz
from datetime import datetime
import os

# 환산 비율용 글로벌 변수
exalted_rate = None

# 검색할 리그명 설정 (리그가 바뀔 때 이 변수만 수정하세요)
LEAGUE_NAME = "Runes of Aldur"
import urllib.parse
LEAGUE_ENCODED = urllib.parse.quote(LEAGUE_NAME)

# 사용자가 직접 관리하는 아이템-스킬 매핑 JSON 파일 불러오기
try:
    base_dir = os.path.dirname(os.path.abspath(__file__))
    item_skill_path = os.path.join(base_dir, 'poe2_item_to_skill.json')
    with open(item_skill_path, 'r', encoding='utf-8') as f:
        SPECIAL_SKILL_ID = json.load(f)
except Exception as e:
    print(f"[경고] poe2_item_to_skill.json 파일을 읽어오지 못했습니다. 스킬 검색이 생략될 수 있습니다. ({e})")
    SPECIAL_SKILL_ID = {}

def to_exalted(amount, currency):
    global exalted_rate
    c = str(currency).lower() if currency else ''
    if 'exalt' in c: return float(amount)
    if 'divine' in c: return float(amount) * exalted_rate if exalted_rate else None
    return None

def percentile(arr, p):
    if not arr: return None
    if p <= 0: return arr[0]
    if p >= 1: return arr[-1]
    idx = (len(arr) - 1) * p
    lo = math.floor(idx)
    hi = math.ceil(idx)
    if lo == hi: return arr[lo]
    weight = idx - lo
    return arr[lo] * (1 - weight) + arr[hi] * weight

def mad_filter(arr, k=3):
    if len(arr) <= 2: return list(arr)
    s = sorted(arr)
    med = percentile(s, 0.5)
    abs_dev = sorted([abs(x - med) for x in arr])
    mad = percentile(abs_dev, 0.5) or 0
    if mad == 0: return list(arr)
    scale = 1.4826 * mad
    return [x for x in arr if abs(x - med) <= k * scale]

def robust_average_ex(ex_vals):
    if not ex_vals:
        return {"avg": "", "used": 0, "method": "none"}
    
    sorted_vals = sorted(ex_vals)
    p10 = percentile(sorted_vals, 0.10)
    p90 = percentile(sorted_vals, 0.90)
    spread = (p90 / max(p10, 1e-9)) if (p10 and p90) else 1
    
    filtered = mad_filter(ex_vals, 3)
    if len(filtered) < min(4, len(ex_vals)):
        filtered = mad_filter(ex_vals, 4.5)
    if not filtered:
        filtered = list(ex_vals)
        
    if spread > 2.0 and len(filtered) >= 3:
        s = sorted(filtered)
        med = percentile(s, 0.5)
        return {"avg": f"{med:.2f} exalted", "used": len(s), "method": "median(spread_guard)"}
        
    m = len(filtered)
    s = sorted(filtered)
    
    if m >= 8:
        k = math.floor(m * 0.2)
        if m - 2*k < 4:
            k = max(1, math.floor((m - 4) / 2))
        core = s[k : m - k]
        avg_num = sum(core) / len(core)
        method = f"trimmed_mean_20%({k}each)"
    elif m >= 5:
        core = s[1 : m - 1]
        avg_num = sum(core) / len(core)
        method = "trimmed_mean_1each"
    elif m == 4:
        core = s[1 : 3]
        avg_num = sum(core) / len(core)
        method = "mid-mean(2of4)"
    elif m == 3:
        avg_num = s[1]
        method = "median(3)"
    elif m == 2:
        avg_num = sum(s) / 2
        method = "mean(2)"
    else:
        avg_num = s[0]
        method = "single"
        
    return {"avg": f"{avg_num:.2f} exalted", "used": m, "method": method}

def parse_and_wait_rate_limit(headers):
    # X-Rate-Limit-Ip: 3:10:60, 30:300:60
    # X-Rate-Limit-Ip-State: 1:10:0, 29:300:0
    limit_str = headers.get('X-Rate-Limit-Ip', '')
    state_str = headers.get('X-Rate-Limit-Ip-State', '')
    
    if not limit_str or not state_str:
        time.sleep(3.5) # 헤더가 없으면 기본 안전 대기
        return

    limits = {}
    for rule in limit_str.split(','):
        parts = rule.strip().split(':')
        if len(parts) >= 2:
            limits[parts[1]] = int(parts[0]) # period: limit
            
    for rule in state_str.split(','):
        parts = rule.strip().split(':')
        if len(parts) >= 2:
            hits = int(parts[0])
            period = parts[1]
            limit = limits.get(period, 999)
            
            # 한계치에 아슬아슬하게 도달하면(예: 30개 제한인데 29개째 썼을 때)
            if hits >= limit - 1:
                wait_sec = 12 if period == '10' else 60
                print(f"\n[안전 장치 작동] {period}초당 {limit}회 제한에 거의 도달({hits}/{limit})!")
                print(f"서버 밴을 피하기 위해 {wait_sec}초간 전략적 휴식을 취합니다...")
                for i in range(wait_sec, 0, -1):
                    print(f"휴식 중... {i}초 남음  ", end='\r')
                    time.sleep(1)
                print("\n휴식 완료! 다시 쌩쌩하게 달립니다.")
                return

    # 한계가 아니더라도 너무 빨리 쏘면 단기 밴(10초 3회)을 맞을 수 있으니 기본적으로 3.5초는 쉼
    time.sleep(3.5)

def make_request(url, method='GET', payload=None):
    headers = {
        'Accept': 'application/json, text/javascript, */*; q=0.01',
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36',
        'Origin': 'https://poe.game.daum.net',
        'Referer': f'https://poe.game.daum.net/trade2/search/poe2/{LEAGUE_ENCODED}',
        'X-Requested-With': 'XMLHttpRequest',
    }
    if payload:
        headers['Content-Type'] = 'application/json'
    
    data = json.dumps(payload).encode('utf-8') if payload else None
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    
    while True:
        try:
            with urllib.request.urlopen(req) as response:
                res_headers = response.info()
                res_data = json.loads(response.read().decode('utf-8'))
                parse_and_wait_rate_limit(res_headers)
                return res_data
        except urllib.error.HTTPError as e:
            if e.code == 429:
                wait_time = int(e.headers.get('Retry-After', 305))
                print(f"\n[⚠️ 공홈 차단 감지됨 (Rate Limit 429) ⚠️]")
                print(f"서버에서 차단했습니다. 봇이 스스로 {wait_time}초 대기 모드에 진입합니다...")
                for i in range(wait_time, 0, -1):
                    print(f"남은 휴식 시간: {i}초...    ", end='\r')
                    time.sleep(1)
                print("\n대기 종료! 다시 검색을 이어서 시도합니다...\n")
            elif e.code == 400:
                print(f"잘못된 요청(400): {url}")
                return None
            else:
                print(f"HTTP Error {e.code} on {url}")
                return None
        except Exception as e:
            print(f"Error on {url}: {e}")
            return None

def fetch_prices(query_id, data):
    all_ids = data.get('result', [])[:10]
    final_url = f"https://poe.game.daum.net/trade2/search/poe2/{LEAGUE_ENCODED}/{query_id}"
    
    if not all_ids:
        return {"avg": "", "url": final_url, "prices": []}
        
    fetch_url = f"https://poe.game.daum.net/api/trade2/fetch/{','.join(all_ids)}?query={query_id}&realm=poe2"
    fetch_res = make_request(fetch_url, 'GET')
    
    if not fetch_res:
        return {"avg": "", "url": final_url, "prices": []}
        
    prices = []
    ex_vals = []
    
    for r in fetch_res.get('result', []):
        listing = r.get('listing', {})
        price = listing.get('price', {})
        amt = price.get('amount')
        cur = price.get('currency')
        if amt is not None and cur:
            ex = to_exalted(amt, cur)
            if ex is not None:
                ex_vals.append(ex)
                prices.append(f"{ex:.2f} exalted")
                
    avg = ""
    if ex_vals:
        rob = robust_average_ex(ex_vals)
        avg = rob['avg']
        
    return {"avg": avg, "url": final_url, "prices": prices}

def run_query(item_name, ilvl):
    payload = {
        "query": {
            "status": {"option": "securable"},
            "type": item_name,
            "stats": [{"type": "and", "filters": [], "disabled": False}],
            "filters": {
                "misc_filters": {"filters": {"corrupted": {"option": "false"}}, "disabled": False},
                "type_filters": {"filters": {"ilvl": {"min": int(ilvl)}, "rarity": {"option": "normal"}}, "disabled": False},
                "trade_filters": {"filters": {"price": {"option": "exalted_divine"}}, "disabled": False}
            }
        },
        "sort": {"price": "asc"}
    }
    
    search_url = f'https://poe.game.daum.net/api/trade2/search/poe2/{LEAGUE_ENCODED}'
    search_res = make_request(search_url, 'POST', payload)
    if not search_res or 'id' not in search_res:
        return None
    return fetch_prices(search_res['id'], search_res)

def run_skill_min_query(item_name, skill_id, min_val):
    payload = {
        "query": {
            "status": {"option": "securable"},
            "type": item_name,
            "stats": [{
                "type": "and",
                "disabled": False,
                "filters": [{"id": skill_id, "disabled": False, "value": {"min": min_val}}]
            }],
            "filters": {
                "misc_filters": {"filters": {"corrupted": {"option": "false"}}, "disabled": False},
                "type_filters": {"filters": {"rarity": {"option": "normal"}}, "disabled": False},
                "trade_filters": {"filters": {"price": {"option": "exalted_divine"}}, "disabled": False}
            }
        },
        "sort": {"price": "asc"}
    }
    search_url = f'https://poe.game.daum.net/api/trade2/search/poe2/{LEAGUE_ENCODED}'
    search_res = make_request(search_url, 'POST', payload)
    if not search_res or 'id' not in search_res:
        return None
    return fetch_prices(search_res['id'], search_res)

def run_unique_query(item_name):
    payload = {
        "query": {
            "status": {"option": "securable"},
            "term": item_name,
            "stats": [{"type": "and", "filters": [], "disabled": False}],
            "filters": {
                "misc_filters": {"filters": {"corrupted": {"option": "false"}}, "disabled": False},
                "type_filters": {"filters": {"rarity": {"option": "unique"}}, "disabled": False},
                "trade_filters": {"filters": {"price": {"option": "exalted_divine"}}, "disabled": False}
            }
        },
        "sort": {"price": "asc"}
    }
    search_url = f'https://poe.game.daum.net/api/trade2/search/poe2/{LEAGUE_ENCODED}'
    search_res = make_request(search_url, 'POST', payload)
    if not search_res or 'id' not in search_res:
        return None
    return fetch_prices(search_res['id'], search_res)

def fill_result_to_array(arr, start_idx, result):
    if not result:
        arr[start_idx] = "에러(API차단)"
        arr[start_idx+1] = ""
        arr[start_idx+2] = ""
        return
    if not result['avg'] and not result['prices']:
        arr[start_idx] = "매물 없음"
    else:
        arr[start_idx] = result['avg']
    arr[start_idx+1] = result['url']
    arr[start_idx+2] = "\n".join(result['prices'])

def process_base_items(worksheet):
    rows = worksheet.get_all_values()
    if len(rows) < 2: return
    
    checked_count = sum(1 for r in rows[1:] if len(r) > 0 and str(r[0]).strip().upper() == "TRUE")
    print(f"\n[일반 베이스 아이템 스캔 시작] 총 {checked_count}개의 체크된 아이템 대기중...")
    
    for i, row_data in enumerate(rows[1:]):
        row_num = i + 2
        # row_data[0] is A, [1] is B, [3] is D, [4] is E
        if len(row_data) < 2: continue
        
        checked = str(row_data[0]).strip().upper() == "TRUE"
        if not checked: continue
        
        item_name = str(row_data[1]).strip()
        ilvl82 = int(row_data[3]) if len(row_data) > 3 and str(row_data[3]).strip().isdigit() else None
        ilvl81 = int(row_data[4]) if len(row_data) > 4 and str(row_data[4]).strip().isdigit() else None
        
        print(f"[{row_num}행] {item_name} 검색 중...", end='', flush=True)
        
        row_result = [''] * 10
        any_call = False
        
        if ilvl82:
            r82 = run_query(item_name, ilvl82)
            fill_result_to_array(row_result, 0, r82)
            any_call = True
            
        if ilvl81:
            r81 = run_query(item_name, ilvl81)
            fill_result_to_array(row_result, 3, r81)
            any_call = True
            
        skill_id = SPECIAL_SKILL_ID.get(item_name)
        if skill_id:
            r_skill = run_skill_min_query(item_name, skill_id, 20)
            fill_result_to_array(row_result, 6, r_skill)
            any_call = True
            
        kst = pytz.timezone('Asia/Seoul')
        now_str = datetime.now(kst).strftime('%m-%d %H:%M:%S')
        row_result[9] = now_str if any_call else 'EMPTY'
        
        # 구글 시트에 업데이트 (F ~ O 열)
        cell_range = f"F{row_num}:O{row_num}"
        worksheet.update(values=[row_result], range_name=cell_range)
        print(" 완료!")

def process_unique_items(worksheet):
    rows = worksheet.get_all_values()
    if len(rows) < 2: return
    
    checked_count = sum(1 for r in rows[1:] if len(r) > 0 and str(r[0]).strip().upper() == "TRUE")
    print(f"\n[유니크 아이템 스캔 시작] 총 {checked_count}개의 체크된 아이템 대기중...")
    
    for i, row_data in enumerate(rows[1:]):
        row_num = i + 2
        if len(row_data) < 2: continue
        
        checked = str(row_data[0]).strip().upper() == "TRUE"
        if not checked: continue
        
        item_name = str(row_data[1]).strip()
        print(f"[{row_num}행] 유니크 '{item_name}' 검색 중...", end='', flush=True)
        
        row_result = [''] * 10
        r_unique = run_unique_query(item_name)
        fill_result_to_array(row_result, 0, r_unique)
        kst = pytz.timezone('Asia/Seoul')
        now_str = datetime.now(kst).strftime('%m-%d %H:%M:%S')
        row_result[9] = now_str if r_unique else 'EMPTY'
        
        cell_range = f"F{row_num}:O{row_num}"
        worksheet.update(values=[row_result], range_name=cell_range)
        print(" 완료!")

def main():
    print("====================================")
    print(" PoE2 구글 시트 자동 시세 봇 (v1.0)")
    print("====================================")
    print("구글 시트 연동 중...")
    
    import os
    base_dir = os.path.dirname(os.path.abspath(__file__))
    cred_path = os.path.join(os.path.dirname(base_dir), 'credentials.json')
    
    try:
        scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
        creds = ServiceAccountCredentials.from_json_keyfile_name(cred_path, scope)
        client = gspread.authorize(creds)  # type: ignore
    except Exception as e:
        print(f"\n[오류] credentials.json 파일을 읽을 수 없거나 권한이 없습니다.")
        print(f"찾으려는 경로: {cred_path}")
        print(f"상세오류: {e}")
        return

    sheet_id = "1Qlc8YBPTPvz6y2xgaxlNeFm7xKOB7UQTI_H07BqMxDM"
    try:
        sheet = client.open_by_key(sheet_id)
    except Exception as e:
        print(f"\n[오류] 시트에 접근할 수 없습니다. 봇의 이메일이 시트에 편집자로 초대되었는지 확인하세요.\n상세오류: {e}")
        return
        
    print("연동 성공!\n")
    
    # 워크시트 선택
    worksheets = sheet.worksheets()
    for idx, ws in enumerate(worksheets):
        print(f"{idx + 1}. {ws.title}")
        
    try:
        sel = int(input("\n작업할 시트 번호를 선택하세요 (예: 1): ")) - 1
        worksheet = worksheets[sel]
    except:
        print("잘못된 입력입니다.")
        return
        
    global exalted_rate
    try:
        val_a1 = worksheet.acell('A1').value
        if val_a1 is None: raise ValueError("A1 is None")
        exalted_rate = float(val_a1)
        print(f"적용된 환산비: 1 Divine = {exalted_rate} Exalted")
    except:
        exalted_rate = None
        print("환산비(A1)를 읽지 못했습니다. Exalted 고정으로 진행합니다.")
        
    print("\n1. 일반 베이스 아이템 모드 (ilvl 82/81 및 스킬 검색)")
    print("2. 유니크 아이템 모드 (이름으로 유니크 검색)")
    mode = input("모드를 선택하세요 (1 또는 2): ").strip()
    
    if mode in ['1', '2']:
        print("\n시트 초기화 중 (G1 시간 업데이트)...")
        try:
            kst = pytz.timezone('Asia/Seoul')
            now_kst = datetime.now(kst)
            worksheet.update(values=[[f"업데이트 KST: {now_kst.strftime('%Y-%m-%d %H:%M:%S')}"]], range_name="G1")
        except Exception as e:
            print(f"시트 초기화 중 오류가 발생했습니다 (무시하고 진행): {e}")

        if mode == '1':
            process_base_items(worksheet)
        elif mode == '2':
            process_unique_items(worksheet)
    else:
        print("잘못된 모드입니다.")
        return
        
    print("\n모든 작업이 무사히 완료되었습니다!")

if __name__ == "__main__":
    main()
