![http://python-dlp.googlecode.com/files/Method-diagram.jpg](http://python-dlp.googlecode.com/files/Method-diagram.jpg)

**Note**: the [FMA](http://sig.biostr.washington.edu/projects/fm/) to SNOMED-CT _mapping_ / _segmenting_ / _transliteration_ capability (step 3-4)  is inert without the mapping file and corresponding database (more on this later).

# Introduction #

This is the implementation used for the Segmenting and Merging Domain-specific Ontology Modules for Clinical Informatics [method](http://copia.posterous.com/segmenting-and-merging-domain-specific-ontolo).

# Source #

See [source code](http://code.google.com/p/python-dlp/source/browse/trunk/clinical-ontology-modules) in subversion


# Installation #

## Software Dependencies ##

The following Python libraries are needed to use this module

  * [FuXi](http://code.google.com/p/fuxi/) (Uses its [OWL API](http://code.google.com/p/fuxi/wiki/InfixOwl) for creating and manipulating OWL/RDF graphs)
  * Either rdflib 2.4.+ or [layercake-python](http://code.google.com/p/python-dlp/wiki/LayerCakePythonDivergence) (needed by FuXi and used for managing / parsing / serializing OWL RDF graphs)
  * [MySQLdb](http://sourceforge.net/projects/mysql-python/) (Used to persist SNOMED-CT distribution files)
  * MySQL server and client (5.1 preferred)

## Loading SNOMED-CT ##

Below are step-by-step instructions for loading in a SNOMED-CT distribution into a MySQL database using this library.  The last release this has been tested on is the [distribution](http://www.nlm.nih.gov/research/umls/sourcereleasedocs/2010AA/SNOMEDCT/sourcerepresentation.html) released on January 31st 2010.

First, we need to create a MySQL database (we will call it _snomed\_distro_, but any valid database name will suffice)

```
$ mysql -u ..user.. -p
Enter password: 
Server version: 5.1.29-rc MySQL Community Server (GPL)

Type 'help;' or '\h' for help. Type '\c' to clear the buffer.

mysql> create database snomed_distro;
Query OK, 1 row affected (0.00 sec)

mysql> 
```

Next, I load the distribution files, passing their location to the _-l_ option:

```
$ python ManageSNOMED-CT.py --load \
   -l SnomedCT_INT_20100131/Terminology/Content \
   -s localhost \
  -f sct1_Concepts_Core_INT_20100131.txt,sct1_Descriptions_en_INT_20100131.txt,sct1_Relationships_Core_INT_20100131.txt,sct1_TextDefinitions_en-US_INT_20100131.txt \
  -u root \
  --password=..password..\
   -d snomed_distro  
SnomedCT_INT_20100131/Terminology/Content
Droping table Concepts
Droping table Descriptions
Droping table Relationships
Droping table Text_Definitions
Loading  Concepts
Executing:
LOAD DATA LOCAL INFILE 'SnomedCT_INT_20100131/Terminology/Content/sct1_Concepts_Core_INT_20100131.txt' IGNORE INTO TABLE Concepts IGNORE 1 LINES
Result:  ()
Loading  Descriptions
Executing:
LOAD DATA LOCAL INFILE 'SnomedCT_INT_20100131/Terminology/Content/sct1_Descriptions_en_INT_20100131.txt' IGNORE INTO TABLE Descriptions IGNORE 1 LINES
Result:  ()
Loading  Relationships
Executing:
LOAD DATA LOCAL INFILE 'SnomedCT_INT_20100131/Terminology/Content/sct1_Relationships_Core_INT_20100131.txt' IGNORE INTO TABLE Relationships IGNORE 1 LINES
Result:  ()
Loading  Text_Definitions
Executing:
LOAD DATA LOCAL INFILE 'SnomedCT_INT_20100131/Terminology/Content/sct1_TextDefinitions_en-US_INT_20100131.txt' IGNORE INTO TABLE Text_Definitions IGNORE 1 LINES
Result:  ()
```

Afterwards, I can verify the database has been loaded:

```
mysql> use snomed_distro;
Reading table information for completion of table and column names
You can turn off this feature to get a quicker startup with -A

Database changed
mysql> show tables;           
+-------------------------+
| Tables_in_snomed_distro |
+-------------------------+
| Concepts                | 
| Descriptions            | 
| Relationships           | 
| Text_Definitions        | 
+-------------------------+
4 rows in set (0.00 sec)

mysql> describe Concepts;
+--------------------+-------------+------+-----+---------+-------+
| Field              | Type        | Null | Key | Default | Extra |
+--------------------+-------------+------+-----+---------+-------+
| ConceptId          | char(18)    | NO   | PRI | NULL    |       | 
| ConceptStatus      | smallint(6) | NO   |     | NULL    |       | 
| FullySpecifiedName | text        | NO   |     | NULL    |       | 
| CTV3ID             | char(5)     | NO   |     | NULL    |       | 
| SNOMEDID           | text        | NO   |     | NULL    |       | 
| IsPrimitive        | smallint(6) | NO   |     | NULL    |       | 
+--------------------+-------------+------+-----+---------+-------+
6 rows in set (0.01 sec)
```

The table names follow the specifications described in the SNOMED-CT Technical Implementation Guide.  Finally, I can extract OWL axioms regarding essential hypertension (using the FuXi command-line tool to render them in the Manchester OWL syntax):

```
$ python ManageSNOMED-CT.py -e 59621000 \
    -s localhost \
    -u ..user.. \
   --password=..password.. \
   -d snomed_distro  | \
    FuXi --ns=sno=tag:info@ihtsdo.org,2007-07-31:SNOMED-CT# \
            --output=man-owl \
            --class=sno:EssentialHypertension \
            --stdin
..snip...
Class: sno:EssentialHypertension 
    ## Primitive Type (Essential hypertension) ##
    SNOMED-CT Code:  (a primitive concept)59621000
    SubClassOf: ( sno:hasDefinitionalManifestation some Finding of increased blood pressure )
                Hypertensive disorder
                ( sno:findingSite some Systemic arterial structure )
..snip..
```


# Command-line Options #

```
Usage: ManageSNOMED-CT.py [options]

Options:
  -h, --help            show this help message and exit
  --root=ROOT           Determines the termination point for the extraction
                        algorithm (either stop at the closest primitive
                        concept going upwards or at the very top of the SNOMED
                        taxonomy).  Respectively the value of this option can
                        be one of "primitive" or "root" (the default)
  --load                Load SNOMED-CT distribution files (in the current
                        directory) into a MySQL DB
  --verbose             Output debug print statements or not
  -e EXTRACT, --extract=EXTRACT
                        Extract an OWL representation from SNOMED-CT using the
                        comma-separated list of SNOMED-CT identifiers as the
                        starting point
  --snomedCore          Extract an OWL representation from SNOMED-CT using the
                        concepts with human readable definitions as the
                        starting point
  --extractFile=EXTRACTFILE
                        Same as --extract, except the comma-separated list of
                        SNOMED-CT identifiers are in the specified file
  -o OUTPUT, --output=OUTPUT
                        The name of the file to write out the OWL/RDF to
                        (STDOUT is used otherwise
  -n NORMALFORM, --normalForm=NORMALFORM
                        Whether to extract using the long normal form (long),
                        short normal form (short), or neither (- the default
                        -)
  -l LOCATION, --location=LOCATION
                        The directory where the delimited files or SNOMED-CT
                        -> FMA mappings will be loaded from (the default is
                        the current directory)
  -s SERVER, --server=SERVER
                        Host name of the MySQL database to connect to
  -f FILES, --files=FILES
                        A comma-separated list of distribution files to load
                        from in the order: concept, descriptions,
                        relationship, definition
  -p PORT, --port=PORT  The port to use when connecting to the MySQL database
  -w PASSWORD, --password=PASSWORD
                        Password
  -u USERNAME, --username=USERNAME
                        User name to use when connecting to the MySQL database
  -d DATABASE, --database=DATABASE
                        The name of the MySQL database to connect to
  --profile             Enable profiling statistics

```