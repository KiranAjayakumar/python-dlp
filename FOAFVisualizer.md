FOAFVisualizer

See: [source](http://python-dlp.googlecode.com/svn/trunk/foaf-visualize/FOAFVisualize.py)

# Introduction #

Takes a set of RDF graphs and (using Kaleidos) generates a parameterized graph of the social network.  A list of nicks can be given to limit the graph to only those 'nodes' (or people)

# Dependencies #

  * [Boost Graph Library - Python Bindings](http://www.generic-programming.org/~dgregor/bgl-python/)

# Details #

Command-line help:

```
chimezie@laptop:~/workspace/python-dlp/foaf-visualize$ python FOAFVisualize.py 
FOAFVisualize.py [--help] [--stdin] [--nicks=<.. foaf nicks ..>] [--output=<.. output.dot ..>] [--input-format=<'n3' or 'xml'>] [--ns=prefix=namespaceUri] --input=<facts1.n3,facts2.n3,..>
```

Example diagram:

![http://python-dlp.googlecode.com/svn/trunk/foaf-visualize/visualizer-test.png](http://python-dlp.googlecode.com/svn/trunk/foaf-visualize/visualizer-test.png)

Generated via:

```
chimezie@laptop:~/workspace/python-dlp/foaf-visualize$ python FOAFVisualize.py --nicks=eikeon,DanC,chimezie,hhalpin --input=webwho.xrdf,harry.rdf,danc.rdf,eikeon.rdf --output=webwho.dot;circo -Tsvg -o webwho.svg webwho.dot
```