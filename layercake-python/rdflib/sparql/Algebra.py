#!/usr/local/bin/python
# -*- coding: utf-8 -*-
"""
An implementation of the W3C SPARQL Algebra on top of sparql-p's expansion trees

See: http://www.w3.org/TR/rdf-sparql-query/#sparqlAlgebra

For each symbol in a SPARQL abstract query, we define an operator for evaluation. 
The SPARQL algebra operators of the same name are used to evaluate SPARQL abstract 
query nodes as described in the section "Evaluation Semantics".

We define eval(D(G), graph pattern) as the evaluation of a graph pattern with respect 
to a dataset D having active graph G. The active graph is initially the default graph.
"""
import unittest, os
from StringIO import StringIO
from rdflib.Graph import Graph, ReadOnlyGraphAggregate, ConjunctiveGraph
from rdflib import URIRef, Variable, plugin, BNode, Literal
from rdflib.util import first, MakeImmutableDict
from rdflib.store import Store
from rdflib import sparql
from rdflib.sparql.bison.Query import AskQuery, SelectQuery, DescribeQuery, Query, Prolog
from rdflib.sparql.bison.IRIRef import NamedGraph,RemoteGraph
from rdflib.sparql.bison.SolutionModifier import ASCENDING_ORDER, \
                                                 ParsedOrderConditionExpression, \
                                                 DESCENDING_ORDER, \
                                                 UNSPECIFIED_ORDER
from rdflib.sparql import sparqlGraph, sparqlOperators, SPARQLError, Query, DESCRIBE
from rdflib.sparql.bison.SPARQLEvaluate import unRollTripleItems, _variablesToArray
from rdflib.sparql.bison.Util import ListRedirect
from rdflib.sparql.bison.GraphPattern import *
from rdflib.sparql.graphPattern import BasicGraphPattern
from rdflib.sparql.bison.Triples import ParsedConstrainedTriples
from rdflib.sparql.bison.SPARQLEvaluate import createSPARQLPConstraint,\
     CONSTRUCT_NOT_SUPPORTED,convertTerm
from rdflib import sparql as sparqlModule

#A variable to determine whether we obey SPARQL definition of RDF dataset
#which does not allow matching of default graphs (or any graph with a BNode for a name)
#"An RDF Dataset comprises one graph, 
# the default graph, which does not have a name" - 
#  http://www.w3.org/TR/rdf-sparql-query/#namedAndDefaultGraph
DAWG_DATASET_COMPLIANCE = False

def ReduceGraphPattern(graphPattern,prolog):
    """
    Takes parsed graph pattern and converts it into a BGP operator
    
    .. Replace all basic graph patterns by BGP(list of triple patterns) ..
    """
    if isinstance(graphPattern.triples[0],list) and len(graphPattern.triples) == 1:
        graphPattern.triples = graphPattern.triples[0]
    items = []
    for triple in graphPattern.triples:
        bgp=BasicGraphPattern(list(unRollTripleItems(triple,prolog)),prolog)
        items.append(bgp)
    if len(items) == 1:
        assert isinstance(items[0],BasicGraphPattern), repr(items)
        bgp=items[0]
        return bgp
    elif len(items) > 1:
        constraints=[b.constraints for b in items if b.constraints]
        constraints=reduce(lambda x,y:x+y,constraints,[])
        def mergeBGPs(left,right):
            if isinstance(left,BasicGraphPattern):
                left = left.patterns
            if isinstance(right,BasicGraphPattern):
                right = right.patterns
            return left+right
        bgp=BasicGraphPattern(reduce(mergeBGPs,items),prolog)
        bgp.addConstraints(constraints)
        return bgp
    else:
        #an empty BGP?
        raise

