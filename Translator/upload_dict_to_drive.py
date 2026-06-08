import os
import json
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

def main():
    print("구글 드라이브에 번역 사전(JSON) 덮어쓰기를 시작합니다...")
    
    base_dir = os.path.dirname(os.path.abspath(__file__))
    file_path = os.path.join(base_dir, "poe2_kr_translation_dict.json")
    
    if not os.path.exists(file_path):
        print(f"[오류] 파일이 존재하지 않습니다: {file_path}")
        return
        
    # 1. 구글 API 인증
    scope = ['https://www.googleapis.com/auth/drive']
    google_creds_json = os.environ.get('GOOGLE_CREDENTIALS_JSON')
    
    try:
        if google_creds_json:
            creds_dict = json.loads(google_creds_json)
            creds = Credentials.from_service_account_info(creds_dict, scopes=scope)
        else:
            cred_path = os.path.join(os.path.dirname(base_dir), 'credentials.json')
            creds = Credentials.from_service_account_file(cred_path, scopes=scope)
            
        service = build('drive', 'v3', credentials=creds)
    except Exception as e:
        print(f"[오류] 구글 드라이브 인증 실패: {e}")
        return
        
    # 2. 구글 드라이브 파일 덮어쓰기 (업데이트)
    FILE_ID = "14W6nEzgV7nQg6QV1f9bHY7jai8Dssq6R"
    
    print(f"지정된 파일(ID: {FILE_ID})에 데이터를 덮어쓰는 중...")
    media = MediaFileUpload(file_path, mimetype='application/json', resumable=True)
    
    try:
        uploaded_file = service.files().update(
            fileId=FILE_ID,
            media_body=media,
            fields='id, webViewLink',
            supportsAllDrives=True
        ).execute()
    except Exception as e:
        print(f"[오류] 파일 업데이트 실패: {e}")
        return
        

    # 완료 메시지 및 다운로드 링크
    print("\n=======================================================")
    print("[성공] 구글 드라이브 업로드 완료!")
    print(f"파일 링크: {uploaded_file.get('webViewLink')}")
    print("=======================================================")
    print("※ 위 링크를 통해 업로드된 JSON 파일을 확인하고 다운로드할 수 있습니다.")
    print("※ 깃허브 액션 환경에서는 이 로그에서 링크를 확인할 수 있습니다.")

if __name__ == "__main__":
    main()
