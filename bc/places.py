"""Read-only offline POI search. Coordinates and names always come from OSM."""
import json
import math
from pathlib import Path
import sqlite3

DATA = Path(__file__).resolve().parent / 'data'
DB_PATH = DATA / 'yunlin.sqlite3'
TOWNS = ['斗六市','斗南鎮','虎尾鎮','西螺鎮','土庫鎮','北港鎮','古坑鄉','大埤鄉','莿桐鄉','林內鄉','二崙鄉','崙背鄉','麥寮鄉','東勢鄉','褒忠鄉','臺西鄉','元長鄉','四湖鄉','口湖鄉','水林鄉']
LABELS = {'rest':'休息設施','park':'公園','cafe':'咖啡店','food':'餐飲','toilet':'廁所','convenience':'便利商店','fuel':'加油站','medical':'醫療','attraction':'景點','lodging':'住宿','parking':'停車場','water':'飲水設施','all':'地點'}


def categories(tags):
    a, l, t = tags.get('amenity'), tags.get('leisure'), tags.get('tourism')
    found = []
    if a in {'bench','lounger'} or l in {'picnic_table','outdoor_seating'} or tags.get('bench') == 'yes': found.append('rest')
    if l in {'park','garden'}: found.append('park')
    if a == 'cafe': found.append('cafe')
    if a in {'restaurant','fast_food','food_court','ice_cream'}: found.append('food')
    if a == 'toilets': found.append('toilet')
    if tags.get('shop') == 'convenience': found.append('convenience')
    if a == 'fuel': found.append('fuel')
    if a in {'hospital','clinic','pharmacy','doctors','dentist'}: found.append('medical')
    if t in {'attraction','viewpoint','museum','gallery','zoo','theme_park'} or tags.get('historic'): found.append('attraction')
    if t in {'hotel','motel','hostel','guest_house','camp_site','chalet'}: found.append('lodging')
    if a == 'parking': found.append('parking')
    if a == 'drinking_water' or tags.get('drinking_water') == 'yes': found.append('water')
    return found


def metadata():
    with sqlite3.connect(f'{DB_PATH.as_uri()}?mode=ro', uri=True) as db:
        return json.loads(db.execute('SELECT value FROM metadata WHERE key=?', ('snapshot',)).fetchone()[0])


def explicit_name(text):
    """Find the longest actual OSM name mentioned verbatim by the user."""
    normalized = text.casefold().replace('台','臺')
    with sqlite3.connect(f'{DB_PATH.as_uri()}?mode=ro', uri=True) as db:
        names = db.execute('SELECT DISTINCT name FROM places WHERE named=1').fetchall()
    matches = [name for (name,) in names if len(name) >= 3 and name.casefold().replace('台','臺') in normalized]
    return max(matches,key=len) if matches else ''


def distance_m(lat, lon, plat, plon):
    a,b = math.radians(lat),math.radians(plat)
    h = math.sin((b-a)/2)**2 + math.cos(a)*math.cos(b)*math.sin(math.radians(plon-lon)/2)**2
    return 6371000 * 2 * math.asin(math.sqrt(min(1,h)))


def search(category='all', keyword='', district='', latitude=None, longitude=None, limit=5, radius_km=None):
    from search_scope import resolve_scope
    latitude,longitude,radius_km = resolve_scope('', '',latitude,longitude,radius_km)
    # Bound parameters only; model text is never SQL or a filesystem path.
    sql = 'SELECT * FROM places WHERE 1=1'
    params = []
    if category != 'all':
        sql += ' AND osm_id IN (SELECT osm_id FROM categories WHERE category=?)'
        params.append(category)
    if district:
        sql += ' AND district=?'
        params.append(district)
    if keyword:
        sql += ' AND instr(search_text, ?) > 0'
        params.append(keyword.casefold().replace('台','臺'))
    sql += ' ORDER BY named DESC, name, osm_id'
    with sqlite3.connect(f'{DB_PATH.as_uri()}?mode=ro', uri=True) as db:
        db.row_factory = sqlite3.Row
        rows = db.execute(sql, params).fetchall()
    candidates = []
    for row in rows:
        tags = json.loads(row['tags'])
        if tags.get('access') in {'private','no'}: continue
        if category == 'rest' and tags.get('access') in {'customers','permit'}: continue
        point = {'osm_id':row['osm_id'], 'name':row['name'], 'name_is_label':not bool(row['named']),
                 'district':row['district'], 'latitude':row['lat'], 'longitude':row['lon'],
                 'coordinate_type':row['coordinate_type'],
                 'categories':categories(tags), 'address':row['address'] or None,
                 'opening_hours':tags.get('opening_hours'), 'access':tags.get('access'),
                 'fee':tags.get('fee'),
                 'matched_tags':{k:tags[k] for k in ('amenity','leisure','tourism','shop','bench','seats','covered') if k in tags},
                 'source_url':f"https://www.openstreetmap.org/{row['osm_id']}",
                 'distance_m':None}
        if latitude is not None:
            distance = distance_m(latitude,longitude,row['lat'],row['lon'])
            if radius_km is not None and distance > radius_km * 1000:
                continue
            point['distance_m'] = round(distance,1)
        candidates.append(point)
    if latitude is not None:
        candidates.sort(key=lambda p: (p['distance_m'],p['osm_id']))
    elif category == 'rest':
        # Prefer an actual seat/picnic table over a larger facility tagged bench=yes.
        candidates.sort(key=lambda p: (not (p['matched_tags'].get('amenity') in {'bench','lounger'} or p['matched_tags'].get('leisure') == 'picnic_table'),p['name_is_label'],p['name'],p['osm_id']))
    return candidates[:limit], len(candidates)


def answer(category, keyword='', district='', latitude=None, longitude=None, limit=5, radius_km=None):
    points, total = search(category,keyword,district,latitude,longitude,limit,radius_km)
    area = district or '雲林縣'
    label = LABELS.get(category,'地點')
    if not points:
        reply = f'本機雲林 OSM 資料中找不到符合條件的{area}{label}，不代表當地沒有。'
        if category == 'rest': reply += '可改查公園或咖啡店，但座位與開放狀態需要另行確認。'
    else:
        names = '、'.join(p['name'] for p in points)
        reply = f'找到 {total} 筆符合條件的{label}，列出 {len(points)} 筆：{names}。'
        if latitude is None: reply += '未提供目前位置，這些結果未按距離排序。'
        else: reply += '已依直線距離排序；距離不是步行路程。'
        if category == 'rest': reply += '這些地點有座椅或休息設施標註，無法確認目前是否有空位。'
        reply += '離線資料無法確認即時營業或開放狀態。'
    if radius_km is not None:
        reply = f'以座標 {latitude}, {longitude} 為中心，僅查詢直線距離 {radius_km:g} 公里內的雲林地點。' + reply
    return {'places':points, 'reply':reply}