def ReduceToAlgebra(left,right):
    """
    
    Converts a parsed Group Graph Pattern into an expression in the algebra by recursive
    folding / reduction (via functional programming) of the GGP as a list of Basic 
    Triple Patterns or "Graph Pattern Blocks"
    
    12.2.1 Converting Graph Patterns
    
    [20] GroupGraphPattern ::= '{' TriplesBlock? ( ( GraphPatternNotTriples | Filter )
         '.'? TriplesBlock? )* '}'
    [22] GraphPatternNotTriples ::= OptionalGraphPattern | GroupOrUnionGraphPattern | 
         GraphGraphPattern
    [26] Filter ::= 'FILTER' Constraint
    [27] Constraint ::= BrackettedExpression | BuiltInCall | FunctionCall
    [56] BrackettedExpression  ::= '(' ConditionalOrExpression ')'
            
    
    ( GraphPatternNotTriples | Filter ) '.'? TriplesBlock?
      nonTripleGraphPattern     filter         triples
    """
    if not isinstance(right,AlgebraExpression):
        if isinstance(right,ParsedGroupGraphPattern):
            right = reduce(ReduceToAlgebra,right,None)
            print right;raise
        assert isinstance(right,GraphPattern),type(right)
        #Parsed Graph Pattern
        if right.triples:
            if right.nonTripleGraphPattern:
                #left is None, just return right (a GraphPatternNotTriples)
                if isinstance(right.nonTripleGraphPattern,ParsedGraphGraphPattern):
                    right = Join(ReduceGraphPattern(right,sparqlModule.prolog),
                                 GraphExpression(
                                    right.nonTripleGraphPattern.name,
                                    reduce(ReduceToAlgebra,
                                           right.nonTripleGraphPattern.graphPatterns,
                                           None)))
                elif isinstance(right.nonTripleGraphPattern,
                                ParsedOptionalGraphPattern):
                    # Join(LeftJoin( ..left.. ,{..}),..triples..)
                    if left:
                        assert isinstance(left,(Join,BasicGraphPattern)),repr(left)
                        rightTriples = ReduceGraphPattern(right,sparqlModule.prolog)
                        LJright = LeftJoin(left,
                                           reduce(ReduceToAlgebra,
                                                  right.nonTripleGraphPattern.graphPatterns,
                                                  None))
                        return Join(LJright,rightTriples)
                    else:
                        # LeftJoin({},right) => {}
                        #see http://lists.w3.org/Archives/Public/public-rdf-dawg/2007AprJun/0046.html
                        return EmptyGraphPatternExpression()
                                            
                elif isinstance(right.nonTripleGraphPattern,
                                ParsedAlternativeGraphPattern):
                    #Join(Union(..),..triples..)
                    unionList =\
                      [ reduce(ReduceToAlgebra,i.graphPatterns,None) for i in 
                          right.nonTripleGraphPattern.alternativePatterns ]                        
                    right = Join(reduce(Union,unionList),
                                 ReduceGraphPattern(right,sparqlModule.prolog))
                else:
                    raise Exception(right)
            else:
                if isinstance(left,BasicGraphPattern) and left.constraints:
                    if right.filter:
                        if not left.patterns:
                            #{ } FILTER E1 FILTER E2 BGP(..)
                            filter2=createSPARQLPConstraint(right.filter,sparqlModule.prolog)
                            right = ReduceGraphPattern(right,sparqlModule.prolog)
                            right.addConstraints(left.constraints)
                            right.addConstraint(filter2)
                            return right
                        else:
                            #BGP(..) FILTER E1 FILTER E2 BGP(..)
                            left.addConstraint(createSPARQLPConstraint(right.filter,
                                                                   sparqlModule.prolog))
                    right = ReduceGraphPattern(right,sparqlModule.prolog)
                else:
                    if right.filter:
                        #FILTER ...
                        filter=createSPARQLPConstraint(right.filter,sparqlModule.prolog)
                        right = ReduceGraphPattern(right,sparqlModule.prolog)
                        right.addConstraint(filter)
                    else:
                    #BGP(..)
                        right = ReduceGraphPattern(right,sparqlModule.prolog)
                    
        else:
            #right.triples is None
            if right.nonTripleGraphPattern is None:
                if right.filter:
                    if isinstance(left,BasicGraphPattern):
                        #BGP(...) FILTER
                        left.addConstraint(createSPARQLPConstraint(right.filter, 
                                                                   sparqlModule.prolog))
                        return left
                    else:
                        pattern=BasicGraphPattern()
                        pattern.addConstraint(createSPARQLPConstraint(right.filter,
                                                                      sparqlModule.prolog))
                        if left is None:
                            return pattern 
                        else:
                            right=pattern
                else:
                    return left
                #     raise Exception(right)
            elif right.nonTripleGraphPattern:
                if isinstance(right.nonTripleGraphPattern,ParsedGraphGraphPattern):
                    # Join(left,Graph(...))
                    right = GraphExpression(right.nonTripleGraphPattern.name,
                                            reduce(ReduceToAlgebra,
                                                   right.nonTripleGraphPattern.graphPatterns,
                                                   None))
                elif isinstance(right.nonTripleGraphPattern,ParsedOptionalGraphPattern):
                    if left:
                        # LeftJoin(left,right)
                        return LeftJoin(left,
                                        reduce(ReduceToAlgebra,
                                               right.nonTripleGraphPattern.graphPatterns,
                                               None))
                    else:
                        # LeftJoin({},right)
                        #see - http://lists.w3.org/Archives/Public/public-rdf-dawg/2007AprJun/0046.html
                        return EmptyGraphPatternExpression()
                elif isinstance(right.nonTripleGraphPattern,
                                ParsedAlternativeGraphPattern):
                    #right = Union(..)
                    unionList =\
                      map(lambda i: reduce(ReduceToAlgebra,i.graphPatterns,None),
                          right.nonTripleGraphPattern.alternativePatterns)
                    right = reduce(Union,unionList)
                elif isinstance(right.nonTripleGraphPattern,ParsedGroupGraphPattern):
                    right = reduce(ReduceToAlgebra,
                                   right.nonTripleGraphPattern.graphPatterns,
                                   None)                    
                else:
                    raise Exception(right)
    if not left:
        return right
    else:
        return Join(left,right)

def RenderSPARQLAlgebra(parsedSPARQL,nsMappings=None):
    nsMappings = nsMappings and nsMappings or {}
    sparqlModule.prolog = parsedSPARQL.prolog
    if sparqlModule.prolog is not None:
        sparqlModule.prolog.DEBUG = False
    else:
        sparqlModule.prolog = Prolog(None, [])
        sparqlModule.prolog.DEBUG=False
    return reduce(ReduceToAlgebra,
                  parsedSPARQL.query.whereClause.parsedGraphPattern.graphPatterns,None)

def LoadGraph(dtSet,dataSetBase,graph):
    #An RDF URI dereference, following TAG best practices
    #Need a hook (4Suite) to bypass urllib's inability
    #to implement URI RFC verbatim - problematic for descendent 
    #specifications
    try:
        from Ft.Lib.Uri import UriResolverBase as Resolver
        from Ft.Lib.Uri import GetScheme, OsPathToUri
    except:
        def OsPathToUri(path):
            return path
        def GetScheme(uri):
            return None
        class Resolver:
            supportedSchemas=[None]
            def resolve(self, uriRef, baseUri):
                return uriRef 
    if dataSetBase is not None:
        res = Resolver()
        scheme = GetScheme(dtSet) or GetScheme(dataSetBase)
        if scheme not in res.supportedSchemes:
            dataSetBase = OsPathToUri(dataSetBase) 
        source=Resolver().resolve(str(dtSet), dataSetBase)
    else:
        source = dtSet
    #GRDDL hook here!
    try:
        #Try as RDF/XML first (without resolving)
        graph.parse(source)
    except:
        try:
            #Parse as Notation 3 instead
            source=Resolver().resolve(str(dtSet), dataSetBase)
            graph.parse(source,format='n3')
        except:
            raise
            #RDFa?
            graph.parse(dtSet,format='rdfa')

