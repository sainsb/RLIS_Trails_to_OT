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

import json

import csv

# http://www.codeforamerica.org/specifications/trails/spec.html

TRAILS_URL = 'http://library.oregonmetro.gov/rlisdiscovery/trails.zip'

WGS84 = pyproj.Proj("+init=EPSG:4326") # LatLon with WGS84 datum used for geojson
ORSP = pyproj.Proj("+init=EPSG:2913", preserve_units=True) # datum used by Oregon Metro

STEWARDS = []
ORCA_SITES = {}

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

def get_steward_id(steward):
    try:
      id = [x['steward_id'] for x in STEWARDS if x["name"] == steward][0]
      return id
    except IndexError as e:
        #Crap stewards
        if steward=='Home Owner Association': return 9999 #private
        if steward=='North Clackamas Parks and Recreation Department': return 58672 #should be district
        if steward=='United States Fish & Wildlife' : return 43262
        if steward=='Wood Village Parks & Recreation' : return 8348
        if steward is None: return 9999 #private
        return 9999

def compare_segment_arrays(a, b):
  if len(a) != len(b): return False
  for n in a:
    if n in b:
      continue
    else:
      return False
  return True

def is_subset(a,b):
  foo=True
  for val in a:
    if val in b:
      continue
    else:
      #print val
      foo= False
  return foo

