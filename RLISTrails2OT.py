#
#  _____   _____  _______ __   _      _______  ______ _______ _____         
# |     | |_____] |______ | \  |         |    |_____/ |_____|   |   |       
# |_____| |       |______ |  \_|         |    |    \_ |     | __|__ |_____  
#                                                                           
# _______  _____  __   _ _    _ _______  ______ _______ _____  _____  __   _
# |       |     | | \  |  \  /  |______ |_____/ |______   |   |     | | \  |
# |_____  |_____| |  \_|   \/   |______ |    \_ ______| __|__ |_____| |  \_|
#                                                                           

# http://www.lfd.uci.edu/~gohlke/pythonlibs/#pyshp
import shapefile

# http://www.lfd.uci.edu/~gohlke/pythonlibs/#pyproj
import pyproj

# http://www.lfd.uci.edu/~gohlke/pythonlibs/#requests
import requests

import hashlib, collections, csv, os, sys, zipfile

from json import dumps, loads

# http://www.codeforamerica.org/specifications/trails/spec.html

TRAILS_URL = 'http://library.oregonmetro.gov/rlisdiscovery/trails.zip'
ORCA_URL = 'http://library.oregonmetro.gov/rlisdiscovery/orca.zip'

WGS84 = pyproj.Proj("+init=EPSG:4326") # LatLon with WGS84 datum used for geojson
ORSP = pyproj.Proj("+init=EPSG:2913", preserve_units=True) # datum used by Oregon Metro