def TopEvaluate(query,dataset,passedBindings = None,DEBUG=False,exportTree=False,
                dataSetBase=None,
                extensionFunctions={}):
    """
    The outcome of executing a SPARQL is defined by a series of steps, starting 
    from the SPARQL query as a string, turning that string into an abstract 
    syntax form, then turning the abstract syntax into a SPARQL abstract query
    comprising operators from the SPARQL algebra. This abstract query is then 
    evaluated on an RDF dataset.
    """
    if not passedBindings:
        passedBindings = {}
    if query.prolog:
        query.prolog.DEBUG = DEBUG
    sparqlModule.prolog = query.prolog
    prolog = sparqlModule.prolog
    prolog.answerList = []
    prolog.eagerLimit = None
    prolog.extensionFunctions.update(extensionFunctions)
    query.prolog.rightMostBGPs = set()

    if query.query.dataSets:
        graphs = []
        for dtSet in query.query.dataSets:
            if isinstance(dtSet,NamedGraph):
                newGraph = Graph(dataset.store,dtSet)
                LoadGraph(dtSet,dataSetBase,newGraph)
                graphs.append(newGraph)
            else:
                #"Each FROM clause contains an IRI that indicates a graph to be 
                # used to form the default graph. This does not put the graph 
                # in as a named graph." -- 8.2.1 Specifying the Default Graph
                if DAWG_DATASET_COMPLIANCE:
                    #@@ this should indicate a merge into the 'default' graph
                    # per http://www.w3.org/TR/rdf-sparql-query/#unnamedGraph
                    # (8.2.1 Specifying the Default Graph)
                    assert isinstance(dataset,ConjunctiveGraph)
                    memGraph = dataset.default_context
                else:
                    memStore = plugin.get('IOMemory',Store)()
                    memGraph = Graph(memStore)
                LoadGraph(dtSet,dataSetBase,memGraph)
                if memGraph.identifier not in [g.identifier for g in graphs]:
                    graphs.append(memGraph)
        tripleStore = sparqlGraph.SPARQLGraph(ReadOnlyGraphAggregate(graphs,
                                                                     store=dataset.store),
                                              dSCompliance=DAWG_DATASET_COMPLIANCE)
    else:        
        tripleStore = sparqlGraph.SPARQLGraph(dataset,
                                              dSCompliance=DAWG_DATASET_COMPLIANCE)    
    if isinstance(query.query,SelectQuery) and query.query.variables:
        query.query.variables = [convertTerm(item,query.prolog) 
                                   for item in query.query.variables]
    else:
        query.query.variables = []
    expr = reduce(ReduceToAlgebra,query.query.whereClause.parsedGraphPattern.graphPatterns,
                  None)

    limit = None
    offset = 0
    if isinstance(query.query,SelectQuery) and query.query.solutionModifier.limitClause is not None:
        limit = int(query.query.solutionModifier.limitClause)
    if isinstance(query.query,SelectQuery) and query.query.solutionModifier.offsetClause is not None:
        offset = int(query.query.solutionModifier.offsetClause)
    else:
        offset = 0

    # @todo consider allowing in cases where offset is nonzero
    if limit is not None and offset == 0:
        query.prolog.eagerLimit = limit
        for x in expr.fetchTerminalExpression():
            query.prolog.rightMostBGPs.add(x)
        if query.prolog.DEBUG:
            print "Setting up for an eager limit evaluation (size: %s)"%query.prolog.eagerLimit
    if DEBUG:
        print "## Full SPARQL Algebra expression ##"
        print expr
        print "###################################"

    if isinstance(expr,BasicGraphPattern):
        retval = None
        bindings = Query._createInitialBindings(expr)
        if passedBindings:
            bindings.update(passedBindings)
        top = Query._SPARQLNode(None,bindings,expr.patterns, tripleStore,expr=expr)
        top.topLevelExpand(expr.constraints, query.prolog)
            
#        for tree in Query._fetchBoundLeaves(top):
#            print_tree(tree)
#        print "---------------"
        result = Query.Query(top, tripleStore)
    else:
        assert isinstance(expr,AlgebraExpression), repr(expr)
        if DEBUG:
            print "## Full SPARQL Algebra expression ##"
            print expr
            print "###################################"
        result = expr.evaluate(tripleStore,passedBindings,query.prolog)
        if isinstance(result,BasicGraphPattern):
            retval = None
            bindings = Query._createInitialBindings(result)
            if passedBindings:
                bindings.update(passedBindings)
            top = Query._SPARQLNode(None,bindings,result.patterns, 
                                    result.tripleStore,expr=result)
            top.topLevelExpand(result.constraints, query.prolog)
            result = Query.Query(top, tripleStore)
        assert isinstance(result,Query.Query),repr(result)
    if exportTree:
        from rdflib.sparql.Visualization import ExportExpansionNode
        if result.top:
            ExportExpansionNode(result.top,fname='out.svg',verbose=True)
        else:
            ExportExpansionNode(result.parent1.top,fname='out1.svg',verbose=True)
            ExportExpansionNode(result.parent2.top,fname='out2.svg',verbose=True)
    if result == None :
        # generate some proper output for the exception :-)
        msg = "Errors in the patterns, no valid query object generated; "
        msg += ("pattern:\n%s\netc..." % basicPatterns[0])
        raise SPARQLError(msg)

    if isinstance(query.query,AskQuery):
        return result.ask()
    elif isinstance(query.query,SelectQuery):
        orderBy = None
        orderAsc = None
        if query.query.solutionModifier.orderClause:
            orderBy     = []
            orderAsc    = []
            for orderCond in query.query.solutionModifier.orderClause:
                # is it a variable?
                if isinstance(orderCond,Variable):
                    orderBy.append(orderCond)
                    orderAsc.append(ASCENDING_ORDER)
                # is it another expression, only variables are supported
                else:
                    if isinstance(orderCond.expression,ListRedirect):
                        expr=orderCond.expression.reduce()
                    else:
                        assert isinstance(orderCond,ParsedOrderConditionExpression) and\
                               isinstance(orderCond.expression,Variable),\
                        "Support for ORDER BY with anything other than a variable is not supported: %s"%orderCond
                        expr=orderCond.expression
                    orderBy.append(expr)                    
                    orderAsc.append(
                        orderCond.order == ASCENDING_ORDER or
                        orderCond.order == UNSPECIFIED_ORDER
                    )

        selectionF = Query._variablesToArray(query.query.variables,"selection")
        vars = result._getAllVariables()
        if orderAsc and not query.query.variables:
            #SELECT * ..., variables are extracted in the order they appear
            _vars = []
            for _n in walktree(result.top):#, depthfirst = True, leavesOnly = True, optProxies=False):
                if isinstance(_n.expr,BasicGraphPattern):
                    for s,p,o,_context in _n.expr.patterns:
                        for term in [s,p,o]:
                            if term not in _vars:
                                _vars.append(term)
            vars = _vars

        selection=result.select(
            query.query.variables if query.query.variables else vars,
            query.query.distinct,
            limit,
            orderBy,
            orderAsc,
            offset
        )

        if result.parent1 != None and result.parent2 != None :
            answers=reduce(lambda x,y:x+y,
                                    [root.returnResult(selectionF) \
                                      for root in fetchUnionBranchesRoots(result)])
            topUnionBindings = query.query.distinct and \
                        Query._uniquefyList([MakeImmutableDict(ans) for ans in answers]) or answers
        else:
            if (limit == 0 or limit is not None or offset is not None and \
                 offset > 0):
                if prolog.answerList:
                    topUnionBindings = query.query.distinct and \
                        Query._uniquefyList([MakeImmutableDict(ans) 
                            for ans in prolog.answerList]) or prolog.answerList
                    vars = prolog.answerList[0].keys()
                else: 
                    topUnionBindings=[]
            else:    
                answers = result.top.returnResult(selectionF)
                topUnionBindings = (query.query.distinct and 
                    Query._uniquefyList([MakeImmutableDict(ans) 
                        for ans in answers]) or answers)
        return   selection,\
                 _variablesToArray(query.query.variables,"selection"),\
                 vars,\
                 orderBy,query.query.distinct,\
                 topUnionBindings
    elif isinstance(query.query,DescribeQuery):
        if query.query.solutionModifier.limitClause is not None:
            limit = int(query.query.solutionModifier.limitClause)
        else:
            limit = None
        if query.query.solutionModifier.offsetClause is not None:
            offset = int(query.query.solutionModifier.offsetClause)
        else:
            offset = 0
        if result.parent1 != None and result.parent2 != None :
            rt=(r for r in reduce(lambda x,y:x+y,
                            [root.returnResult(selectionF) \
                              for root in fetchUnionBranchesRoots(result)]))
        elif limit is not None or offset != 0:
            raise NotImplemented("Solution modifiers cannot be used with DESCRIBE")
        else:
            rt=result.top.returnResult(None)
        rtGraph=Graph()
        for binding in rt:        
            g=extensionFunctions[DESCRIBE](query.query.describeVars,
                                               binding,
                                               tripleStore.graph)
            return g
    else:
