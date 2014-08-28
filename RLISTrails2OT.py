
# http://www.lfd.uci.edu/~gohlke/pythonlibs/#pyshp
import shapefile

# http://www.lfd.uci.edu/~gohlke/pythonlibs/#pyproj
import pyproj

# http://www.lfd.uci.edu/~gohlke/pythonlibs/#requests
import requests

import hashlib, collections, csv, os, sys, zipfile

# http://www.codeforamerica.org/specifications/trails/spec.html

TRAILS_URL = 'http://library.oregonmetro.gov/rlisdiscovery/trails.zip'

wgs84 = pyproj.Proj("+init=EPSG:4326") # LatLon with WGS84 datum used for geojson
orsp = pyproj.Proj("+init=EPSG:2913", preserve_units=True) # datum used by Oregon Metro

if not os.path.exists(os.getcwd()+'/src'):
    os.makedirs(os.getcwd()+'/src')

if not os.path.exists(os.getcwd()+'/output'):
    os.makedirs(os.getcwd()+'/output')

#download it

with open(os.getcwd()+'/src/trails.zip', 'wb') as handle:
    response = requests.get(TRAILS_URL, stream=True)

    if not response.ok:
        # Something went wrong
        print "Failed to download RLIS Trails"
        sys.exit()

    for block in response.iter_content(1024):
        if not block:
            break

        handle.write(block)

print 'Downloaded Trails'

#unzip it
zfile = zipfile.ZipFile(os.getcwd()+'/src/trails.zip')
for name in zfile.namelist():
  (dirname, filename) = os.path.split(name)
  zfile.extract(name, os.getcwd()+'/src/')
zfile.close()
print 'Unzipped Trails'

# read the shapefile
reader = shapefile.Reader(os.getcwd()+'/src/trails.shp')
fields = reader.fields[1:]
field_names = [field[0] for field in fields]
buffer = []

print 'Read shapefile into memory'

stewards = {}
named_trails = {}

def get_duplicates(arr):
    dup_arr = arr[:]
    for i in set(arr):
        dup_arr.remove(i)       
    return list(set(dup_arr)) 

for sr in reader.shapeRecords():
    
        atr = dict(zip(field_names, sr.record))

        # we're only allowing open trails to pass
        if atr['STATUS'].upper() == 'OPEN':
            props = collections.OrderedDict()

            # Hash the name and take the last six digits of the hex rep
            # In this way we can ensure that agencies get the same id each time
            # without having to maintain an agency id in house

            if atr['AGENCYNAME'] not in stewards.iterkeys():
                m = hashlib.sha224(atr['AGENCYNAME']).hexdigest()
                agency_id = str(int(m[-6:], 16))
                stewards[atr['AGENCYNAME']] = agency_id
                
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

            if trlname.strip() == "":
                if atr['SHAREDNAME'].strip() != "":
                   trlname = atr['SHAREDNAME']
                else:
                   trlname = "Unnamed"

            if trlname+'_'+trlsys not in named_trails.iterkeys():
                named_trails[trlname+'_'+trlsys] = [id]
            else:
                named_trails[trlname+'_'+trlsys].append(id)

            buffer.append(segment)

#Release the shapefile
reader = None

# write the GeoJSON file
from json import dumps
trail_segments = open(os.getcwd() + "/output/trail_segments.geojson", "w")
trail_segments.write(dumps({"type": "FeatureCollection",\
"features": buffer}, indent=2) + "\n")
trail_segments.close()

named_trails_out = open(os.getcwd() + "/output/named_trails.csv", "w")
named_trails_out.write('"name", "segment_ids", "id", "description", "part_of"\n')

print 'Created trail_segments.geojson'

uniqueness = []

for k, v in named_trails.iteritems():
    m = hashlib.sha224(k).hexdigest()
    id = str(int(m[-7:], 16))
    uniqueness.append(id)

    named_trails_out.write('"'+k.split('_')[0]+ '","'+';'.join(v)+'","'+id+'","","'+k.split('_')[1]+'"\n')
    
named_trails_out.close()

print 'Created named_trails.csv'

# simple check to ensure no collisions
# check named_trail_ids for dups
dups = get_duplicates(uniqueness)
print "duplicate ids: " + str(dups)

uniqueness = []

stewards_out = open(os.getcwd() + "/output/stewards.csv", "w")
stewards_out.write('"name","id","url","phone","address","publisher","license"\n')

for k, v in sorted(stewards.iteritems()):
    
    uniqueness.append(v)

    stewards_out.write('"'+k+'","'+v+'","","","","Oregon Metro - RLIS","Open Commons Open Database License (ODbL) and Content License (DbCL)"\n')

stewards_out.close()

print 'Created stewards.csv'

dups = get_duplicates(uniqueness)
print "duplicate ids: " + str(dups)

print 'done'
