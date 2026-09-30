"""Deterministic location/radius extraction; never ask an LLM to calculate distance."""
import math
import re

NUMBER = r'[+-]?(?:\d+(?:\.\d*)?|\.\d+)'
COORDINATES = re.compile(r'(?:座標|坐標|coordinates?)\s*[:：]?\s*[（(]?\s*(' + NUMBER + r')\s*[,，、]\s*(' + NUMBER + r')\s*[）)]?', re.I)
RADIUS = re.compile(r'(?:(?:半徑|範圍)\s*[:：]?\s*)?(' + NUMBER + r'|[一二兩三四五六七八九十]+)\s*(公里|千米|公尺|米|km|m)\s*(?:以內|之內|內)', re.I)
DIGITS = {'一':1,'二':2,'兩':2,'三':3,'四':4,'五':5,'六':6,'七':7,'八':8,'九':9}


def number(value):
    if value in DIGITS: return DIGITS[value]
    if '十' in value:
        left,right = value.split('十')
        return (DIGITS[left] if left else 1)*10 + (DIGITS[right] if right else 0)
    return float(value)


def extract_scope(text):
    coords = COORDINATES.findall(text)
    radii = RADIUS.findall(text)
    if len(set(coords)) > 1 or len(set(radii)) > 1:
        raise ValueError('找到多組座標或範圍，請只提供一組搜尋中心與半徑。')
    lat,lon = map(float,coords[0]) if coords else (None,None)
    radius = None
    if radii:
        value,unit = radii[0]
        radius = number(value) / (1000 if unit.lower() in {'m','公尺','米'} else 1)
    return lat,lon,radius


def resolve_scope(text, instruction, latitude=None, longitude=None, radius_km=None):
    if (latitude is None) != (longitude is None):
        raise ValueError('latitude 和 longitude 必須一起提供。')
    # Form/JSON fields override the instruction, which overrides spoken defaults.
    for source in (instruction,text):
        lat,lon,radius = extract_scope(source)
        if latitude is None and lat is not None: latitude,longitude = lat,lon
        if radius_km is None and radius is not None: radius_km = radius
    if latitude is not None:
        if not math.isfinite(latitude) or not -90 <= latitude <= 90 or not math.isfinite(longitude) or not -180 <= longitude <= 180:
            raise ValueError('座標順序須為緯度、經度；緯度 -90～90，經度 -180～180。')
    if radius_km is not None:
        if not math.isfinite(radius_km) or radius_km <= 0:
            raise ValueError('搜尋半徑 radius_km 必須是大於零的公里數。')
        if latitude is None:
            raise ValueError('指定搜尋半徑時，請同時提供中心座標。')
    return latitude,longitude,radius_km


def without_scope(text):
    return RADIUS.sub('',COORDINATES.sub('',text)).strip(' ，,。')