#        10.2 CONSTRUCT
#        The CONSTRUCT query form returns a single RDF graph specified by a graph 
#        template. The result is an RDF graph formed by taking each query solution 
#        in the solution sequence, substituting for the variables in the graph 
#        template, and combining the triples into a single RDF graph by set union.
        if query.query.solutionModifier.limitClause is not None:
            limit = int(query.query.solutionModifier.limitClause)
        else:
            limit = None
        if query.query.solutionModifier.offsetClause is not None:
            offset = int(query.query.solutionModifier.offsetClause)
        else:
            offset = 0
        if result.parent1 != None and result.parent2 != None :
            rt=(r for r in reduce(lambda x,y:x+y,
                            [root.returnResult(selectionF) \
                              for root in fetchUnionBranchesRoots(result)]))
        elif limit is not None or offset != 0:
            raise NotImplemented("Solution modifiers cannot be used with CONSTRUCT")
        else:
            rt=result.top.returnResult(None)
        rtGraph=Graph()
        for binding in rt:        
            for s,p,o,func in ReduceGraphPattern(query.query.triples,prolog).patterns:
                s,p,o=map(lambda x:isinstance(x,Variable) and binding.get(x) or
                                 x,[s,p,o])
                #If any such instantiation produces a triple containing an unbound
                #variable or an illegal RDF construct, such as a literal in subject 
                #or predicate position, then that triple is not included in the 
                #output RDF graph.
                if not [i for i in [s,p,o] if isinstance(i,Variable)]:
                    rtGraph.add((s,p,o))
        return rtGraph

class AlgebraExpression(object):
    """
    For each symbol in a SPARQL abstract query, we define an operator for 
    evaluation. The SPARQL algebra operators of the same name are used 
    to evaluate SPARQL abstract query nodes as described in the section 
    "Evaluation Semantics".
    """
    def __repr__(self):
        return "%s(%s,%s)"%(self.__class__.__name__,self.left,self.right)

    def evaluate(self,tripleStore,initialBindings,prolog):
        """
        12.5 Evaluation Semantics
        
        We define eval(D(G), graph pattern) as the evaluation of a graph pattern
        with respect to a dataset D having active graph G. The active graph is 
        initially the default graph.
        """        
        raise Exception(repr(self))

class EmptyGraphPatternExpression(AlgebraExpression):
    """
    A placeholder for evaluating empty graph patterns - which
    should result in an empty multiset of solution bindings
    """
    def __repr__(self):
        return "EmptyGraphPatternExpression(..)"
    def evaluate(self,tripleStore,initialBindings,prolog):
        #raise NotImplementedError("Empty Graph Pattern expressions, not supported")
        if prolog.DEBUG:
            print "eval(%s,%s,%s)"%(self,initialBindings,tripleStore.graph)
        empty = Query._SPARQLNode(None,{},[],tripleStore)
        empty.bound = False
        return Query.Query(empty, tripleStore)

def fetchUnionBranchesRoots(node):
    for parent in [node.parent1,node.parent2]:
        if parent.parent1:            
            for branch_root in fetchUnionBranchesRoots(parent):
                yield branch_root
        else:
            yield parent.top

def fetchChildren(node):
    if isinstance(node,Query._SPARQLNode):
        yield [c for c in node.children]
    elif isinstance(node,Query.Query):
        if node.parent1 is None:
            for c in fetchChildren(node.top):
                yield c
        else:
            for parent in [node.parent1,node.parent2]:
                for c in fetchChildren(parent):
                    yield c                 

def walktree(top, depthfirst = True, leavesOnly = True, optProxies=False):
    #assert top.parent1 is None
    if isinstance(top,Query._SPARQLNode) and top.clash:
        return
    if not depthfirst and (not leavesOnly or not top.children):
        proxies=False
        for optChild in reduce(lambda x,y: x+y,[list(Query._fetchBoundLeaves(o))
                                        for o in top.optionalTrees],[]):
            proxies=True        
            yield optChild
        if not proxies:
            yield top
    children=reduce(lambda x,y:x+y,list(fetchChildren(top)))
#    if isinstance(top,Query._SPARQLNode) or isinstance(top,Query.Query) and \
#        top.parent1 is None:
#        children = top.children
#    else:
#        children = top.parent1.children + top.parent2.children 
    for child in children:
        if child.children:
            for newtop in walktree(child, depthfirst,leavesOnly,optProxies):
                yield newtop
        else:
            proxies=False
            for optChild in reduce(lambda x,y: x+y,[list(Query._fetchBoundLeaves(o))
                                            for o in child.optionalTrees],[]):
                proxies=True        
                yield optChild
            if not proxies:
                yield child

    if depthfirst and (not leavesOnly or not children):
        proxies=False
        for optChild in reduce(lambda x,y: x+y,[list(Query._fetchBoundLeaves(o))
                                        for o in top.optionalTrees],[]):
            proxies=True        
            yield optChild
        if not proxies:
            yield top

