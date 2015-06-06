

This wiki lists the major points of divergence from rdflib 3.0 beyond just the differences in the new APIs.  It mostly chronicles modifications that were made since [this](http://code.google.com/p/rdflib/source/detail?r=1658) merge from a mercurial maintenance branch used for a [patient registry](http://www.w3.org/2001/sw/sweo/public/UseCases/ClevelandClinic/).

# Installation #

The source is located here _[/trunk/layercake-python/](http://code.google.com/p/python-dlp/source/browse/trunk/#trunk/layercake-python)_ and can be checked out from the Google Code [subversion](http://subversion.apache.org/) repository this way:

```
svn checkout http://python-dlp.googlecode.com/svn/trunk/ python-dlp
```

See the [Source](http://code.google.com/p/python-dlp/source/checkout) tab for more information.

Once the directory has been checked out, you can install the module (see: [Installing Python Modules](http://docs.python.org/install/index.html#the-new-standard-distutils)) it to your local machine by running the following command in the root directory of the local copy of the source tree:

```
$ python setup.py install
```

Once, you have done this, the [scripts](#Command-line_scripts.md) below should be available to use.

# Details #

  * Various fixes to the in-memory, [sparql-p](http://www.ivan-herman.net/Misc/2010/sparqlDesc.html) based SPARQL algebra implementation
  * Various fixes to [SPARQL-to-SQL](http://chimezie.posterous.com/a-complete-translation-from-sparql-into-effic) implementation (including significant performance enhancements)
    * Support for told BNode queries (queries with BNodes having explicit labels - _:a are matched by name)
    * ASK query fixes
  * Completely removed old C parser (so it is 100% Python again)_

# Additional SPARQL Layers #

New **sparql\_query** method on all Store instances and a default that is a 'native' SPARQL implementation based on sparql-p's expansion trees layered on top of the read-only RDF APIs of the underlying store

# Generic SPARQL Store #

Added rdflib.store.SPARQL store which is an implementation of the readonly subset of the APIs to use SPARQL against a remote endpoint.  Augments Ivan Herman's [SPARQL Endpoint interface to Python](http://ivan-herman.name/2007/07/06/sparql-endpoint-interface-to-python/) in the following ways:
  * Support for namespace binding
  * Replaced 'native' Python XML DOM api with 4Suite-XML Domlette
  * Incorporated as an rdflib store

# GRDDL Implementation with Amara #

It also [includes](http://code.google.com/p/python-dlp/source/browse/trunk/layercake-python/rdflib_tools/GRDDLAmara.py) an updated version of GRDDL.py ported to work with [Amara 2](http://xml3k.org/Amara2) (the successor to 4Suite XML).

# Command-line scripts #

There are several command-line scripts installed along with this package and are described briefly after the list below:
  * rdfpipe
  * mysql-rdfload
  * dataset-description
  * sparqler

## rdfpipe Command-line Script ##

This command-line script is used for parsing and serializing RDF document using the supported RDF formats both from files and from STDIN

The command-line help is
```
USAGE: RDFPipe.py [options]
    
    Options:
    
      --stdin                     Parse RDF from STDIN (useful for piping)
      --help                      
      --input-format              Format of the input document(s).  One of:
                                  'xml','trix','n3','nt','rdfa'
      --output                    Format of the final serialized RDF graph.  One of:
                                  'n3','xml','pretty-xml','turtle',or 'nt'
      --ns=prefix=namespaceUri    Register a namespace binding (QName prefix to a 
                                  base URI).  This can be used more than once
```

## mysql-rdfload Command-line Script ##

This script is used for the initial large-scale loading of a MySQL-backed store.

The command-line help is
```
Usage: mysql-rdfload [options] <DB Type> [records directory] [records directory] ..

Options:
  -h, --help            show this help message and exit
  -c CONNECTION, --connection=CONNECTION
                        Database connection string
  -i ID, --id=ID        Database table set identifier
  --delimited=DELIMITED
                        Directory in which to store delimited files
  -r, --reuse           Reuse existing delimited files instead of creating new
                        ones
  -u URI, --uri=URI     Target GRAPH URI / Name
  --uriList=URI         A list of URIs (similar to -u) but one per record
                        directory if multiple are given
  -p URI PATTERN, --uriPattern=URI PATTERN
                        Target GRAPH URI / Name pattern ({fName} and
                        {extension) are replaced with the filename and
                        extension of the source file
  --uriPatternList=URI PATTERN
                        A list of URI patterns (similar to -p) but one per
                        record directory if multiple are given
  -d, --delete          Delete old repository before starting
  -e EXT=FORMAT, --extensionMap=EXT=FORMAT
                        2 item Tuple of file extension and input format
  --input-format=RDF_FORMAT
                        The format of the RDF document(s) which serve as the
                        initial facts  for the RETE network. One of
                        'xml','n3','trix', 'nt', or 'rdfa'.  The default is
                        xml
  --name=GRAPHNAME      The name of the graph to parse the RDF
                        serialization(s) into
```

## dataset-description Command-line Script ##

This script returns a document describing the dataset (or ConjunctiveGraph) indicated by the given options using the [SPARQL service description document vocabulary](http://www.w3.org/TR/sparql11-service-description/)

The command-line help is
```
Usage: dataset-description [options] <DB Type>

Options:
  -h, --help            show this help message and exit
  -c CONNECTION, --connection=CONNECTION
                        Database connection string
  -i ID, --id=ID        Database table set identifier
```

## sparqler Command-line Script ##

This command-line is used for dispatching SPARQL queries against the indicated dataset

The command-line help is
```
Usage: sparqler [options] \
    <DB connection string> <DB table identifier> <SPARQL query string>

Options:
  -h, --help            show this help message and exit
  -s STORE, --storeKind=STORE
                        Use this type of DB
  --owl=OWL             Owl file used to help identify literal and resource
                        properties
  --rdfs=RDFS           RDFS file used to help identify literal and resource
                        properties
  -d, --debug           Enable (store-level) debugging
  --sparqlDebug         Enable (SPARQL evaluation) debugging
  --file=FILE           File to load SPARQL from
  --timing              Whether or not to print out timing information
  -l URI, --literal=URI
                        Add URI to the list of literal properties
  -p, --profile         Enable profiling statistics
  -r URI, --resource=URI
                        Add URI to the list of resource properties
  --ns=PREFIX=URI       Register a namespace binding (QName prefix to a base
                        URI).  This can be used more than once
```

# Acknowledgements: #

  * [Brian Beck](http://code.google.com/u/exogen/)
  * [John Clark](http://code.google.com/u/John.L.Clark/)
  * [Brendan Elliot](http://code.google.com/u/risukun/)
  * Ivan Herman
  * Uche Ogbuji