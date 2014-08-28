RLIS Trails to Open Trail Specification
=================

A python conversion script for [RLIS Trails](http://rlisdiscovery.oregonmetro.gov/?action=viewDetail&layerID=2404) to the [Open Trail specification](http://www.codeforamerica.org/specifications/trails/spec.html)

* Aims to be lean on dependencies.
 * Does not require GDAL, shapely, arcpy etc.
* Not web-based.

In Brief
========
Order of operations
1. Download trails file from RLIS
2. Unzip
3. Read shapefile (into memory)
4. Create trails_segments.geojson
5. Create named_trails.csv
6. Create stewards.csv

Dependencies
============
If you have a compiler, you can run `pip install -r requirements.txt` but if not or you don't know,
go snag these installables for your correct platform and python version:

* [pyshp](http://www.lfd.uci.edu/~gohlke/pythonlibs/#pyshp)
* [pyproj](http://www.lfd.uci.edu/~gohlke/pythonlibs/#pyproj)
* [requests](http://www.lfd.uci.edu/~gohlke/pythonlibs/#requests)

Instructions
===========

* Clone or download the zipped repository
* Satisfy dependencies (see above)
* `>python RLISTRails2OT.py`

Disclaimers
==========

* We don't currently have a trailheads dataset



License
=======

* [Open Database and Content License](http://opendatacommons.org/licenses/odbl/)
* [RLIS version](http://www.oregonmetro.gov/sites/default/files/Open_Database_and_Content_Licenses.pdf)