def print_tree(node, padding=' '):
    print padding[:-1] + repr(node)
    padding = padding + ' '
    count = 0
    #_children1=reduce(lambda x,y:x+y,list(fetchChildren(node)))
    for child in node.children:#_children1:
        count += 1
        print padding + '|'
        if child.children:
            if count == len(node.children):
                print_tree(child, padding + ' ')
            else:
                print_tree(child, padding + '|')
        else:
            print padding + '+-' + repr(child) + ' ' + repr(dict([(k,v) 
                    for k,v in child.bindings.items() if v]))
            optCount=0
            for optTree in child.optionalTrees:
                optCount += 1
                print padding + '||'
                if optTree.children:
                    if optCount == len(child.optionalTrees):
                        print_tree(optTree, padding + ' ')
                    else:
                        print_tree(optTree, padding + '||')
                else:
                    print padding + '+=' + repr(optTree)
                
    count = 0    
    for optTree in node.optionalTrees:
        count += 1
        print padding + '||'
        if optTree.children:
            if count == len(node.optionalTrees):
                print_tree(optTree, padding + ' ')
            else:
                print_tree(optTree, padding + '||')
        else:
            print padding + '+=' + repr(optTree)
            
            
#List flattener
#Credit: http://code.activestate.com/recipes/576719/            
def deepFlatten(lista):
    try:
        for item in lista:
            for one in deepFlatten(item):
                yield one
    except:
        yield lista                        

def _ExpandJoin(node,expression,tripleStore,prolog,optionalTree=False):
    """
    Traverses to the leaves of expansion trees to implement the Join
    operator
    """
    if prolog.DEBUG:
        print_tree(node)
        print "-------------------"
    #for node in BF_leaf_traversal(node):
    currExpr = expression
    for node in walktree(node):
        if node.clash:
            continue
        assert len(node.children) == 0 
        if prolog.DEBUG:
            print "Performing Join(%s,..)"%node
        if isinstance(currExpr,AlgebraExpression):
            #If an algebra expression evaluate it passing on the leaf bindings
            if prolog.DEBUG:
                print "passing on bindings to %s\n:%s"%(currExpr,node.bindings.copy())
            expression = currExpr.evaluate(tripleStore,node.bindings.copy(),prolog)
        else:
            expression = currExpr
        if isinstance(expression,BasicGraphPattern):
            tS = tripleStore
            if hasattr(expression,'tripleStore'):
                if prolog.DEBUG:                    
                    print "has tripleStore: ",expression.tripleStore
                tS = expression.tripleStore
            if prolog.DEBUG:
                print "Evaluated left node and traversed to leaf, expanding with ", 
                expression
                print node.tripleStore.graph
                print "expressions bindings: ", 
                Query._createInitialBindings(expression)
                print "node bindings: ", node.bindings
            exprBindings = Query._createInitialBindings(expression)
            exprBindings.update(node.bindings)
            #An indicator for whether this node has any descendant optional expansions
            #we should consider instead
            #in Join(LeftJoin(A,B),X), if the inner LeftJoin is successful, 
            #then X is joined
            #against the cumulative bindings ( instead of just A )
            
            descendantOptionals = list(deepFlatten([Query._fetchBoundLeaves(o,previousBind=True)
                                                        for o in node.optionalTrees]))
            child = None            
            if not node.clash and (not descendantOptionals or 
                                   not [n for n in descendantOptionals
                                          if n.priorLeftJoin and n.clash]):
                #It has compatible bindings and either no optional expansions
                #, no *valid* optional expansions, or not valid optional
                #expansions that were later marked as clashed
                child = Query._SPARQLNode(node,
                                          exprBindings,
                                          expression.patterns,
                                          tS,
                                          expr=node.expr)
                child.topLevelExpand(expression.constraints, prolog)
                if prolog.DEBUG:
                    print "Has compatible bindings and no valid optional expansions"
                    print "Newly bound descendants: "
                    for c in Query._fetchBoundLeaves(child):
                        print "\t",c, c.bound                        
                        print c.bindings
        else:
            assert isinstance(expression,Query.Query)
            if not expression.top:
                #already evaluated a UNION - fetch UNION branches
                child = list(fetchUnionBranchesRoots(expression))
            else:
                #Already been evaluated (non UNION), just attach the SPARQLNode
                child = expression.top
        if isinstance(child,Query._SPARQLNode):
            if node.clash == False and child is not None:
                node.children.append(child)
                if prolog.DEBUG:
                    print "Adding %s to %s (a UNION branch)"%(child,node)
        elif child:
            for newChild in child:
                node.children.append(newChild)
                if prolog.DEBUG:
                    print "Adding %s to %s"%(child,node)                    
        if prolog.DEBUG:
            print_tree(node)
            print "-------------------" 
        for optTree in node.optionalTrees:
            #Join the optional paths as well - those that are bound and valid
            for validLeaf in Query._fetchBoundLeaves(optTree):
                _ExpandJoin(validLeaf,
                            expression,
                            tripleStore,
                            prolog,
                            optionalTree=True)

class NonSymmetricBinaryOperator(AlgebraExpression):
    def fetchTerminalExpression(self):
        if isinstance(self.right,BasicGraphPattern):
            yield self.right
        else:
            for i in self.right.fetchTerminalExpression():
                yield i

class Join(NonSymmetricBinaryOperator):
    """
    [[(P1 AND P2)]](D,G) = [[P1]](D,G) compat [[P2]](D,G)
    
    Join(Ω1, Ω2) = { merge(μ1, μ2) | μ1 in Ω1 and μ2 in Ω2, and μ1 and μ2 are \
                     compatible }
    
    Pseudocode implementation:
    
    Evaluate BGP1
    Traverse to leaves (expand and expandOption leaves) of BGP1, set 'rest' to 
    triple patterns in BGP2 (filling out bindings).
    Trigger another round of expand / expandOptions (from the leaves)    
    """
    def __init__(self,BGP1,BGP2):
        self.left  = BGP1
        self.right = BGP2
            
    def evaluate(self,tripleStore,initialBindings,prolog):
        if prolog.DEBUG:
            print "eval(%s,%s,%s)"%(self,initialBindings,tripleStore.graph)
        if isinstance(self.left,AlgebraExpression):
            left = self.left.evaluate(tripleStore,initialBindings,prolog)
        else:
            left = self.left
        if isinstance(left,BasicGraphPattern):        
            retval = None
            bindings = Query._createInitialBindings(left)
            if initialBindings:
                bindings.update(initialBindings)
            if hasattr(left,'tripleStore'):
                #Use the prepared tripleStore
                lTS = left.tripleStore
            else:
                lTS = tripleStore
            top = Query._SPARQLNode(None,
                                    bindings,
                                    left.patterns,
                                    lTS,
                                    expr=left)
            top.topLevelExpand(left.constraints, prolog)
            _ExpandJoin(top,self.right,tripleStore,prolog)
            return Query.Query(top, tripleStore)
        else:
            assert isinstance(left,Query.Query), repr(left)
            if left.parent1 and left.parent2:
                #union branch.  We need to unroll all operands (recursively)
                for union_root in fetchUnionBranchesRoots(left):
                    _ExpandJoin(union_root,self.right,tripleStore,prolog)
            else:
                for b in Query._fetchBoundLeaves(left.top):
                    _ExpandJoin(b,self.right,tripleStore,prolog)
            return left

