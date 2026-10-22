#!/usr/bin/env python3
"""Generuj per-powiat JSON remiz OSP z wyciągu OSM i granic powiatowych GeoJSON.

Uruchom przez:
 python generuj_katalog.py --boundaries powiaty.json --stations stations.geojson --out ../site/public_html/mapa-pro-katalog/data
Lub opcjonalnie z PBF Geofabrik (wymaga osmium-tool):
 python generuj_katalog.py --boundaries powiaty.json --pbf malopolskie-latest.osm.pbf --out ...

Wpisy OSM licencja ODbL, granice administracyjne - Geoportal / PZGIK.
"""
from __future__ import annotations
import argparse
from collections import defaultdict
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import tempfile
import sys
import unicodedata

REGIONS = {
    '02':'dolnośląskie', '04':'kujawsko-pomorskie', '06':'lubelskie', '08':'lubuskie',
    '10':'łódzkie','12':'małopolskie','14':'mazowieckie','16':'opolskie',
    '18':'podkarpackie','20':'podlaskie','22':'pomorskie','24':'śląskie',
    '26':'świętokrzyskie','28':'warmińsko-mazurskie','30':'wielkopolskie','32':'zachodniopomorskie',
}

def point_in_ring(lon,lat,ring):
    inside=False
    for a,b in zip(ring, ring[-1:]+ring[:-1]):
        x1,y1=a[:2]; x2,y2=b[:2]
        if (y1>lat)!=(y2>lat) and lon < (x2-x1)*(lat-y1)/(y2-y1)+x1:
            inside=not inside
    return inside

def in_poly(lon,lat,poly):
    if not poly or not point_in_ring(lon,lat,poly[0]):return False
    return not any(point_in_ring(lon,lat,hole) for hole in poly[1:])

def in_geo(lon,lat,geom):
    coords=geom.get('coordinates') or []
    typ=geom.get('type')
    if typ=='Polygon':return in_poly(lon,lat,coords)
    if typ=='MultiPolygon':return any(in_poly(lon,lat,p) for p in coords)
    return False

def centroid(geom):
    typ=geom.get('type')
    coords=geom.get('coordinates') or []
    if typ=='Point' and len(coords)>=2: return float(coords[0]),float(coords[1])
    if typ=='Polygon' and coords:
        ring=coords[0]
    elif typ=='MultiPolygon' and coords:
        ring=max((p[0] for p in coords if p), key=len, default=[])
    else:
        return None
    if not ring:return None
    # Marker only; representative arithmetic location approximates building outlines.
    if len(ring)>1 and ring[0]==ring[-1]:ring=ring[:-1]
    return (sum(float(p[0]) for p in ring)/len(ring),sum(float(p[1]) for p in ring)/len(ring))

def normalized(v):
    return ''.join(c for c in unicodedata.normalize('NFKD',str(v).lower()) if not unicodedata.combining(c))

def volunteer(tags):
    name=' '.join(str(tags.get(k) or '') for k in ['name','short_name','operator'])
    kind=' '.join(str(tags.get(k) or '') for k in ['fire_station:type','emergency_service'])
    n=normalized(name);t=normalized(kind)
    if 'professional' in t or 'career' in t or 'panstwowa straz pozarna' in n or n.startswith('psp ') or n.startswith('jrg '):return False
    return n.startswith('osp ') or ' osp ' in (' '+n+' ') or 'ochotnicza straz pozarna' in n or 'volunt' in t

def read_geo(path):
    geo=json.loads(Path(path).read_text(encoding='utf-8-sig'))
    if geo.get('type')!='FeatureCollection':raise ValueError('Plik musi zawierać GeoJSON FeatureCollection')
    return geo['features']

