
# http://www.lfd.uci.edu/~gohlke/pythonlibs/#pyshp
import shapefile

# http://www.lfd.uci.edu/~gohlke/pythonlibs/#pyproj
import pyproj

# http://www.lfd.uci.edu/~gohlke/pythonlibs/#requests
import requests

import hashlib

wgs84 = pyproj.Proj("+init=EPSG:4326") # LatLon with WGS84 datum used for geojson
orsp = pyproj.Proj("+init=EPSG:2913", preserve_units=True) # datum used by Oregon Metro

# read the shapefile
reader = shapefile.Reader("c:/temp/trails.shp")
fields = reader.fields[1:]
field_names = [field[0] for field in fields]
buffer = []
conter=0

agencies = {}
trail_names = {}

for sr in reader.shapeRecords():

    if conter < 100:

        atr = dict(zip(field_names, sr.record))

        # we're only allowing open trails to pass
        if atr['STATUS'].upper() == 'OPEN':
            props = {}
            # This is bad news, difficult to hang off of something that is 
            # semi randomly produced.
            if atr['AGENCYNAME'] not in agencies.iterkeys():
                m = hashlib.sha224(agencies.iterkeys().next()).hexdigest()
                agency_id = int(m[-5:], 16)
                agencies[atr['AGENCYNAME']] = agency_id
                
                """
                t='Hillsboro Parks and Recreation'
                >>> m=hashlib.sha224(t).hexdigest()
                'c33f51592f1d24ef759d695dc05602a265832bc1a55918da3228ed08'
                >>> int(m[-5:], 16)
                584968
                """

            props['id'] = str(int(atr['TRAILID']))
            props['steward_id'] = agency_id
            props['name'] = atr['TRAILNAME'].strip()
            props['motor_vehicles'] = 'no'
            props['foot'] = 'yes' if atr['HIKE'] == 'Yes' else 'No'
            props['bicycle'] = 'yes' if atr['ROADBIKE'] == 'Yes'\
                or atr['MTNBIKE'] == 'Yes' else 'no'
            props['horse'] = 'yes' if atr['EQUESTRIAN'] == 'Yes' else 'no'
            props['ski'] = 'no'
            props['wheelchair'] = 'yes' if atr['ACCESSIBLE'] == 'Accessible' else 'no'
            props['osm_tags'] = 'surface='+atr['TRLSURFACE']+';width='+atr['WIDTH']

            n_geom = []
            geom = sr.shape.__geo_interface__
            for point in geom['coordinates']:
                n_geom.append(pyproj.transform(orsp, wgs84, point[0], point[1]))
    
            buffer.append(dict(type="Feature", \
            geometry=n_geom, properties=props))
            conter +=1 

# write the GeoJSON file
from json import dumps
geojson = open("c:/temp/trails.json", "w")
geojson.write(dumps({"type": "FeatureCollection",\
"features": buffer}, indent=2) + "\n")
geojson.close()

print 'done'
"""
{
  "type": "FeatureCollection",
  "features": [
    {
      "type": "Feature",
      "properties": {
        "id": "01",
        "steward_id": "1",
        "name": "",
        "motor_vehicles": "no",
        "foot": "yes",
        "bicycle": "no",
        "horse": "no",
        "ski": "no",
        "wheelchair": "no",
        "osm_tags": "surface=gravel; width=5"
      },
      "geometry": {
        "type": "LineString",
        "coordinates": [
          [
            -105.26275634765625,
            43.24320200099953
          ],
          [
            -105.71319580078125,
            43.42100882994726
          ],
          [
            -105.71319580078125,
            43.44100882994726
          ],
          [
            -105.68319580078125,
            43.44100882994726
          ]
        ]
      }
    },
  ]
}
"""