def _ExpandLeftJoin(node,expression,tripleStore,prolog,optionalTree=False):
    """
    Traverses to the leaves of expansion trees to implement the LeftJoin
    operator
    """
    currExpr = expression
    if prolog.DEBUG:
        print "DFS and LeftJoin expansion of "
        print_tree(node)
        print "---------------------"
        print node.bindings
    for node in walktree(node,optProxies=True):
        if node.clash:
            continue
        assert len(node.children) == 0 
        # this is a leaf in the original expansion
        if prolog.DEBUG:
            print "Performing LeftJoin(%s,..)"%node
        if isinstance(currExpr,AlgebraExpression):
            #If a Graph pattern evaluate it passing on the leaf bindings
            #(possibly as solutions to graph names
            if prolog.DEBUG:
                print "evaluating B in LeftJoin(A,B)"
                print "passing on bindings to %s\n:%s"%(currExpr,
                                                        node.bindings.copy())
            expression = currExpr.evaluate(tripleStore,node.bindings.copy(),
                                           prolog)
        else:
            expression = currExpr
        if isinstance(expression,BasicGraphPattern):
            rightBindings = Query._createInitialBindings(expression)
            rightBindings.update(node.bindings)
            optTree = Query._SPARQLNode(None,
                                        rightBindings,
                                        expression.patterns,
                                        tripleStore,
                                        expr=expression)
            if prolog.DEBUG:
                print "evaluating B in LeftJoin(A,B) - a BGP: ", expression
                print "Passing on bindings ",rightBindings
            optTree.topLevelExpand(expression.constraints, prolog)
            for proxy in Query._fetchBoundLeaves(optTree):
                #Mark a successful evaluation of LeftJoin (new bindings were added)
                #these become proxies for later expressions 
                proxy.priorLeftJoin=True
        else:
            if prolog.DEBUG:
                print "Attaching previously evaluated node: ", expression.top
            assert isinstance(expression,Query.Query)
            if not expression.top:
                #already evaluated a UNION - fetch UNION branches
                optTree = list(fetchUnionBranchesRoots(expression))
            else:
                #Already been evaluated (non UNION), just attach the SPARQLNode
                optTree = expression.top
        if prolog.DEBUG:
            print "Optional tree: ", optTree
        if isinstance(optTree,Query._SPARQLNode):
            if optTree.clash == False and optTree is not None:
                node.optionalTrees.append(optTree)
                if prolog.DEBUG:
                    print "Adding %s to %s (a UNION branch)"%(optTree,
                                                              node.optionalTrees)
        else:
            assert isinstance(optTree,list)
            for newChild in optTree:
#                if not newChild.clash:
                node.optionalTrees.append(newChild)
                if prolog.DEBUG:
                    print "Adding %s to %s"%(newChild,node.optionalTrees)                    
        if prolog.DEBUG:
            print "DFS after LeftJoin expansion "
            print_tree(node)
            print "---------------------"
       
        
class LeftJoin(NonSymmetricBinaryOperator):
    """
    Let Ω1 and Ω2 be multisets of solution mappings and F a filter. We define:
    LeftJoin(Ω1, Ω2, expr) = 
        Filter(expr, Join(Ω1, Ω2)) set-union Diff(Ω1, Ω2, expr)
    
    LeftJoin(Ω1, Ω2, expr) = 
    { merge(μ1, μ2) | μ1 in Ω1 and μ2 in Ω2, and 
                      μ1 and μ2 are compatible, and 
                      expr(merge(μ1, μ2)) is true }
    set-union
    { μ1 | μ1 in Ω1 and μ2 in Ω2, and 
           μ1 and μ2 are not compatible }
    set-union
    { μ1 | μ1 in Ω1and μ2 in Ω2, and μ1 and μ2 are compatible and 
           expr(merge(μ1, μ2)) is false }
    
    """
    def __init__(self,BGP1,BGP2,expr=None):
        self.left  = BGP1
        self.right = BGP2

    def evaluate(self,tripleStore,initialBindings,prolog):
        if prolog.DEBUG:
            print "eval(%s,%s,%s)"%(self,initialBindings,tripleStore.graph)
        if isinstance(self.left,AlgebraExpression):
            #print "evaluating A in LeftJoin(A,B) - an expression"
            left = self.left.evaluate(tripleStore,initialBindings,prolog)
        else:
            left = self.left
        if isinstance(left,BasicGraphPattern):        
            #print "expanding A in LeftJoin(A,B) - a BGP: ", left
            retval = None
            bindings = Query._createInitialBindings(left)
            if initialBindings:
                bindings.update(initialBindings)
            if hasattr(left,'tripleStore'):
                #Use the prepared tripleStore
                tripleStore = left.tripleStore
            top = Query._SPARQLNode(None,
                                    bindings,
                                    left.patterns,
                                    tripleStore,
                                    expr=left)
            top.topLevelExpand(left.constraints, prolog)
            for b in Query._fetchBoundLeaves(top):
                _ExpandLeftJoin(b,self.right,tripleStore,prolog)            
            #_ExpandLeftJoin(top,self.right,tripleStore,prolog)
            return Query.Query(top, tripleStore)
        else:
            assert isinstance(left,Query.Query), repr(left)
            if left.parent1 and left.parent2:
                for union_root in fetchUnionBranchesRoots(left):
                    _ExpandLeftJoin(union_root,self.right,tripleStore,prolog)
            else:
                for b in Query._fetchBoundLeaves(left.top):
                    _ExpandLeftJoin(b,self.right,tripleStore,prolog)                        
            #_ExpandLeftJoin(left.top,self.right,tripleStore,prolog)
            return left

