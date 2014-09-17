#
#  _____   _____  _______ __   _      _______  ______ _______ _____         
# |     | |_____] |______ | \  |         |    |_____/ |_____|   |   |       
# |_____| |       |______ |  \_|         |    |    \_ |     | __|__ |_____  
#                                                                           
# _______  _____  __   _ _    _ _______  ______ _______ _____  _____  __   _
# |       |     | | \  |  \  /  |______ |_____/ |______   |   |     | | \  |
# |_____  |_____| |  \_|   \/   |______ |    \_ ______| __|__ |_____| |  \_|
#                                                                           
#                                             ...:bns wrecking crew rulez:...

# http://www.lfd.uci.edu/~gohlke/pythonlibs/#pyshp
import shapefile

# http://www.lfd.uci.edu/~gohlke/pythonlibs/#pyproj
import pyproj

# http://www.lfd.uci.edu/~gohlke/pythonlibs/#requests
import requests

import hashlib, collections, csv, os, sys, zipfile

# http://www.codeforamerica.org/specifications/trails/spec.html

TRAILS_URL = 'http://library.oregonmetro.gov/rlisdiscovery/trails.zip'
ORCA_URL = 'http://library.oregonmetro.gov/rlisdiscovery/orca.zip'

WGS84 = pyproj.Proj("+init=EPSG:4326") # LatLon with WGS84 datum used for geojson
ORSP = pyproj.Proj("+init=EPSG:2913", preserve_units=True) # datum used by Oregon Metro


if not os.path.exists(os.getcwd()+'/output'):
    """
    Create a directory to hold hte output
    """
    os.makedirs(os.getcwd()+'/output')

def get_duplicates(arr):
    """
    helper function to check for duplicate ids
    """
    dup_arr = arr[:]
    for i in set(arr):
        dup_arr.remove(i)       
    return list(set(dup_arr)) 

def download(path, file):
    if not os.path.exists(os.getcwd()+'/src'):
        os.makedirs(os.getcwd()+'/src')

    with open(os.getcwd()+'/src/'+file+'.zip', 'wb') as handle:
        response = requests.get(path, stream=True)

        if not response.ok:
            # Something went wrong
            print "Failed to download "+file
            sys.exit()

        for block in response.iter_content(1024):
            if not block:
                break

            handle.write(block)
    print 'Downloaded '+file
    unzip(file)
    print 'Unzipped '+file

def unzip(file):
    zfile = zipfile.ZipFile(os.getcwd()+'/src/'+file+'.zip')
    for name in zfile.namelist():
        (dirname, filename) = os.path.split(name)
        zfile.extract(name, os.getcwd()+'/src/')
    zfile.close()

if __name__ == 'main':

    download(TRAILS_URL, 'trails')
    download(ORCA_URL, 'orca')

    # read the trails shapefile
    reader = shapefile.Reader(os.getcwd()+'/src/trails.shp')
    fields = reader.fields[1:]
    field_names = [field[0] for field in fields]

    trail_segments = []
    stewards = {}
    named_trails = {}

    #iterate trails
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
                """
            #Field massage
            id = props['id'] = str(int(atr['TRAILID']))
            props['steward_id'] = stewards[atr['AGENCYNAME']]
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
                n_geom.append(pyproj.transform(ORSP, WGS84, point[0], point[1]))
            
            segment= collections.OrderedDict()
            segment['type']='Feature'
            segment['properties'] = props
            segment['geometry'] = {"type":"LineString", "coordinates":n_geom}

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

            trail_segments.append(segment)

    #Release the trails shapefile
    #reader = None
    print ("Completed trails")

    # read the parks shapefile
    reader = shapefile.Reader(os.getcwd()+'/src/orca.shp')
    fields = reader.fields[1:]
    field_names = [field[0] for field in fields]

    areas = []

    for sr in reader.shapeRecords():
    
        atr = dict(zip(field_names, sr.record))

        #Horrid horribleness definition Query
        if atr['COUNTY'] in ['Clackamas', 'Multnomah', 'Washington'] and (atr['OWNLEV1'] in ['Private', 'Non-Profits'] and (atr['UNITTYPE'] in ['Natural Area', 'Other'] and atr['RECREATION']=='Yes') or atr['CONSERVATI']=='High') or (atr['OWNLEV1'] not in ['Private', 'Non-Profits'] and (atr['UNITTYPE']== 'Other' and (atr['RECREATION']=='Yes' or atr['CONSERVATI'] in ['High', 'Medium']) or atr['UNITTYPE'] == 'Natural Area') ) or atr['OWNLEV2'] == 'Non-profit Conservation' or atr['UNITTYPE']== 'Park':

            props = collections.OrderedDict()

            if atr['MANAGER'] not in stewards.iterkeys():
                m = hashlib.sha224(atr['MANAGER']).hexdigest()
                agency_id = str(int(m[-6:], 16))
                stewards[atr['MANAGER']] = agency_id

            geom = sr.shape.__geo_interface__
            rings = []
            for ring in geom['coordinates']:
                n_geom = []
                for point in ring:
                    n_geom.append(pyproj.transform(ORSP, WGS84, point[0], point[1]))
                rings.append(n_geom)

            rings = {"type":"Polygon", "coordinates":rings}

            props['name'] = atr['SITENAME']

            m = hashlib.sha224(atr['SITENAME']+atr['MANAGER']).hexdigest()
            orca_id = str(int(m[-6:], 16))

            props['id'] = orca_id
            props['steward_id'] = stewards[atr['MANAGER']]
            props['url'] = ''
            props['osm_tags'] = ''

            _area= collections.OrderedDict()
            _area['type']='Feature'
            _area['properties'] = props
            _area['geometry'] = rings

            areas.append(_area)
    # free up the shp file.
    reader = None


    ######################################################
    # write trail_segments.geojson
    #
    from json import dumps, loads
    trail_segments_out = open(os.getcwd() + "/output/trail_segments.geojson", "w")
    trail_segments_out.write(dumps({"type": "FeatureCollection",\
    "features": trail_segments}, indent=2) + "\n")
    trail_segments_out.close()

    print 'Created trail_segments.geojson'
    #
    ######################################################

    ######################################################
    # write trail_names.csv
    #
    named_trails_out = open(os.getcwd() + "/output/named_trails.csv", "w")
    named_trails_out.write('"name", "segment_ids", "id", "description", "part_of"\n')

    #
    ########################################################


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

    # load in the /data/stewards.json file 
    # in order to lookup the address, url and phone.
    steward_lookups = open(os.getcwd() + "/ref/stewards.json")
    slookup = loads(steward_lookups.read())
    steward_lookups.close()

    stewards_out = open(os.getcwd() + "/output/stewards.csv", "w")
    stewards_out.write('"name","id","url","phone","address","publisher","license"\n')

    for k, v in sorted(stewards.iteritems()):
    
        uniqueness.append(v)

        # basically looking up 
        obj = next((x for x in slookup if x['name'] == k), {'url':'', 'phone': '', 'address':''})
    
        stewards_out.write('"'+k+'","'+v+'","'+obj['url']+'","'+obj['phone']+'","'+obj['address']+'","Oregon Metro - RLIS","Open Commons Open Database License (ODbL) and Content License (DbCL)"\n')

    stewards_out.close()

    print 'Created stewards.csv'

    dups = get_duplicates(uniqueness)
    print "duplicate ids: " + str(dups)

    areas_out = open(os.getcwd()+"/output/areas.geojson", "w")
    areas_out.write(dumps({"type": "FeatureCollection",\
    "features": areas}, indent=2) + "\n")
    areas_out.close()

    print 'done'