def process_trail_segments():
    trail_segments = []
    named_trails = []

    # read the trails shapefile
    reader = shapefile.Reader(os.getcwd()+'/src/trails.shp')
    fields = reader.fields[1:]
    field_names = [field[0] for field in fields]

    #iterate trails
    for sr in reader.shapeRecords():

        atr = dict(zip(field_names, sr.record))

        # we're only allowing open existing trails to pass
        if atr['STATUS'].upper() == 'OPEN' and atr['SYSTEMTYPE'].upper() != 'OTHER' and atr['TRLSURFACE'] != 'Water':
            props = collections.OrderedDict()

            #effectively join to the stewards table
            id = props['id'] = str(int(atr['TRAILID']))
            props['steward_id'] = get_steward_id(atr['AGENCYNAME'])
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

            trail_segments.append(segment)

            if atr['TRAILNAME'] != None and '   ' not in atr['TRAILNAME']:
              if len([x for x in named_trails if x["atomic_name"]==atr['TRAILNAME']+'|'+atr['COUNTY']])==0:
                named_trails.append({'atomic_name': atr['TRAILNAME']+'|'+atr['COUNTY'], 'name':atr['TRAILNAME'],'segment_ids':[atr['TRAILID']]})
              else:
                [x for x in named_trails if x["atomic_name"]==atr['TRAILNAME']+'|'+atr['COUNTY']][0]['segment_ids'].append(atr['TRAILID'])

            if atr['SYSTEMNAME'] != None and '   ' not in atr['SYSTEMNAME']:
              if len([x for x in named_trails if x['atomic_name']==atr['SYSTEMNAME']])==0:
                named_trails.append({'atomic_name': atr['SYSTEMNAME'], 'name':atr['SYSTEMNAME'],'segment_ids':[atr['TRAILID']]})
              else:
                [x for x in named_trails if x["atomic_name"]==atr['SYSTEMNAME']][0]['segment_ids'].append(atr['TRAILID'])

            if atr['SHAREDNAME'] != None and '   ' not in atr['SHAREDNAME']:
              if len([x for x in named_trails if x['atomic_name']==atr['SHAREDNAME']])==0:
                named_trails.append({'atomic_name': atr['SHAREDNAME'], 'name':atr['SHAREDNAME'],'segment_ids':[atr['TRAILID']]})
              else:
                [x for x in named_trails if x["atomic_name"]==atr['SHAREDNAME']][0]['segment_ids'].append(atr['TRAILID'])

    #Release the trails shapefile

    reader = None

    #step 1
    #remove duplicate geometries in named_trails
    all_arrays = []
    for trail in named_trails: all_arrays.append(trail['segment_ids'])

    #identify duplicate geometries
    duplicates = [x for x in named_trails if len([y for y in all_arrays if compare_segment_arrays(x['segment_ids'],y)])>1]

    glob_segs = None

    counter = 0
    for dup in duplicates:
      if glob_segs is None or not compare_segment_arrays(dup['segment_ids'],glob_segs):

        #find ur buddy
        d = [x for x in duplicates if compare_segment_arrays(x['segment_ids'],dup['segment_ids'])]
        glob_segs = dup['segment_ids']

        to_remove = [x for x in d if '|' in x['atomic_name']]

        if len(to_remove) == 1:
          named_trails.remove(to_remove[0])
        else:
          print 'no piped atomic name... I dunno'

    #step 2 - remove atomically stored trails (with county) that are pure
    # subsets of a regional trail superset
    glob_name = None
    for trail in named_trails:
      if glob_name is None or trail['name'] != glob_name:
        dups = [x for x in named_trails if x['name']==trail['name']]
        glob_name = trail['name']

        #determine the dup with the most segs *heinous*
        superset = max(enumerate(dups), key = lambda tup: len(tup[1]['segment_ids']))
        superitem = [x for x in dups if x==superset[1]][0]

        for dup in dups:
          if len(dup['segment_ids']) != len(superitem['segment_ids']):
            foo =is_subset(dup['segment_ids'], superitem['segment_ids'])
            if foo and '|' in dup['atomic_name']:
              #print 'Removed '+dup['atomic_name'] + ' from named_trails'
              named_trails.remove(dup)
        glob_name = trail['name']

    #step 3 - remove atomically stored trails (with county) that are
    # *impure* subsets of a regional trail superset
    #this sucks
    #So let's look for where the name matches the atomic name of an existing
    #named trail - the assumption being that the atomic name of a regional
    #trail will not include the pipe '|' and county
    to_delete=[]

    for trail in named_trails:
      if '|' in trail['atomic_name']:
        for test_trail in named_trails:
          if trail['name'] == test_trail['atomic_name']:
            #print trail['name'] + ' combined with regional trail'
            #Insert whatever segments in trail that aren't in
            #test_trail

            for segment in trail['segment_ids']:
              if segment not in test_trail['segment_ids']:
                test_trail['segment_ids'].append(segment)

            #append to to_delete
            to_delete.append(trail)

    #delete
    for trail in to_delete:
      named_trails.remove(trail)

    #step 4 - assign named trail id from reference table
    for trail in named_trails:
      if '|' in trail['atomic_name']:
        county = trail['atomic_name'].split('|')[1].strip()
        name =  trail['atomic_name'].split('|')[0].strip()

      else: #don't need the county == blank
        name = trail['atomic_name']
        county = ''

      id= [x for x in NAMED_TRAIL_IDS if x[1]==county and x[2]==name]

      if len(id)==0:
        print '*' +name+' || '+ county # no id in named_trails
      else:
        [x for x in named_trails if x['atomic_name']==trail['atomic_name']][0]['named_trail_id'] = id[0]

    #step 5 - remove atomic name
    for n in named_trails:
      n.pop('atomic_name')

    print ("Completed trails")

    return trail_segments, named_trails

def process_areas():
    # read the parks shapefile
    reader = shapefile.Reader(os.getcwd()+'/src/orca_sites.shp') #this is actually ORCA_sites_beta
    fields = reader.fields[1:]
    field_names = [field[0] for field in fields]

    areas = []
    counter = 0
    for sr in reader.shapeRecords():
        # if counter == 10000: break #Take the 1st 10,000 features, ORCA is a supermassive YKW
        atr = dict(zip(field_names, sr.record))

        # if atr['STATUS'] == 'Closed': #We don't want any closed sites to show up.
        #     continue

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

        # if atr['COUNTY'] in ['Clackamas', 'Multnomah', 'Washington'] and ((atr['OWNLEV1'] in ['Private', 'Non-Profits'] and (atr['UNITTYPE'] in ['Natural Area', 'Other'] and atr['RECREATION']=='Yes') or atr['CONSERVATI']=='High') or (atr['OWNLEV1'] not in ['Private', 'Non-Profits'] and (atr['UNITTYPE']== 'Other' and (atr['RECREATION']=='Yes' or atr['CONSERVATI'] in ['High', 'Medium']) or atr['UNITTYPE'] == 'Natural Area') ) or atr['OWNLEV2'] == 'Non-profit Conservation' or atr['UNITTYPE']== 'Park'):
        if 1:
            props = collections.OrderedDict()

            # if atr['MANAGER'] not in stewards.iterkeys():
            #     m = hashlib.sha224(atr['MANAGER']).hexdigest()
            #     agency_id = str(int(m[-6:], 16))
            #     stewards[atr['MANAGER']] = agency_id

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

            props['id'] = int(atr['DISSOLVEID'])
            if props['id'] in ORCA_SITES:
                props['steward_id'] = ORCA_SITES[props['id']]
            else:
                props['steward_id'] = 0
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

    return areas