class Union(AlgebraExpression):
    """
    II. [[(P1 UNION P2)]](D,G) = [[P1]](D,G) OR [[P2]](D,G)
    
    Union(Ω1, Ω2) = { μ | μ in Ω1 or μ in Ω2 }
    
    """
    def __init__(self,BGP1,BGP2):
        self.left  = BGP1
        self.right = BGP2

    def fetchTerminalExpression(self):
        for item in [self.left,self.right]:
            if isinstance(item,BasicGraphPattern):
                yield item
            else:
                for i in item.fetchTerminalExpression():
                    yield i

    def evaluate(self,tripleStore,initialBindings,prolog):
        if prolog.DEBUG:
            print "eval(%s,%s,%s)"%(self,initialBindings,tripleStore.graph)
        if isinstance(self.left,AlgebraExpression):
            left = self.left.evaluate(tripleStore,initialBindings,prolog)
        else:
            left = self.left
        if isinstance(left,BasicGraphPattern):        
            #The left expression has not been evaluated
            retval = None
            bindings = Query._createInitialBindings(left)
            if initialBindings:
                bindings.update(initialBindings)
            top = Query._SPARQLNode(None,
                                    bindings,
                                    left.patterns, 
                                    tripleStore,
                                    expr=left)
            top.topLevelExpand(left.constraints, prolog)
            top = Query.Query(top, tripleStore)
        else:
            #The left expression has already been evaluated 
            assert isinstance(left,Query.Query), repr(left)
            top = left
        #Now we evaluate the right expression (independently)
        if isinstance(self.right,AlgebraExpression):
            #If it is a GraphExpression, 'reduce' it
            right = self.right.evaluate(tripleStore,initialBindings,prolog)
        else:
            right = self.right
        tS = tripleStore
        if isinstance(right,BasicGraphPattern):
            if hasattr(right,'tripleStore'):            
                tS = right.tripleStore
            rightBindings = Query._createInitialBindings(right)
            if initialBindings:
                rightBindings.update(initialBindings)            
            rightNode = Query._SPARQLNode(None,
                                          rightBindings,
                                          right.patterns,
                                          tS,
                                          expr=right)
            rightNode.topLevelExpand(right.constraints, prolog)
        else:
            assert isinstance(right,Query.Query), repr(right)
            rightNode = right.top
#        if prolog.DEBUG:
#            print "### Two UNION trees ###"
#            print self.left
#            print_tree(top.top)
#            print self.right                       
#            print_tree(rightNode)
#            print "#######################"
            
        #The UNION semantics are implemented by the overidden __add__ method                
        return top + Query.Query(rightNode, tS)

class GraphExpression(AlgebraExpression):
    """
    [24] GraphGraphPattern ::=  'GRAPH'  VarOrIRIref  GroupGraphPattern
    eval(D(G), Graph(IRI,P)) = eval(D(D[i]), P)
    eval(D(G), Graph(var,P)) =
        multiset-union over IRI i in D : Join( eval(D(D[i]), P) , Omega(?v->i) )    
    """
    def __init__(self,iriOrVar,GGP):
        self.iriOrVar  = iriOrVar
        self.GGP = GGP

    def __repr__(self):
        return "Graph(%s,%s)"%(self.iriOrVar,self.GGP)

    def fetchTerminalExpression(self):
        if isinstance(self.GGP,BasicGraphPattern):
            yield self.GGP
        else:
            for i in self.GGP.fetchTerminalExpression():
                yield i

    def evaluate(self,tripleStore,initialBindings,prolog):
        """
        .. The GRAPH keyword is used to make the active graph one of all of the 
           named graphs in the dataset for part of the query ...
        """
        if prolog.DEBUG:
            print "eval(%s,%s,%s)"%(self,initialBindings,tripleStore.graph)
        if isinstance(self.iriOrVar,Variable):
            #A variable: 
            if self.iriOrVar in initialBindings:
                #assert initialBindings[self.iriOrVar], "Empty binding for GRAPH variable!"
                if prolog.DEBUG:
                    print "Passing on unified graph name: ", 
                    initialBindings[self.iriOrVar]
                tripleStore = sparqlGraph.SPARQLGraph(
                                            Graph(tripleStore.store,
                                                  initialBindings[self.iriOrVar])
                                            ,dSCompliance=DAWG_DATASET_COMPLIANCE)
            else: 
                if prolog.DEBUG:
                    print "Setting up BGP to return additional bindings for %s"%self.iriOrVar
                tripleStore = sparqlGraph.SPARQLGraph(tripleStore.graph,
                                                      graphVariable = self.iriOrVar,
                                                      dSCompliance=DAWG_DATASET_COMPLIANCE)
        else:
            graphName =  self.iriOrVar
            graphName  = convertTerm(graphName,prolog)
            if isinstance(tripleStore.graph,ReadOnlyGraphAggregate):
                targetGraph = [g for g in tripleStore.graph.graphs 
                                 if g.identifier == graphName]
                #assert len(targetGraph) == 1
                targetGraph = targetGraph[0]
            else:
                targetGraph = Graph(tripleStore.graph.store,graphName)
            tripleStore = sparqlGraph.SPARQLGraph(targetGraph,
                                                  dSCompliance=\
                                                  DAWG_DATASET_COMPLIANCE)
        if isinstance(self.GGP,AlgebraExpression):
            #Dont evaluate
            return self.GGP.evaluate(tripleStore,initialBindings,prolog)
        else:
            assert isinstance(self.GGP,BasicGraphPattern),repr(self.GGP)
            #Attach the prepared triple store to the BGP
            self.GGP.tripleStore = tripleStore
            return self.GGP

#########################################

#         Tests                         # 

#########################################

    
TEST1="BASE <http://example.com/> SELECT * WHERE { ?s :p1 ?v1 ; :p2 ?v2 }"
#BGP( ?s :p1 ?v1 .?s :p2 ?v2 )
TEST1_REPR=\
"BGP((?s,http://example.com/p1,?v1),(?s,http://example.com/p2,?v2))"

TEST2 = "BASE <http://example.com/> SELECT * WHERE { { ?s :p1 ?v1 } UNION {?s :p2 ?v2 } }"
#Union( BGP(?s :p1 ?v1) , BGP(?s :p2 ?v2) )
TEST2_REPR=\
"Union(BGP((?s,http://example.com/p1,?v1)),BGP((?s,http://example.com/p2,?v2)))"

TEST3 = "BASE <http://example.com/> SELECT * WHERE { ?s :p1 ?v1 OPTIONAL {?s :p2 ?v2 } }"
#LeftJoin(BGP(?s :p1 ?v1), BGP(?s :p2 ?v2), true)
TEST3_REPR=\
"LeftJoin(BGP((?s,http://example.com/p1,?v1)),BGP((?s,http://example.com/p2,?v2)))"

TEST4 = "BASE <http://example.com/> SELECT * WHERE { ?s :p ?o. { ?s :p1 ?v1 } UNION {?s :p2 ?v2 } }"
#Join(BGP(?s :p ?v),Union(BGP(?s :p1 ?v1), BGP(?s :p2 ?v2)))
TEST4_REPR=\
"Join(BGP((?s,http://example.com/p,?o)),Union(BGP((?s,http://example.com/p1,?v1)),BGP((?s,http://example.com/p2,?v2))))"

