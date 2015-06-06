

# Introduction #

This wiki describes how Triclops can be configured to be used with the MySQL /  SPARQL-to-SQL implementation.

The package comes with a skeletal configuration file ( SPARQLServer-sample.conf ) snippets of which are shown below This file should be copied and modified accordingly for one or more SPARQL servers

```
[DEFAULT]
#Configuration options for underlying RDFLib store
store_identifier=..store identifier.
```

The store identifier is usually given for a particular dataset. MySQL credentials are placed to use to connect to a particular database (also given). So, this file probably should not be readable by anyone except priviledged users (preferably the same one that launches the server)

```
connection=user=..change me..,password=..change me..,host=..change me..,db=.. change me..
store=MySQL
static_files=%(here)s/htdocs
```

The relevant OWL file for a dataset is also given.

```
#This is the path to the OWL file to use for optimizing SPARQL queries
datastore_owl=.. path to OWL file ..
```

Below is what should be used to register default namespace bindings:

```
#'|' delimited strings of the form _key_=_val_ where _key_ is a prefix and _val_ is the URI to bind it to
nsBindings=dc=http://purl.org/dc/terms/|obo=http://purl.org/obo/owl/obo#

#Whether or not to output additional (detailed) debugging information relevant
#to the SPARQL query evaluation process.  An absence of this variable is
#interpreted as being set to false (or 0)
debugQuery=1
```

This variable determines whether or not the MySQL query optimizer should evaluate BGPs in the given triple pattern order to allow it to use statistical data to determine an appropriate join order

```
#Whether or not to allow MySQL to use it's own methods to determine join order
#This cannot be used in conjunction with DISABLE_SELECTION_ESTIMATION.
#An absence of this variable is interpreted as being set to false (or 0)
MYSQL_ORDER=1
```

```
NO_BASE_RESOLUTION=1
```

In addition, a _endpoint_ variable needs to be set to the path of the main SPARQL service:

```
endpoint=/sparql/protocol
```

At this point, the server can be launched as a system daemon via:
```
paster serve someConfigurationFile.conf --daemon --log=someLogFileName.log --pid-file=somePidFileName.pid
```

A running SPARQL service can be stopped with the following command (note the given pid and log file must be the same as the one used to start the daemon):

```
 paster serve someConfigurationFile.conf --stop-daemon --log=someLogFileName.log --pid-file=somePidFileName.pid
```

This should be run from the working directory of Triclops

# Entailment Regime Configuration #

For now, see [log](http://code.google.com/p/python-dlp/source/detail?r=351) for commit

# SPARQL Query management #

Triclops can be setup for use in managing SPARQL queries and their results against either a local rdflib / [layercake-python](http://code.google.com/p/python-dlp/wiki/LayerCakePythonDivergence) dataset or a remote one via the proxy SPARQL endpoint capabilities described in the next secsion.  The following configuration directives need to be added to the section at the top (_composite:main_):

```
[composite:main] 
/codemirror = codemirror
/js         = codemirrorJs
/queryMgr   = queryMgr
```

The following sections are needed:

```
[app:queryMgr]
use = egg:Triclops#queryMgr

[app:codemirror]
use = egg:Paste#static
document_root = %(here)s/htdocs/codemirror

[app:codemirrorJs]
use = egg:Paste#static
document_root = %(here)s/htdocs/codemirror/js
```

This requires a symbolic link named _codemirror_ to be placed in the _htdocs_ subdirectory that points to the [codemirror](http://codemirror.net/) source tree.  This can be done by downloading the codemirror source archive, decompressing it in Triclops working directory and creating such a link.  Alternatively, it can be checked out via git:

```
$ git clone http://marijnhaverbeke.nl/git/codemirror
$ cd htdocs/
$ ln -s ../codemirror
```

In addition,  a _manageQueries_ variable needs to be set to the path (relative or absolute) to where the query documents and their results are stored for management.  In the example below, a sub directory in the working copy named queries is used.

```
manageQueries=queries
```

Finally, the _queryMgr_ variable needs to be set:

```
queryMgr = queryMgr
```

At this point, the server can be (re-)started and a browser can point to /queryMgr to pull up the query manager

# Proxy SPARQL Endpoint #

Using the _[SPARQL client library as Generic SPARQL Store](http://code.google.com/p/python-dlp/wiki/LayerCakePythonDivergence#Generic_SPARQL_Store)_ capability, Triclops can be used as a [SPARQL protocol for RDF](http://www.w3.org/TR/rdf-sparql-protocol/) [proxy server](http://en.wikipedia.org/wiki/Proxy_server) to a live SPARQL endpoint in the sense that it simply delegates the evaluation of SPARQL queries to the remote server but handles the rendering, (term-based) browsing of results from the query, query management, and query mediation.  The latter in particular can be achieved via [query mediation capabilities](http://code.google.com/p/fuxi/wiki/TopDownSW) over a remote SPARQL service

A remote [SPARQL endpoint](http://www.w3.org/TR/sparql11-service-description/#sd-endpoint) can be configured with the following entry in the configuration file:
```
sparql_proxy = ... SPARQL endpoint URL ...
```