if __name__ == "__main__":

    #####################################################
    # Download data from RLIS
    #
    # download(TRAILS_URL, 'trails')
    #download(ORCA_URL, 'orca')
    #
    #####################################################

    #####################################################
    # Load Stewards into Python object
    #
    with open(os.getcwd() + "/output/stewards.csv", mode='r') as infile:
      reader = csv.DictReader(infile, ['steward_id', 'name', 'url', 'phone', 'address','publisher', 'license']) #stewards.csv header
      reader.next()
      for row in reader:
        STEWARDS.append(row)
      for row in STEWARDS:
        row['steward_id'] = int(row['steward_id'])
    print "sucked up stewards"
    #
    #
    #####################################################

    #####################################################
    # Load Named Trails into Python object
    #
    with open(os.getcwd() + "/ref/named_trails_lookup.csv", mode='r') as infile:
      reader = csv.reader(infile)
      reader.next() #skip header line
      NAMED_TRAIL_IDS = list(reader)
      for row in NAMED_TRAIL_IDS:
        row[0] = int(row[0])
    print "Sucked up Named trail ids"

    #####################################################
    # Load Named Trails into Python object
    #
    with open(os.getcwd() + "/ref/orca_sites_to_steward.csv", mode='r') as infile:
      reader = csv.reader(infile)
      reader.next() #skip header line

      for row in reader:
        # print row
        ORCA_SITES[int(row[0])] = int(row[1])
    print "Sucked up orca sites"

    #
    #
    #####################################################

    #####################################################
    # Load objects and arrays with calls to core functions
    #
    trail_segments, named_trails = process_trail_segments()

    ######################################################
    # write named_trails.csv
    #
    named_trails_out = open(os.getcwd() + "/output/named_trails.csv", "w")
    named_trails_out.write('"name","segment_ids","id","description","part_of"\n')

    for named_trail in named_trails:
      try: #horrible hack for trails that are in the current (2014 Q4) Trails download in RLIS
        #discovery that are not in named_trails.csv because they were removed or whatever...
        named_trails_out.write(named_trail['name']+","+ ";".join(str(x) for x in named_trail['segment_ids'])+","+ str(named_trail['named_trail_id'][0]) + ",,\n")
      except:
        pass

    named_trails_out.close()

    print 'Created named_trails.csv'
    #
    ########################################################

    ########################################################
    # write trail_segments.geojson
    #
    trail_segments_out = open(os.getcwd() + "/output/trail_segments.geojson", "w")
    trail_segments_out.write(json.dumps({"type": "FeatureCollection",\
    "features": trail_segments}, indent=2) + "\n")
    trail_segments_out.close()

    print 'Created trail_segments.geojson'
    #
    ########################################################

    # sys.exit(1)

    areas= process_areas()

    ########################################################
    # write areas.geojson
    #
    areas_out = open(os.getcwd()+"/output/areas.geojson", "w")
    areas_out.write(json.dumps({"type": "FeatureCollection",\
    "features": areas}, indent=2, encoding="Latin1") + "\n")
    areas_out.close()

    print 'Created areas.geojson'
    #
    ########################################################

    print 'Process complete'