TEST5 = "BASE <http://example.com/> SELECT * WHERE { ?a ?b ?c OPTIONAL { ?s :p1 ?v1 } }"
#Join(BGP(?s :p ?v),Union(BGP(?s :p1 ?v1), BGP(?s :p2 ?v2)))
TEST5_REPR=\
"LeftJoin(BGP((?a,?b,?c)),BGP((?s,http://example.com/p1,?v1)))"

TEST6="BASE <http://example.com/> SELECT * WHERE { ?a :b :c OPTIONAL {:x :y :z} { :x1 :y1 :z1 } UNION { :x2 :y2 :z2 } }"
TEST6_REPR=\
"Join(LeftJoin(BGP((?a,http://example.com/b,http://example.com/c)),BGP((http://example.com/x,http://example.com/y,http://example.com/z))),Union(BGP((http://example.com/x1,http://example.com/y1,http://example.com/z1)),BGP((http://example.com/x2,http://example.com/y2,http://example.com/z2))))"

TEST7="BASE <http://example.com/> SELECT * WHERE { ?s :p1 ?v1 OPTIONAL { ?s :p2 ?v2. FILTER( ?v1 < 3 ) } }"
TEST7_REPR=\
"LeftJoin(BGP((?s,http://example.com/p1,?v1)),Filter(.. a filter ..,BGP(?s,http://example.com/p2,?v2)))"

TEST8="BASE <http://example.com/> SELECT * WHERE { ?s :p1 ?v1. FILTER ( ?v1 < 3 ) OPTIONAL { ?s :p3 ?v3 } }"
TEST8_REPR=\
"LeftJoin(Filter(.. a filter ..,BGP(?s,http://example.com/p1,?v1)),BGP((?s,http://example.com/p3,?v3)))"

TEST10=\
"""
PREFIX  data:  <http://example.org/foaf/>
PREFIX  foaf:  <http://xmlns.com/foaf/0.1/>
PREFIX  rdfs:  <http://www.w3.org/2000/01/rdf-schema#>

SELECT ?mbox ?nick ?ppd
FROM NAMED <http://example.org/foaf/aliceFoaf>
FROM NAMED <http://example.org/foaf/bobFoaf>
WHERE
{
  GRAPH data:aliceFoaf
  {
    ?alice foaf:mbox <mailto:alice@work.example> ;
           foaf:knows ?whom .
    ?whom  foaf:mbox ?mbox ;
           rdfs:seeAlso ?ppd .
    ?ppd  a foaf:PersonalProfileDocument .
  } .
  GRAPH ?ppd
  {
      ?w foaf:mbox ?mbox ;
         foaf:nick ?nick
  }
}"""

reducableSPARQL=\
"""
PREFIX mf: <http://www.w3.org/2001/sw/DataAccess/tests/test-manifest#>
PREFIX qt: <http://www.w3.org/2001/sw/DataAccess/tests/test-query#>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
SELECT ?test ?testName ?testComment ?query ?result ?testAction
WHERE {
    { ?test a mf:QueryEvaluationTest }
      UNION
    { ?test a <http://jena.hpl.hp.com/2005/05/test-manifest-extra#TestQuery> }
    ?test mf:name   ?testName.
    OPTIONAL { ?test rdfs:comment ?testComment }
    ?test mf:action    ?testAction;
          mf:result ?result.
    ?testAction qt:query ?query }"""
    
reducableSPARQLExpr=\
"Join(LeftJoin(Join(Union(BGP((?test,http://www.w3.org/1999/02/22-rdf-syntax-ns#type,mf:QueryEvaluationTest)),BGP((?test,http://www.w3.org/1999/02/22-rdf-syntax-ns#type,http://jena.hpl.hp.com/2005/05/test-manifest-extra#TestQuery))),BGP((?test,mf:name,?testName))),BGP((?test,rdfs:comment,?testComment))),BGP((?test,mf:action,?testAction),(?test,mf:result,?result),(?testAction,qt:query,?query)))"    

ExprTests = \
[
    (TEST1,TEST1_REPR),
    (TEST2,TEST2_REPR),
    (TEST3,TEST3_REPR),
    (TEST4,TEST4_REPR),
    (TEST5,TEST5_REPR),
    (TEST6,TEST6_REPR),
    (TEST7,TEST7_REPR),
    (TEST8,TEST8_REPR),
    (reducableSPARQL,reducableSPARQLExpr),    
]

test_graph_a = """
@prefix  foaf:     <http://xmlns.com/foaf/0.1/> .
@prefix  rdf:      <http://www.w3.org/1999/02/22-rdf-syntax-ns#> .
@prefix  rdfs:     <http://www.w3.org/2000/01/rdf-schema#> .

_:a  foaf:name     "Alice" .
_:a  foaf:mbox     <mailto:alice@work.example> .
_:a  foaf:knows    _:b .

_:b  foaf:name     "Bob" .
_:b  foaf:mbox     <mailto:bob@work.example> .
_:b  foaf:nick     "Bobby" .
_:b  rdfs:seeAlso  <http://example.org/foaf/bobFoaf> .

<http://example.org/foaf/bobFoaf>
     rdf:type      foaf:PersonalProfileDocument ."""
     
test_graph_b = """
@prefix  foaf:     <http://xmlns.com/foaf/0.1/> .
@prefix  rdf:      <http://www.w3.org/1999/02/22-rdf-syntax-ns#> .
@prefix  rdfs:     <http://www.w3.org/2000/01/rdf-schema#> .

_:z  foaf:mbox     <mailto:bob@work.example> .
_:z  rdfs:seeAlso  <http://example.org/foaf/bobFoaf> .
_:z  foaf:nick     "Robert" .

<http://example.org/foaf/bobFoaf>
     rdf:type      foaf:PersonalProfileDocument ."""     
     
scopingQuery=\
"""
PREFIX  data:  <http://example.org/foaf/>
PREFIX  foaf:  <http://xmlns.com/foaf/0.1/>
PREFIX  rdfs:  <http://www.w3.org/2000/01/rdf-schema#>

SELECT ?ppd
FROM NAMED <http://example.org/foaf/aliceFoaf>
FROM NAMED <http://example.org/foaf/bobFoaf>
WHERE
{
  GRAPH ?ppd { ?b foaf:name "Bob" . } .
  GRAPH ?ppd { ?doc a foaf:PersonalProfileDocument . }
}"""     

if __name__ == '__main__':
    unittest.main()