if not os.path.exists(os.getcwd()+'/output'):
    """
    Create a directory to hold the output
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

def process_trail_segments():
    stewards = {}
    named_trails = {}
    trail_segments = []

    # read the trails shapefile
    reader = shapefile.Reader(os.getcwd()+'/src/trails.shp')
    fields = reader.fields[1:]
    field_names = [field[0] for field in fields]

    #iterate trails
    for sr in reader.shapeRecords():
    
        atr = dict(zip(field_names, sr.record))

        # we're only allowing open trails to pass
        if atr['STATUS'].upper() == 'OPEN':
            props = collections.OrderedDict()

            # Hash the name and take the last six digits of the hex string
            # In this way we can ensure that agencies get the same id each time
            # without having to maintain an agency id in house.
            # Caveat: If the agency name changes ever so slightly, we'll lose the id persistence

            if atr['AGENCYNAME'] not in stewards.iterkeys():
                m = hashlib.sha224(atr['AGENCYNAME']).hexdigest()
                agency_id = str(int(m[-6:], 16))
                stewards[atr['AGENCYNAME']] = agency_id
            
            id = props['id'] = str(int(atr['TRAILID']))
            props['steward_id'] = stewards[atr['AGENCYNAME']]
            props['motor_vehicles'] = 'no'
            props['foot'] = 'yes' if atr['HIKE'] == 'Yes' else 'No'
            props['bicycle'] = 'yes' if atr['ROADBIKE'] == 'Yes'\
                or atr['MTNBIKE'] == 'Yes' else 'no'
            props['horse'] = 'yes' if atr['EQUESTRIAN'] == 'Yes' else 'no'
            props['ski'] = 'no'

            # spec: "yes", "no", "permissive", "designated"
            props['wheelchair'] = 'yes' if atr['ACCESSIBLE'] == 'Accessible' else 'no'

            props['osm_tags'] = 'surface='+atr['TRLSURFACE']+';width='+atr['WIDTH']

            # Assumes single part geometry == our (RLIS) trails.shp
            n_geom = []
            geom = sr.shape.__geo_interface__

            if geom['type'] !='LineString':
                print 'Encountered multipart...skipping'
                continue

            for point in geom['coordinates']:
                n_geom.append(pyproj.transform(ORSP, WGS84, point[0], point[1]))
            
            segment= collections.OrderedDict()
            segment['type']='Feature'
            segment['properties'] = props
            segment['geometry'] = {"type":"LineString", "coordinates":n_geom}

            # Establish parameters for named_trail.csv construction
            trlname= atr['TRAILNAME'].strip()
            trlsys = atr['SYSTEMNAME'].strip()

            #Trail name can fail to sharedname else unnamed.
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
    reader = None

    print ("Completed trails")
    return trail_segments, stewards, named_trails

def process_areas(stewards):
    # read the parks shapefile
    reader = shapefile.Reader(os.getcwd()+'/src/orca.shp')
    fields = reader.fields[1:]
    field_names = [field[0] for field in fields]

    areas = []
    counter = 0
    for sr in reader.shapeRecords():
        if counter == 10000: break #Take the 1st 10,000 features, ORCA is a supermassive YKW
        atr = dict(zip(field_names, sr.record))

        if atr['STATUS'] == 'Closed': #We don't want any closed sites to show up.
            continue

        """
        SELECT * 
        FROM   orca 
        WHERE  county IN ( 'Clackamas', 'Multnomah', 'Washington' ) 
               AND ( ( ownlev1 IN ( 'Private', 'Non-Profits' ) 
                       AND ( unittype IN ( 'Natural Area', 'Other' ) 
                             AND recreation = 'Yes' ) 
                        OR conservation = 'High' ) 
                      OR ( ownlev1 NOT IN ( 'Private', 'Non-Profits' ) 
                           AND ( unittype = 'Other' 
                                 AND ( recreation = 'Yes' 
                                        OR conservation IN ( 'High', 'Medium' ) ) 
                                  OR unittype = 'Natural Area' ) ) 
                      OR ( ownlev2 = 'Non-profit Conservation' ) 
                      OR ( unittype = 'Park' ) ) 
        """

        if atr['COUNTY'] in ['Clackamas', 'Multnomah', 'Washington'] and ((atr['OWNLEV1'] in ['Private', 'Non-Profits'] and (atr['UNITTYPE'] in ['Natural Area', 'Other'] and atr['RECREATION']=='Yes') or atr['CONSERVATI']=='High') or (atr['OWNLEV1'] not in ['Private', 'Non-Profits'] and (atr['UNITTYPE']== 'Other' and (atr['RECREATION']=='Yes' or atr['CONSERVATI'] in ['High', 'Medium']) or atr['UNITTYPE'] == 'Natural Area') ) or atr['OWNLEV2'] == 'Non-profit Conservation' or atr['UNITTYPE']== 'Park'):

            props = collections.OrderedDict()

            if atr['MANAGER'] not in stewards.iterkeys():
                m = hashlib.sha224(atr['MANAGER']).hexdigest()
                agency_id = str(int(m[-6:], 16))
                stewards[atr['MANAGER']] = agency_id

            geom = sr.shape.__geo_interface__

            if geom['type'] == 'MultiPolygon':
                polys=[]
                for poly in geom['coordinates']:
                    rings = []
                    for ring in poly:
                        n_geom = []
                        for point in ring:
                            n_geom.append(pyproj.transform(ORSP, WGS84, point[0], point[1]))
                        rings.append(n_geom)
                    polys.append(rings)

                new_geom = {"type":"MultiPolygon", "coordinates":polys}
            else:
                rings = []
                for ring in geom['coordinates']:
                    n_geom = []
                    for point in ring:
                        n_geom.append(pyproj.transform(ORSP, WGS84, point[0], point[1]))
                    rings.append(n_geom)
                new_geom = {"type":"Polygon", "coordinates":rings}

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
            _area['geometry'] = new_geom

            areas.append(_area)

            counter +=1
    # free up the shp file.
    reader = None

    return areas, stewards

if __name__ == "__main__":

    #####################################################
    # Download data from RLIS
    #
    download(TRAILS_URL, 'trails')
    download(ORCA_URL, 'orca')
    #
    #####################################################

    #####################################################
    # Load objects and arrays with calls to core functions
    #
    trail_segments, stewards, named_trails = process_trail_segments()
    
    areas, stewards = process_areas(stewards)
    #
    ######################################################

    ######################################################
    # write trail_segments.geojson
    #
    trail_segments_out = open(os.getcwd() + "/output/trail_segments.geojson", "w")
    trail_segments_out.write(dumps({"type": "FeatureCollection",\
    "features": trail_segments}, indent=2) + "\n")
    trail_segments_out.close()

    print 'Created trail_segments.geojson'
    #
    ######################################################

    ######################################################
    # write named_trails.csv
    #
    named_trails_out = open(os.getcwd() + "/output/named_trails.csv", "w")
    named_trails_out.write('"name","segment_ids","id","description","part_of"\n')

    uniqueness = []

    for k, v in named_trails.iteritems():
        m = hashlib.sha224(k).hexdigest()
        id = str(int(m[-7:], 16))
        uniqueness.append(id)

        named_trails_out.write('"'+k.split('_')[0]+ '","'+';'.join(v)+'","'+id+'","","'+k.split('_')[1]+'"\n')
    
    named_trails_out.close()

    # simple check: named_trail.id for dups to ensure no collisions
    print "duplicate ids: " + str(get_duplicates(uniqueness))

    print 'Created named_trails.csv'
    #
    ########################################################


    ########################################################
    # write stewards.csv
    #
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

    # simple check stewards.id for dups to ensure no collisions
    print "duplicate ids: " + str(get_duplicates(uniqueness))

    print 'Created stewards.csv'
    #
    ######################################################


    ########################################################
    # write areas.geojson
    #
    areas_out = open(os.getcwd()+"/output/areas.geojson", "w")
    areas_out.write(dumps({"type": "FeatureCollection",\
    "features": areas}, indent=2) + "\n")
    areas_out.close()

    print 'Created areas.geojson'
    #
    ######################################################

    print 'Process complete'