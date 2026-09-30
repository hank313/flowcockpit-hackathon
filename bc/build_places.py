"""Build Yunlin-only SQLite from a Geofabrik Taiwan OSM PBF snapshot.
Usage: .venv/bin/python build_places.py /path/taiwan.osm.pbf --source-url URL
Requires requirements-data.txt (only for database building).
"""
import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sqlite3
import tempfile

import osmium
from shapely.geometry import shape, mapping, Point
from shapely import make_valid
from shapely.prepared import prep
from places import DATA, DB_PATH, TOWNS, LABELS, categories


def build(pbf, source_url):
    factory = osmium.geom.GeoJSONFactory()
    county = None
    towns = {}
    processor = (osmium.FileProcessor(pbf)
        .with_areas(osmium.filter.TagFilter(('boundary','administrative')))
        .with_filter(osmium.filter.KeyFilter('boundary')))
    for o in processor:
        if not o.is_area() or o.tags.get('boundary') != 'administrative': continue
        name = o.tags.get('name:zh') or o.tags.get('name','')
        if o.tags.get('ISO3166-2') != 'TW-YUN' and name not in TOWNS: continue
        geom = make_valid(shape(json.loads(factory.create_multipolygon(o))))
        if o.tags.get('ISO3166-2') == 'TW-YUN':
            county = geom
            county_id = f'relation/{o.orig_id()}'
        elif name in TOWNS: towns[name] = geom
    if county is None: raise RuntimeError('Yunlin county boundary TW-YUN missing; database not replaced')
    towns = {n:g for n,g in towns.items() if county.covers(g.representative_point())}
    if len(towns) != 20: raise RuntimeError(f'Expected 20 Yunlin townships, found {len(towns)}: {list(towns)}')
    print('Boundary:',county_id, 'townships:',len(towns), flush=True)
    county_test = prep(county)
    town_tests = [(n,prep(g)) for n,g in towns.items()]
    rows = {}
    skipped_geometry = 0
    processor = (osmium.FileProcessor(pbf).with_areas()
        .with_filter(osmium.filter.KeyFilter('amenity','leisure','tourism','shop','historic','drinking_water','bench')))
    for o in processor:
        if o.is_relation(): continue
        tags = dict(o.tags)
        if any(k in tags for k in ('disused:amenity','abandoned:amenity')) and not tags.get('amenity'): continue
        try:
            if o.is_node():
                point = Point(o.location.lon,o.location.lat)
                kind, ident, coord = 'node',o.id,'osm_node'
            elif o.is_area():
                geom = make_valid(shape(json.loads(factory.create_multipolygon(o))))
                point = geom.representative_point()
                kind, ident = ('way' if o.from_way() else 'relation'),o.orig_id()
                coord = 'representative_point_not_entrance'
            elif o.is_way() and not o.is_closed():
                geom = shape(json.loads(factory.create_linestring(o)))
                point = geom.interpolate(0.5,normalized=True)
                kind, ident, coord = 'way',o.id,'line_midpoint_not_entrance'
            else: continue
        except (RuntimeError, ValueError):
            skipped_geometry += 1
            continue
        if not county_test.covers(point): continue
        district = next((n for n,g in town_tests if g.covers(point)), '')
        cats = categories(tags)
        name = tags.get('name:zh') or tags.get('name') or tags.get('brand:zh') or tags.get('brand')
        named = bool(name)
        if not name:
            label = LABELS[cats[0]] if cats else (tags.get('amenity') or tags.get('shop') or tags.get('tourism') or '地點')
            name = f'{district or "雲林縣"}未命名{label}'
        address = ''.join(tags.get(k,'') for k in ['addr:city','addr:district','addr:suburb','addr:street','addr:housenumber'])
        osm_id = f'{kind}/{ident}'
        search_text = ' '.join([name,address,district,*[v for k,v in tags.items() if k.startswith(('name','alt_name','brand','operator'))]]).casefold().replace('台','臺')
        rows[osm_id] = (osm_id,name,int(named),district,point.y,point.x,coord,address,search_text,json.dumps(tags,ensure_ascii=False))
    if len(rows) < 100: raise RuntimeError(f'Too few POIs ({len(rows)}); database not replaced')
    with osmium.io.Reader(str(pbf)) as reader:
        timestamp = reader.header().get('osmosis_replication_timestamp')
    counts = Counter()
    DATA.mkdir(exist_ok=True)
    # Build atomically; failed updates leave the working database intact.
    with tempfile.TemporaryDirectory(dir=DATA) as temp:
        target = Path(temp)/'yunlin.sqlite3'
        with sqlite3.connect(target) as db:
            db.executescript('''
            CREATE TABLE places(osm_id TEXT PRIMARY KEY,name TEXT NOT NULL,named INTEGER,district TEXT,lat REAL,lon REAL,coordinate_type TEXT,address TEXT,search_text TEXT,tags TEXT);
            CREATE TABLE categories(osm_id TEXT,category TEXT,PRIMARY KEY(osm_id,category));
            CREATE INDEX category_idx ON categories(category);
            CREATE INDEX district_idx ON places(district);
            CREATE TABLE metadata(key TEXT PRIMARY KEY,value TEXT);
            ''')
            db.executemany('INSERT INTO places VALUES (?,?,?,?,?,?,?,?,?,?)', rows.values())
            for ident,row in rows.items():
                for cat in categories(json.loads(row[-1])):
                    counts[cat] += 1
                    db.execute('INSERT INTO categories VALUES (?,?)',(ident,cat))
            with open(pbf,'rb') as file: digest = hashlib.file_digest(file,'sha256').hexdigest()
            meta = {'region':'雲林縣','boundary':county_id,'osm_timestamp':timestamp,
                    'built_at':datetime.now(timezone.utc).isoformat(),'source_url':source_url,
                    'source_sha256':digest,'place_count':len(rows),'category_counts':dict(counts),
                    'townships':sorted(towns),'skipped_geometry_taiwan':skipped_geometry,
                    'scope':'Yunlin amenities/leisure/tourism/shops/historic/drinking_water/bench POIs; no routing or map tiles',
                    'attribution':'© OpenStreetMap contributors','license':'ODbL 1.0',
                    'license_url':'https://www.openstreetmap.org/copyright',
                    'coordinates':'WGS84; areas use an interior representative point, not an entrance'}
            db.execute('INSERT INTO metadata VALUES (?,?)',('snapshot',json.dumps(meta,ensure_ascii=False)))
            assert db.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
        target.replace(DB_PATH)
    (DATA/'metadata.json').write_text(json.dumps(meta,ensure_ascii=False,indent=2),encoding='utf-8')
    features = [{'type':'Feature','properties':{'name':'雲林縣','osm_id':county_id},'geometry':mapping(county)}]
    features += [{'type':'Feature','properties':{'name':n},'geometry':mapping(g)} for n,g in towns.items()]
    (DATA/'boundaries.geojson').write_text(json.dumps({'type':'FeatureCollection','features':features},ensure_ascii=False),encoding='utf-8')
    print(json.dumps(meta,ensure_ascii=False,indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('pbf',type=Path)
    parser.add_argument('--source-url',required=True)
    args = parser.parse_args()
    build(args.pbf,args.source_url)
