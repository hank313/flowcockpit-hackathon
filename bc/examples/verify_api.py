"""Run reproducible intent/audio/location requests against a running BC service."""
import argparse
import json
from pathlib import Path
import sys
import httpx


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base-url',default='http://127.0.0.1:8001')
    args = parser.parse_args()
    folder = Path(__file__).resolve().parent
    payload = json.loads((folder/'intent-request.json').read_text(encoding='utf-8'))
    fields = {key:str(payload[key]) for key in ('latitude','longitude','type','target_candidate_id')}
    fields['language'] = 'zh'
    reference = {'type':payload['type'],'target_candidate_id':payload['target_candidate_id']}
    def show(label, response):
        print(label, response.status_code)
        print(json.dumps(response.json(),ensure_ascii=False,indent=2))
        response.raise_for_status()
        return response.json()
    def check(condition, message):
        if not condition: raise ValueError(message)
    with httpx.Client(base_url=args.base_url.rstrip('/'),timeout=180) as client:
        data = show('JSON /api/intent',client.post('/api/intent',json=payload))
        check(data['conditions'].get('max_drive_distance_m')==500,'行駛條件不符')
        for endpoint in ('/api/intent','/api/audio'):
            with (folder/'rest-stop.wav').open('rb') as audio:
                response = client.post(endpoint,files={'file':('rest-stop.wav',audio,'audio/wav')},data=fields)
            data = show('Audio '+endpoint,response)
            bc = data if endpoint=='/api/intent' else data['bc_to_d']
            check(bc['reference']==reference,'操作或候選 ID 不符')
            check(bc['latitude']==payload['latitude'] and bc['longitude']==payload['longitude'],'回傳座標不符')
            check('休息' in bc['raw_text'],'未辨識到範例語音的休息需求')
            location = show('GET /api/location',client.get('/api/location'))
            check(location['latitude']==payload['latitude'] and location['longitude']==payload['longitude'],'位置紀錄不符')
            check(location['source']==endpoint,'位置紀錄來源不符')
    print('PASS：文字、音訊、操作欄位與位置紀錄驗證完成。')


if __name__ == '__main__':
    try:
        main()
    except (httpx.HTTPError, ValueError, KeyError, OSError) as exc:
        print('FAIL:',exc,file=sys.stderr)
        sys.exit(1)
