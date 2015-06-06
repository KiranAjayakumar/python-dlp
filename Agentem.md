This is an architectural overview of a finite state machine for semantic web agents

# Introduction #

The motivation is a lack of any coherence in how a _semantic web agent_ (with more sophistication than just a [scutter](http://wiki.foaf-project.org/Scutter)) might go about consuming, processing, and acting upon RDF content retrieved from a "semantic web" in a semi-deterministic way.  Much of this is motivated by Jim Hendler's must-read article _[Where are the Agents?](http://www.mindswap.org/blog/2007/04/23/where-are-all-the-agents-long-form/)_ and a follow-up "answer": _[Where are the Semantic Agents?](http://www.multiagent.com/where-semantic-agents)_.

Furthermore, I feel that with all the inference capabilities FuXi is now equipped with, if there are no 'killer apps' that can immediately become cannon fodder, then there must be something naive (and perhaps vacuous) about the notion of a web of data with infinite value to autonomous agents.  At the very least, some consensus on an agent protocol that addresses the mechanisms that Web Architecture alone is not able facilitate is needed.  Agentem is an experimental python-dlp module to investigate what such a protocol should look like.  Much of this design sketch is motivated by the ESW wiki: [A "Humane" Policy for Intelligent Web Agents and Interpretation via RDF/OWL](http://esw.w3.org/topic/HCLS/WebClosureSocialConvention), [Tabulator: Exploring and Analyzing linked data on the Semantic Web](http://swui.semanticweb.org/swui06/papers/Berners-Lee/Berners-Lee.pdf) , and an older article on a scutter protocol for Redfoot (one of the "original" semantic web agent frameworks): _[A RESTful Scutter Protocol for Redfoot Kernel](http://web.archive.org/web/20070608074143/http://copia.ogbuji.net/blog/2006-01-29/A_RESTful_)_

# Parameters #

The finite state machine documented below is meant to be a parameterized process flow with the following variables

  * A list of RDF predicates which are considered _["Graph Links"](http://esw.w3.org/topic/HCLS/WebClosureSocialConvention#GraphLink)_
  * An indication of which of these predicates require a mandatory dereference of the target IRI
  * An integer representing the maximum recursion depth for traversing (optional) graph links

# FSM Diagram #

![http://python-dlp.googlecode.com/files/agentem.jpg](http://python-dlp.googlecode.com/files/agentem.jpg)


![http://python-dlp.googlecode.com/files/agentem2.jpg](http://python-dlp.googlecode.com/files/agentem2.jpg)

## Notes ##

The process states marked with an asterix are further discussed below (going in top-down order):

### Default, Provenance Graph for REST Metadata ###

This FSM is meant to _drive_ a single [RDF dataset](http://www.w3.org/TR/rdf-sparql-query/#rdfDataset).  In particular, the default graph is used for persisting HTTP request headers for use in constructing RESTful, subsequent requests for RDF graphs.  This allows strong-caching such that the same graph (linked from distinct directions) will only be parsed once if the server supports HTTP headers such as If-Modified-By, and Etags, etc...  See _[A RESTful Scutter Protocol for Redfoot Kernel](http://copia.ogbuji.net/blog/2006-01-29/A_RESTful_)_ for more on this mechanism.  Currently, _["HTTP Vocabulary in RDF"](http://www.w3.org/TR/HTTP-in-RDF/)_ seems like the most promising vocabulary to use in this regard.

### "Lazy" Content Negotiation ###

In addition to storing HTTP response headers, the protocol also requires that an indication of the set of Accept headers that resulted in a successful dereference of an RDF graph serialization be stored in the provenance graph and used to determine whether or not to attempt subsequent content negotiated requests.

### Parameterized graph traversal ###

As mentioned in at the top of this document, a set of predetermined RDF predicates should serve as input to the graph traversal "loop."

### A Graph Naming Convention ###

Upon successful parsing of the Graph IRI, the agent should update / create (depending on the result of the "guided" request) a named graph in the data set with an IRI which corresponds to the racine of the full source IRI.