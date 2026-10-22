import json
import tempfile
from pathlib import Path
from importlib.machinery import SourceFileLoader
mod=SourceFileLoader('generator',str(Path(__file__).with_name('generuj_katalog.py'))).load_module()
def test():
    with tempfile.TemporaryDirectory() as td:
        d=Path(td)
        bounds={'type':'FeatureCollection','features':[{'type':'Feature','properties':{'JPT_KOD_JE':'1206','JPT_NAZWA_':'krakowski'},'geometry':{'type':'Polygon','coordinates':[[[19,49],[20,49],[20,51],[19,51],[19,49]]]}}]}
        stations={'type':'FeatureCollection','features':[{'type':'Feature','id':'node/123','properties':{'amenity':'fire_station','name':'OSP Zabierzów','fire_station:type':'volunteer'},'geometry':{'type':'Point','coordinates':[19.8,50.1]}},{'type':'Feature','id':'node/234','properties':{'amenity':'fire_station','name':'JRG Kraków','fire_station:type':'professional'},'geometry':{'type':'Point','coordinates':[19.7,50.1]}},{'type':'Feature','id':'node/456','properties':{'amenity':'fire_station','name':'OSP poza powiatem'},'geometry':{'type':'Point','coordinates':[18.7,50.1]}}]}
        (d/'b.json').write_text(json.dumps(bounds))
        (d/'s.geojson').write_text(json.dumps(stations))
        mod.build(d/'b.json',d/'s.geojson',d/'out',as_of='2026-10-22')
        o=json.loads((d/'out/powiaty/1206.json').read_text())
        assert len(o['stations'])==1 and o['stations'][0]['lat']==50.1
        assert o['county']=='krakowski'
        assert json.loads((d/'out/powiaty.json').read_text())['counties'][0]['teryt']=='1206'
    print('OK: przypisanie punktów OSP do powiatu, usunięcie PSP i punktów spoza granic')
if __name__=='__main__':test()
