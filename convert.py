
# http://www.lfd.uci.edu/~gohlke/pythonlibs/#pyshp
import shapefile

# http://www.lfd.uci.edu/~gohlke/pythonlibs/#pyproj
import pyproj

# http://www.lfd.uci.edu/~gohlke/pythonlibs/#requests
import requests

import hashlib, collections, csv

# http://www.codeforamerica.org/specifications/trails/spec.html

wgs84 = pyproj.Proj("+init=EPSG:4326") # LatLon with WGS84 datum used for geojson
orsp = pyproj.Proj("+init=EPSG:2913", preserve_units=True) # datum used by Oregon Metro

OUTPUT_PATH = "d:/scratch/transit/"

# read the shapefile
reader = shapefile.Reader("d:/scratch/transit/trails.shp")
fields = reader.fields[1:]
field_names = [field[0] for field in fields]
buffer = []
conter=0

agencies = {}
named_trails = {}

for sr in reader.shapeRecords():

    if conter < 100:

        atr = dict(zip(field_names, sr.record))

        # we're only allowing open trails to pass
        if atr['STATUS'].upper() == 'OPEN':
            props = collections.OrderedDict()

            # Hash the name and take the last six digits of the hex rep
            # In this way we can ensure that agencies get the same id each time
            # without having to maintain an agency id in house

            if atr['AGENCYNAME'] not in agencies.iterkeys():
                m = hashlib.sha224(atr['AGENCYNAME']).hexdigest()
                agency_id = str(int(m[-5:], 16))
                agencies[atr['AGENCYNAME']] = agency_id
                
                """
                t='Hillsboro Parks and Recreation'
                >>> m=hashlib.sha224(t).hexdigest()
                'c33f51592f1d24ef759d695dc05602a265832bc1a55918da3228ed08'
                >>> int(m[-5:], 16)
                584968
                """
            #Field massage
            id = props['id'] = str(int(atr['TRAILID']))
            props['steward_id'] = agency_id
            #props['name'] = atr['TRAILNAME'].strip()
            props['motor_vehicles'] = 'no'
            props['foot'] = 'yes' if atr['HIKE'] == 'Yes' else 'No'
            props['bicycle'] = 'yes' if atr['ROADBIKE'] == 'Yes'\
                or atr['MTNBIKE'] == 'Yes' else 'no'
            props['horse'] = 'yes' if atr['EQUESTRIAN'] == 'Yes' else 'no'
            props['ski'] = 'no'

            # spec: "yes", "no", "permissive", "designated"
            props['wheelchair'] = 'yes' if atr['ACCESSIBLE'] == 'Accessible' else 'no'

            props['osm_tags'] = 'surface='+atr['TRLSURFACE']+';width='+atr['WIDTH']

            n_geom = []
            geom = sr.shape.__geo_interface__
            for point in geom['coordinates']:
                n_geom.append(pyproj.transform(orsp, wgs84, point[0], point[1]))
            
            segment= collections.OrderedDict()
            segment['type']='Feature'
            segment['properties'] = props
            segment['geometry'] = n_geom

            trlname= atr['TRAILNAME'].strip()
            trlsys = atr['SYSTEMNAME'].strip()

            trlname = 'Unnamed' if trlname == "" else trlname

            if trlname+'_'+trlsys not in named_trails.iterkeys():
                named_trails[trlname+'_'+trlsys] = [id]
            else:
                named_trails[trlname+'_'+trlsys].append(id)

            buffer.append(segment)
            conter +=1

# write the GeoJSON file
from json import dumps
trail_segments = open(OUTPUT_PATH + "trail_segments.geojson", "w")
trail_segments.write(dumps({"type": "FeatureCollection",\
"features": buffer}, indent=2) + "\n")
trail_segments.close()

named_trails_out = open(OUTPUT_PATH + "named_trails.csv", "w")
named_trails_out.write("name", "segment_ids", "id", "description", "part_of\n")

for k, v in named_trails:
    

    named_trails_out.write(k.split('_')[0], ';'.join(v), 
    

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