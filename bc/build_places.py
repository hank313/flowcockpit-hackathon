"""Build Taiwan-wide SQLite from a Geofabrik Taiwan OSM PBF snapshot.
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
from shapely.geometry import shape, mapping, Point, LineString
from shapely.ops import polygonize
from shapely import make_valid, STRtree, union_all, prepare
from places import DATA, DB_PATH, LABELS, categories


def build(pbf, source_url):
    factory = osmium.geom.GeoJSONFactory()
    counties = {}
    district_geometries = []
    district_by_id = {}
    county_relations = {}
    district_relations = {}
    partial_boundaries = []
    boundary_fallbacks = []
    class Relations(osmium.SimpleHandler):
        def relation(self, r):
            if r.tags.get('admin_level') in {'7','8'} and r.tags.get('boundary') == 'administrative':
                district_relations[r.id] = (r.tags.get('name:zh') or r.tags.get('name',''), [m.ref for m in r.members if m.type=='w' and m.role=='outer'])
            if r.tags.get('ISO3166-2','').startswith('TW-'):
                name = (r.tags.get('name:zh') or r.tags.get('name','')).replace('台','臺')
                county_relations[name] = (r.id, [m.ref for m in r.members if m.type=='r' and m.role=='subarea'])
    Relations().apply_file(str(pbf))
    processor = (osmium.FileProcessor(pbf)
        .with_areas(osmium.filter.TagFilter(('boundary','administrative')))
        .with_filter(osmium.filter.KeyFilter('boundary')))
    for o in processor:
        if not o.is_area() or o.tags.get('boundary') != 'administrative': continue
        iso = o.tags.get('ISO3166-2','')
        level = o.tags.get('admin_level','')
        if not iso.startswith('TW-') and level not in {'7','8'}: continue
        if not iso.startswith('TW-') and (o.from_way() or len(o.tags.get('nat_ref','')) != 8 or not o.tags.get('nat_ref','').isdigit()): continue
        name = o.tags.get('name:zh') or o.tags.get('name','')
        name = name.replace('台','臺')
        geom = make_valid(shape(json.loads(factory.create_multipolygon(o))))
        if iso.startswith('TW-'):
            counties[name] = (geom,f'relation/{o.orig_id()}')
        else:
            district_geometries.append((name,geom))
            if not o.from_way(): district_by_id[o.orig_id()] = geom
    # Some extracts omit remote island members (e.g. Qijin). Recover only
    # complete closed outer components; never close missing coastline artificially.
    missing = {i for name,(_,children) in county_relations.items() if name not in counties for i in children if i not in district_by_id}
    needed = {w for i in missing for w in district_relations.get(i,('',[]))[1]}
    lines = {}
    if needed:
        for o in osmium.FileProcessor(pbf).with_locations().with_filter(osmium.filter.EntityFilter(osmium.osm.WAY)):
            if o.id in needed and all(n.location.valid() for n in o.nodes):
                lines[o.id] = LineString([(n.lon,n.lat) for n in o.nodes])
        for ident in missing:
            name, members = district_relations.get(ident,('',[]))
            polygons = list(polygonize([lines[w] for w in members if w in lines]))
            if polygons:
                geom = make_valid(union_all(polygons))
                district_by_id[ident] = geom
                district_geometries.append((name,geom))
                partial_boundaries.append({'district':name,'osm_id':f'relation/{ident}','note':'Only closed outer components present in extract; remote islands may be omitted'})
    for name,(ident,children) in county_relations.items():
        if name not in counties:
            if not children or any(i not in district_by_id for i in children):
                raise RuntimeError(f'Incomplete county and district boundaries: {name}: {[i for i in children if i not in district_by_id]}')
            counties[name] = (make_valid(union_all([district_by_id[i] for i in children])), f'relation/{ident}')
            boundary_fallbacks.append(name)
    if len(counties) != 22:
        raise RuntimeError(f'Expected 22 Taiwan counties/cities, found {len(counties)}; database not replaced')
    county_names = list(counties)
    county_shapes = [counties[n][0] for n in county_names]
    prepare(county_shapes)
    county_tree = STRtree(county_shapes)
    def county_for(point):
        return next((county_names[int(i)] for i in county_tree.query(point) if county_shapes[int(i)].covers(point)), '')
    towns = []
    for name,geom in district_geometries:
        county = county_for(geom.representative_point())
        if county: towns.append((county,name,geom))
    if len(towns) != 368:
        raise RuntimeError(f'Too few Taiwan districts ({len(towns)}); database not replaced')
    town_shapes = [g for _,_,g in towns]
    prepare(town_shapes)
    town_tree = STRtree(town_shapes)
    print('Counties:',len(counties),'districts:',len(towns),flush=True)
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
        county = county_for(point)
        if not county: continue
        district = next((towns[int(i)][1] for i in town_tree.query(point) if towns[int(i)][0]==county and town_shapes[int(i)].covers(point)), '')
        cats = categories(tags)
        name = tags.get('name:zh') or tags.get('name') or tags.get('brand:zh') or tags.get('brand')
        named = bool(name)
        if not name:
            label = LABELS[cats[0]] if cats else (tags.get('amenity') or tags.get('shop') or tags.get('tourism') or '地點')
            name = f'{district or county}未命名{label}'
        address = ''.join(tags.get(k,'') for k in ['addr:city','addr:district','addr:suburb','addr:street','addr:housenumber'])
        osm_id = f'{kind}/{ident}'
        search_text = ' '.join([name,address,county,district,*[v for k,v in tags.items() if k.startswith(('name','alt_name','brand','operator'))]]).casefold().replace('台','臺')
        rows[osm_id] = (osm_id,name,int(named),county,district,point.y,point.x,coord,address,search_text,json.dumps(tags,ensure_ascii=False))
    if len(rows) < 50000: raise RuntimeError(f'Too few POIs ({len(rows)}); database not replaced')
    with osmium.io.Reader(str(pbf)) as reader:
        timestamp = reader.header().get('osmosis_replication_timestamp')
    counts = Counter()
    DATA.mkdir(exist_ok=True)
    # Build atomically; failed updates leave the working database intact.
    with tempfile.TemporaryDirectory(dir=DATA) as temp:
        target = Path(temp)/'taiwan.sqlite3'
        with sqlite3.connect(target) as db:
            db.executescript('''
            CREATE TABLE places(osm_id TEXT PRIMARY KEY,name TEXT NOT NULL,named INTEGER,county TEXT,district TEXT,lat REAL,lon REAL,coordinate_type TEXT,address TEXT,search_text TEXT,tags TEXT);
            CREATE TABLE categories(osm_id TEXT,category TEXT,PRIMARY KEY(osm_id,category));
            CREATE INDEX category_idx ON categories(category);
            CREATE INDEX district_idx ON places(county,district);
            CREATE INDEX location_idx ON places(lat,lon);
            CREATE TABLE administrative_areas(county TEXT,district TEXT,PRIMARY KEY(county,district));
            CREATE TABLE metadata(key TEXT PRIMARY KEY,value TEXT);
            ''')
            db.executemany('INSERT INTO places VALUES (?,?,?,?,?,?,?,?,?,?,?)', rows.values())
            db.executemany('INSERT INTO administrative_areas VALUES (?,?)', sorted({(c,n) for c,n,_ in towns}))
            for ident,row in rows.items():
                for cat in categories(json.loads(row[-1])):
                    counts[cat] += 1
                    db.execute('INSERT INTO categories VALUES (?,?)',(ident,cat))
            with open(pbf,'rb') as file: digest = hashlib.file_digest(file,'sha256').hexdigest()
            meta = {'region':'臺灣','schema_version':2,'osm_timestamp':timestamp,
                    'built_at':datetime.now(timezone.utc).isoformat(),'source_url':source_url,
                    'source_sha256':digest,'place_count':len(rows),'category_counts':dict(counts),
                    'partial_boundaries':partial_boundaries,'boundary_from_district_union':boundary_fallbacks,'counties':sorted(counties),'district_count':len(towns),
                    'county_counts':dict(Counter(row[3] for row in rows.values())),
                    'unassigned_district_count':sum(not row[4] for row in rows.values()),
                    'skipped_geometry_taiwan':skipped_geometry,
                    'scope':'Taiwan amenities/leisure/tourism/shops/historic/drinking_water/bench POIs; no routing or map tiles',
                    'attribution':'© OpenStreetMap contributors','license':'ODbL 1.0',
                    'license_url':'https://www.openstreetmap.org/copyright',
                    'coordinates':'WGS84; areas use an interior representative point, not an entrance'}
            db.execute('INSERT INTO metadata VALUES (?,?)',('snapshot',json.dumps(meta,ensure_ascii=False)))
            assert db.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
        db.close()  # `with sqlite3.connect()` 只提交不關閉;Windows 不能替換仍開啟的檔案
        target.replace(DB_PATH)
    (DATA/'metadata.json').write_text(json.dumps(meta,ensure_ascii=False,indent=2),encoding='utf-8')
    features = [{'type':'Feature','properties':{'name':n,'osm_id':ident},'geometry':mapping(g)} for n,(g,ident) in counties.items()]
    features += [{'type':'Feature','properties':{'county':c,'name':n},'geometry':mapping(g)} for c,n,g in towns]
    (DATA/'boundaries.geojson').write_text(json.dumps({'type':'FeatureCollection','features':features},ensure_ascii=False),encoding='utf-8')
    (DATA/'ATTRIBUTION.md').write_text('# Taiwan OSM data\n\n© OpenStreetMap contributors. ODbL 1.0: https://opendatacommons.org/licenses/odbl/1-0/\n\nSource: '+source_url+'\nSee metadata.json for snapshot time, coverage and SHA-256.\n',encoding='utf-8')
    print(json.dumps(meta,ensure_ascii=False,indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('pbf',type=Path)
    parser.add_argument('--source-url',required=True)
    args = parser.parse_args()
    build(args.pbf,args.source_url)