def build(boundaries_path,stations_path,out,as_of=None):
    boundaries=[]
    for f in read_geo(boundaries_path):
        p=f.get('properties') or {}
        t=str(p.get('JPT_KOD_JE') or p.get('teryt') or '')
        n=str(p.get('JPT_NAZWA_') or p.get('name') or '').strip()
        g=f.get('geometry') or {}
        if len(t)!=4 or not t.isdecimal() or len(n)<3 or g.get('type') not in ('Polygon','MultiPolygon'): continue
        region=REGIONS.get(t[:2],'')
        # distinguish city and land county
        if int(t[2:])>=61 and not any(word in normalized(n) for word in ['miasto','powiat ']):
            n=n+' (miasto)'
        boundaries.append({'teryt':t,'name':n,'region':region,'geometry':g})
    if not boundaries:raise ValueError('Nie rozpoznano granic powiatów. Oczekiwane JPT_KOD_JE i JPT_NAZWA_')
    seen=set();by_county=defaultdict(list)
    for f in read_geo(stations_path):
        p=f.get('properties') or {}
        if p.get('amenity')!='fire_station' and p.get('emergency')!='fire_station':continue
        if not volunteer(p): continue
        name=str(p.get('name') or p.get('operator') or '').strip()
        if not name:continue
        coords=centroid(f.get('geometry') or {})
        if coords is None:continue
        lon,lat=coords
        if not (13<lon<25 and 48<lat<56):continue
        ident=str(p.get('@id') or p.get('osm_id') or f.get('id') or '')
        if not ident:continue
        for c in boundaries:
            if in_geo(lon,lat,c['geometry']):
                key=(c['teryt'],ident)
                if key not in seen:
                    seen.add(key)
                    by_county[c['teryt']].append(dict(id=ident,name=name,shortName=str(p.get('short_name') or ''),operator=str(p.get('operator') or ''),type=str(p.get('fire_station:type') or ''),emergencyService=str(p.get('emergency_service') or ''),lat=round(lat,7),lng=round(lon,7)))
                break
    date=as_of or datetime.now(timezone.utc).isoformat(timespec='seconds')
    out=Path(out); (out/'powiaty').mkdir(parents=True,exist_ok=True)
    counties=[{'teryt':c['teryt'],'name':c['name'],'region':c['region']} for c in boundaries]
    counties.sort(key=lambda c:(c['region'],normalized(c['name'])))
    (out/'powiaty.json').write_text(json.dumps({'ok':True,'counties':counties},ensure_ascii=False,separators=(',',':')),encoding='utf-8')
    for c in boundaries:
        arr=sorted(by_county[c['teryt']],key=lambda x:normalized(x['name']))
        if not arr: continue  # nie nadpisuj poprzednich danych innych województw pustym plikiem
        result={'ok':True,'teryt':c['teryt'],'county':c['name'],'updated':date,'source':'© OpenStreetMap contributors (ODbL); granice: Geoportal PRG','stations':arr}
        (out/'powiaty'/f"{c['teryt']}.json").write_text(json.dumps(result,ensure_ascii=False,separators=(',',':')),encoding='utf-8')
    print(f'Powiatów: {len(boundaries)}, remiz OSP: {sum(len(v) for v in by_county.values())}, zapełnionych powiatów: {sum(bool(v) for v in by_county.values())}')
    return boundaries,by_county

def osmium_extract(pbf,output):
    with tempfile.TemporaryDirectory() as d:
        filtered=Path(d)/'remizy.pbf'
        subprocess.run(['osmium','tags-filter','--overwrite','-o',str(filtered),str(pbf),'nwr/amenity=fire_station','nwr/emergency=fire_station'],check=True)
        subprocess.run(['osmium','export','--overwrite','-f','geojson','-o',str(output),str(filtered)],check=True)

def main():
    a=argparse.ArgumentParser()
    a.add_argument('--boundaries',required=True,help='GeoJSON granic powiatów (np. powiaty.json Geoportal)')
    a.add_argument('--stations',help='GeoJSON remiz już wyeksportowanych z OSM')
    a.add_argument('--pbf',help='Wyciąg OSM PBF (wymaga osmium-tool)')
    a.add_argument('--out',required=True,help='Katalog docelowy data/')
    opts=a.parse_args()
    if not opts.stations and not opts.pbf:a.error('Podaj --stations lub --pbf')
    if opts.pbf:
        with tempfile.TemporaryDirectory() as d:
            geo=Path(d)/'remizy.geojson';osmium_extract(opts.pbf,geo);build(opts.boundaries,geo,opts.out)
    else:build(opts.boundaries,opts.stations,opts.out)
if __name__=='__main__':main()
