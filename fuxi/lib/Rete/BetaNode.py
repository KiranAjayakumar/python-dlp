"""
Implements the behavior associated with the 'join' (Beta) node in a RETE network:
    - Stores tokens in two memories
    - Tokens in memories are checked for consistent bindings (unification) for variables in common *across* both
    - Network 'trigger' is propagated downward
    
This reference implementation follows,  quite closely, the algorithms presented in the PhD thesis (1995) of Robert Doorenbos:
    Production Matching for Large Learning Systems (RETE/UL)
    
A N3 Triple is a working memory element (WME)

The Memories are implemented with consistent binding hashes. Unlinking is not implemented but null 
activations are mitigated (somewhat) by the hash / Set mechanism.
              
"""
import unittest, os, time, sys
from itertools import izip, ifilter
from pprint import pprint
from AlphaNode import AlphaNode, BuiltInAlphaNode, ReteToken
from Node import Node
from RuleStore import N3Builtin
from IteratorAlgebra import hash_join
from Util import xcombine
from rdflib import Variable, BNode,RDF,RDFS,Literal
from rdflib.Collection import Collection
from sets import Set
from itertools import izip
from ReteVocabulary import RETE_NS
from rdflib.Graph import QuotedGraph, Graph
from rdflib.Literal import _XSD_NS
from rdflib import BNode, RDF, Namespace, URIRef, Literal, Variable
OWL_NS    = Namespace("http://www.w3.org/2002/07/owl#")
Any = None

LEFT_MEMORY  = 1
RIGHT_MEMORY = 2

#Implementn left unlinking?
LEFT_UNLINKING = False

memoryPosition = {
    LEFT_MEMORY : "left",
    RIGHT_MEMORY: "right",
}

def collectVariables(node):
    """
    Utility function for locating variables common to the patterns in both left and right nodes
    """
    if isinstance(node,BuiltInAlphaNode):
        return Set()
    if isinstance(node,AlphaNode):
        return Set([term for term in node.triplePattern if isinstance(term,(Variable,BNode))])
    elif node:
        combinedVars = Set()
        combinedVars |= node.leftVariables
        combinedVars |= node.rightVariables
        return combinedVars
    else:
        return Set()
        
#From itertools recipes
def iteritems(mapping): 
    return izip(mapping.iterkeys(),mapping.itervalues())
    
def any(seq,pred=None):
    """Returns True if pred(x) is true for at least one element in the iterable"""
    for elem in ifilter(pred,seq):
        return True
    return False

class ReteMemory(Set):
    """
    A hashed rete network memory
    
    The hash setup goes like so:
    
    key = (commonVarValues1,commonVarValues2, .. commonVarValuesN)
    
    where commonVarValuesN are the values associated with the variables common to both the left
    and right side the descendant beta (join) node.  The unique values (variable substitutions)
    are mapped to a set of the corresponding tokens.  These substitutions are 'joined' on in order
    to create partial instanciations of tokens from both sides.   
    
    Memory mapping:
    {
      key => [ .. tripleOrToken ..]
    }   
    
    "The hash function is a function of both the appropriate variable binding from the token or WME
    .. and the node itself."     

    ".. One way to deal with this problem would be to have beta memory nodes check for duplicate
    tokens. Every time a beta memory was activated, it would check whether the \new" match
    was actually a duplicate of some token already in the memory; if so, it would be ignored (i.e.,
    discarded)."
    
    Memories are Set mixins..    

    procedure beta-memory-left-activation (node: beta-memory, t: token, w: WME)
        new-token   allocate-memory()
        new-token.parent <- t
        new-token.wme  <- w
        insert new-token at the head of node.items
        for each child in node.children do left-activation (child, new-token)
    end        

    procedure alpha-memory-activation (node: alpha-memory, w: WME)
        insert w at the head of node.items
        for each child in node.successors do right-activation (child, w)
    end    
     
    """
    def __init__(self,betaNode,position,filter=None):
        super(ReteMemory, self).__init__()
        self.filter                = filter
        self.successor             = betaNode
        self.position              = position
        self.substitutionDict      = {} #hashed 
        
    def union(self, other):
        """Return the union of two sets as a new set.

        (I.e. all elements that are in either set.)
        """
        result = ReteMemory(self.successor,self.position)
        result._update(other)
        return result    
            
    def __repr__(self):
        return "<%sMemory: %s item(s)>"%(self.position == LEFT_MEMORY and 'Beta' or 'Alpha', len(self))

    def addToken(self,token,debug=False):
        """       

        >>> aNode1 = AlphaNode((Variable('P'),RDF.type,OWL_NS.InverseFunctionalProperty))
        >>> aNode2 = AlphaNode((Variable('X'),Variable('P'),Variable('Z')))
        >>> aNode3 = AlphaNode((Variable('Y'),Variable('P'),Variable('Z')))
        >>> token1 = ReteToken((URIRef('urn:uuid:bart'),URIRef('urn:uuid:name'),Literal("Bart Simpson")))
        >>> token1 = token1.bindVariables(aNode2)
        >>> token2 = token1.unboundCopy()
        >>> token2 = token2.bindVariables(aNode3)
        >>> token3 = ReteToken((URIRef('urn:uuid:b'),URIRef('urn:uuid:name'),Literal("Bart Simpson")))
        >>> token3 = token3.bindVariables(aNode2)
        >>> token4 = token3.unboundCopy()
        >>> token4 = token4.bindVariables(aNode3)
        >>> token5 = ReteToken((URIRef('urn:uuid:name'),RDF.type,OWL_NS.InverseFunctionalProperty))
        >>> token5 = token5.bindVariables(aNode1)
        >>> joinNode1 = BetaNode(aNode1,aNode2)
        >>> joinNode2 = BetaNode(joinNode1,aNode3)
        >>> joinNode1.connectIncomingNodes(aNode1,aNode2)        
        >>> cVars = { Variable('P') : URIRef('urn:uuid:name'), Variable('Z') : Literal("Bart Simpson") }
        >>> inst = PartialInstanciation([token1,token2,token3,token4,token5],consistentBindings=cVars)
        >>> inst
        <PartialInstanciation (joined on ?P,?Z): Set([<ReteToken: Y->urn:uuid:b,P->urn:uuid:name,Z->Bart Simpson>, <ReteToken: P->urn:uuid:name>, <ReteToken: X->urn:uuid:b,P->urn:uuid:name,Z->Bart Simpson>, <ReteToken: Y->urn:uuid:bart,P->urn:uuid:name,Z->Bart Simpson>, <ReteToken: X->urn:uuid:bart,P->urn:uuid:name,Z->Bart Simpson>])>
        >>> b = ReteMemory(joinNode2,LEFT_MEMORY)
        >>> b.addToken(inst)
        >>> b
        <BetaMemory: 1 item(s)>
        >>> joinNode2
        <BetaNode : CommonVariables: [u'P', u'Z'] (0 in left, 0 in right memories)>
        >>> b.substitutionDict.keys()
        [(u'urn:uuid:name', rdflib.Literal('Bart Simpson',language=None,datatype=None))]
        """
        commonVarKey = []
        if isinstance(token,PartialInstanciation):
            for binding in token.bindings:
                commonVarKey = []
                for var in self.successor.commonVariables:
                    commonVarKey.append(binding.get(var))
                self.substitutionDict.setdefault(tuple(commonVarKey),Set()).add(token)
        else:
            for var in self.successor.commonVariables:            
                commonVarKey.append(token.bindingDict.get(var))        
            self.substitutionDict.setdefault(tuple(commonVarKey),Set()).add(token)
        self.add(token)
                            
    def reset(self):
        self.clear()
        self.substitutionDict = {}

def project(orig_dict, attributes,inverse=False):
    """
    Dictionary projection: http://jtauber.com/blog/2005/11/17/relational_python:_projection
    
    >>> a = {'one' : 1, 'two' : 2, 'three' : 3 }
    >>> project(a,['one','two'])
    {'two': 2, 'one': 1}
    >>> project(a,['four'])
    {}
    >>> project(a,['one','two'],True)
    {'three': 3}
    """
    if inverse:
        return dict([item for item in orig_dict.items() if item[0] not in attributes])
    else:
        return dict([item for item in orig_dict.items() if item[0] in attributes])
        
class PartialInstanciation(object):
    """
    Represents a set of WMEs 'joined' along one or more
    common variables from an ancestral join node 'up' the network
    
    In the RETE/UL PhD thesis, this is refered to as a token, which contains a set of WME triples.
    This is a bit of a clash with the use of the same word (in the original Forgy paper) to 
    describe what is essentially a WME and whether or not it is an addition to the networks memories 
    or a removal
    
    It is implemented (in the RETE/UL thesis) as a linked list of:
        
    structure token:
        parent: token {points to the higher token, for items 1...i-1} 
        wme: WME {gives item i}
    end
    
    Here it is instead implemented as a Set of WME triples associated with a list variables whose
    bindings are consistent
    
    
    >>> aNode = AlphaNode((Variable('X'),RDF.type,Variable('C')))
    >>> token = ReteToken((URIRef('urn:uuid:Boo'),RDF.type,URIRef('urn:uuid:Foo')))
    >>> token = token.bindVariables(aNode)
    >>> PartialInstanciation([token])    
    <PartialInstanciation: Set([<ReteToken: X->urn:uuid:Boo,C->urn:uuid:Foo>])>
    >>> for token in PartialInstanciation([token]):
    ...   print token
    <ReteToken: X->urn:uuid:Boo,C->urn:uuid:Foo>
    """
    def __init__(self,tokens = None,debug = False,consistentBindings = None):
        """
        Note a hash is calculated by 
        sorting & concatenating the hashes of its tokens 
        """
        self.joinedBindings = consistentBindings and consistentBindings or {}
        self.inconsistentVars = Set()
        self.debug = debug
        self.tokens = Set()
        self.bindings = []
        if tokens:
            for token in tokens:
                self.add(token,noPostProcessing=True)        
            self._generateHash()
            self._generateBindings()

    def _generateHash(self):
        tokenHashes = [hash(token) for token in self.tokens]
        tokenHashes.sort()
        self.hash = hash(reduce(lambda x,y:x+y,tokenHashes))        

    def unify(self,left,right):
        """
        Takes two dictionary and collapses it if there are no overlapping 'bindings' or
        'rounds out' both dictionaries so they each have each other's non-overlapping binding 
        """
        bothKeys = [key for key in left.keys() + right.keys() if key not in self.joinedBindings]
        if len(bothKeys) == len(Set(bothKeys)):
            joinDict = left.copy()
            joinDict.update(right)
            return joinDict
        else:
            rCopy = right.copy()
            left.update(project(rCopy,[key for key in right.keys() if key not in left]))          
            lCopy = left.copy()
            right.update(project(lCopy,[key for key in left.keys() if key not in right]))
            return [left,right]

    def _generateBindings(self):
        """
        Generates a list of dictionaries - each a unique variable substitution (binding)
        which applies to the ReteTokens in this PartialInstanciation
    
        >>> aNode = AlphaNode((Variable('S'),Variable('P'),Variable('O')))
        >>> token1 = ReteToken((URIRef('urn:uuid:alpha'),OWL_NS.differentFrom,URIRef('urn:uuid:beta')))
        >>> token2 = ReteToken((URIRef('urn:uuid:beta'),OWL_NS.differentFrom,URIRef('urn:uuid:alpha')))
        >>> cVars = { Variable('P') : OWL_NS.differentFrom }
        >>> inst = PartialInstanciation([token1.bindVariables(aNode),token2.bindVariables(aNode)],consistentBindings=cVars)
        >>> inst
        <PartialInstanciation (joined on ?P): Set([<ReteToken: S->urn:uuid:beta,P->http://www.w3.org/2002/07/owl#differentFrom,O->urn:uuid:alpha>, <ReteToken: S->urn:uuid:alpha,P->http://www.w3.org/2002/07/owl#differentFrom,O->urn:uuid:beta>])>
        >>> inst.joinedBindings
        {u'P': u'http://www.w3.org/2002/07/owl#differentFrom'}
        >>> inst.tokens
        Set([<ReteToken: S->urn:uuid:beta,P->http://www.w3.org/2002/07/owl#differentFrom,O->urn:uuid:alpha>, <ReteToken: S->urn:uuid:alpha,P->http://www.w3.org/2002/07/owl#differentFrom,O->urn:uuid:beta>])
        >>> inst.bindings        
        [{u'P': u'http://www.w3.org/2002/07/owl#differentFrom', u'S': u'urn:uuid:beta', u'O': u'urn:uuid:alpha'}, {u'P': u'http://www.w3.org/2002/07/owl#differentFrom', u'S': u'urn:uuid:alpha', u'O': u'urn:uuid:beta'}]
        
        Ensure unjoined variables with different names aren't bound to the same value 
        (B and Y aren't both bound to "Bart Simpson" simultaneously)
        
        >>> aNode1 = AlphaNode((Variable('A'),URIRef('urn:uuid:name'),Variable('B')))
        >>> aNode2 = AlphaNode((Variable('X'),URIRef('urn:uuid:name'),Variable('Y')))
        >>> token1 = ReteToken((URIRef('urn:uuid:bart'),URIRef('urn:uuid:name'),Literal("Bart Simpson")))
        >>> token1 = token1.bindVariables(aNode1)
        >>> token2 = ReteToken((URIRef('urn:uuid:b'),URIRef('urn:uuid:name'),Literal("Bart Simpson")))
        >>> token2 = token2.bindVariables(aNode2)
        >>> inst = PartialInstanciation([token1,token2])
        >>> pprint(inst.bindings)
        [{u'A': u'urn:uuid:bart',
          u'B': rdflib.Literal('Bart Simpson',language=None,datatype=None),
          u'X': u'urn:uuid:b',
          u'Y': rdflib.Literal('Bart Simpson',language=None,datatype=None)}]

        Ensure different variables which bind to the same value *within* a token includes this combination
        in the resulting bindings

        >>> aNode1 = AlphaNode((Variable('P1'),RDF.type,URIRef('urn:uuid:Prop1')))
        >>> aNode2 = AlphaNode((Variable('P2'),RDF.type,URIRef('urn:uuid:Prop1')))
        >>> aNode3 = AlphaNode((Variable('P1'),Variable('P2'),RDFS.Class))
        >>> token1 = ReteToken((RDFS.domain,RDFS.domain,RDFS.Class))
        >>> token2 = ReteToken((RDFS.domain,RDF.type,URIRef('urn:uuid:Prop1')))
        >>> token3 = ReteToken((RDFS.range,RDF.type,URIRef('urn:uuid:Prop1')))
        >>> token4 = ReteToken((RDFS.range,RDFS.domain,RDFS.Class))
        >>> inst = PartialInstanciation([token1.bindVariables(aNode3),token2.bindVariables(aNode1),token3.bindVariables(aNode2),token4.bindVariables(aNode3)])
        >>> len(inst.bindings)
        3
        >>> inst.bindings
        [{u'P2': u'http://www.w3.org/2000/01/rdf-schema#range', u'P1': u'http://www.w3.org/2000/01/rdf-schema#domain'}, {u'P2': u'http://www.w3.org/2000/01/rdf-schema#domain', u'P1': u'http://www.w3.org/2000/01/rdf-schema#domain'}, {u'P2': u'http://www.w3.org/2000/01/rdf-schema#domain', u'P1': u'http://www.w3.org/2000/01/rdf-schema#range'}]
                
        >>> aNode1 = AlphaNode((Variable('X'),RDF.value,Literal(2)))
        >>> aNode2 = AlphaNode((Variable('X'),RDF.type,Variable('Y')))                            
        >>> aNode3 = AlphaNode((Variable('Z'),URIRef('urn:uuid:Prop1'),Variable('W')))
        >>> token2 = ReteToken((URIRef('urn:uuid:Foo'),RDF.value,Literal(2))).bindVariables(aNode1)
        >>> token3 = ReteToken((URIRef('urn:uuid:Foo'),RDF.type,URIRef('urn:uuid:Baz'))).bindVariables(aNode2)
        >>> token5 = ReteToken((URIRef('urn:uuid:Bar'),URIRef('urn:uuid:Prop1'),URIRef('urn:uuid:Beezle'))).bindVariables(aNode3)
        >>> inst = PartialInstanciation([token2,token3,token5],consistentBindings={Variable('X'):URIRef('urn:uuid:Foo')})
        >>> pprint(list(inst.tokens))
        [<ReteToken: Z->urn:uuid:Bar,W->urn:uuid:Beezle>,
         <ReteToken: X->urn:uuid:Foo>,
         <ReteToken: X->urn:uuid:Foo,Y->urn:uuid:Baz>]
        >>> inst.bindings
        [{u'Y': u'urn:uuid:Baz', u'X': u'urn:uuid:Foo', u'Z': u'urn:uuid:Bar', u'W': u'urn:uuid:Beezle'}]
        
        >>> inst = PartialInstanciation([token2],consistentBindings={Variable('X'):URIRef('urn:uuid:Foo')})
        >>> inst.bindings
        [{u'X': u'urn:uuid:Foo'}]
        
        >>> aNode1 = AlphaNode((Variable('P'),OWL_NS.inverseOf,Variable('Q')))
        >>> aNode2 = AlphaNode((Variable('P'),RDF.type,OWL_NS.InverseFunctionalProperty))
        >>> token1 = ReteToken((URIRef('urn:uuid:Foo'),OWL_NS.inverseOf,URIRef('urn:uuid:Bar'))).bindVariables(aNode1)
        >>> token2 = ReteToken((URIRef('urn:uuid:Foo'),RDF.type,OWL_NS.InverseFunctionalProperty)).bindVariables(aNode1)
        >>> inst = PartialInstanciation([token1,token2],consistentBindings={Variable('P'):URIRef('urn:uuid:Foo'),Variable('Q'):URIRef('urn:uuid:Bar')})
        >>> inst._generateBindings()
        >>> inst.bindings
        [{u'Q': u'urn:uuid:Bar', u'P': u'urn:uuid:Foo'}]
        """
        if len(self.tokens) == 1:
            self.bindings = [list(self.tokens)[0].bindingDict.copy()]
            return
        bindings  = []
        forcedBindings = []
        isolatedBindings = {}
        for token in self.tokens:
            noIterations = 0
            newDict = {}
            for key in ifilter(
                    lambda x:x not in self.joinedBindings,
                    token.bindingDict.keys()):            
                var = key
                newDict[var] = token.bindingDict[var]
                noIterations+=1
            if noIterations == 1:
                isolatedBindings.setdefault(var,Set()).add(token.bindingDict[var])
            elif noIterations > 1:
                forcedBindings.append(newDict)
        revIsolBindings = {}
        for vals in isolatedBindings.itervalues():
            for val in vals:
                revIsolBindings.setdefault(val,Set()).add(var)
        if isolatedBindings:
            for i in xcombine(*tuple([tuple([(key,val) for val in vals]) 
                        for key,vals in iteritems(isolatedBindings) ])):
                isolatedDict = dict(i)                
                for val in isolatedDict.itervalues():
                    keysForVal = revIsolBindings[val] 
                    if len(keysForVal) <= 1:
                        newDict = isolatedDict.copy()
                        newDict.update(self.joinedBindings)
                        if newDict not in bindings:
                            bindings.append(newDict)
        def collapse(left,right):
            if isinstance(left,list):
                if not left:
                    if isinstance(right,list):
                        return right
                    else:
                        return [right]
                elif isinstance(right,list):
                    return reduce([left,right])
                elif len(left)==1:
                    u = self.unify(left[0],right)
                    if isinstance(u,list):
                        return u 
                    else:
                        return [u]
                else:
                    return left+[right]
            elif isinstance(right,list) and not right and left:
                return [left]
            return self.unify(left,right)
        for forcedBinding in forcedBindings:
            newDict = forcedBinding.copy()
            newDict.update(self.joinedBindings)
            if newDict not in bindings:
                bindings.append(newDict)
        self.bindings = reduce(collapse,bindings,[])
        if not self.bindings:
            self.bindings = [self.joinedBindings]

    def __hash__(self):
        return self.hash 

    def __eq__(self,other):
        return hash(self) == hash(other)                   

    def add(self,token,noPostProcessing=False):
        """        
        >>> aNode = AlphaNode((Variable('S'),Variable('P'),Variable('O')))
        >>> token1 = ReteToken((URIRef('urn:uuid:Boo'),RDF.type,URIRef('urn:uuid:Foo')))
        >>> token2 = ReteToken((URIRef('urn:uuid:Foo'),RDF.type,URIRef('urn:uuid:Boo')))
        >>> inst = PartialInstanciation([token1.bindVariables(aNode),token2.bindVariables(aNode)])
        >>> inst    
        <PartialInstanciation: Set([<ReteToken: S->urn:uuid:Boo,P->http://www.w3.org/1999/02/22-rdf-syntax-ns#type,O->urn:uuid:Foo>, <ReteToken: S->urn:uuid:Foo,P->http://www.w3.org/1999/02/22-rdf-syntax-ns#type,O->urn:uuid:Boo>])>
        """
        self.tokens.add(token)        
        if not noPostProcessing:
            self._generateHash()
            self._generateBindings()
    
    def __repr__(self):
        if self.joinedBindings:
            joinMsg = ' (joined on %s)'%(','.join(['?'+v for v in self.joinedBindings]))
        else:
            joinMsg = ''
        return "<PartialInstanciation%s: %s>"%(joinMsg,self.tokens)

    def __iter__(self):
        return self.tokens.__iter__()
    
    def __len(self):
        return len(self.tokens)

    def addConsistentBinding(self,newJoinVariables):
        #newJoinDict = self.joinedBindings.copy()
        #only a subset of the tokens in this partial instanciation will be 'merged' with
        #the new token - joined on the new join variables
        newJoinDict = dict([(v,None) for v in newJoinVariables])
        #newJoinDict.update(dict([(v,None) for v in newJoinVariables]))
        for binding in self.bindings:
            for key,val in newJoinDict.iteritems():
                boundVal = binding.get(key)
                if boundVal is not None:
                    if val is None:
                        newJoinDict[key]=boundVal
        self.joinedBindings.update(newJoinDict)
        self._generateBindings()             
        
    def newJoin(self,rightWME,newJoinVariables):
        """
        >>> aNode1 = AlphaNode((Variable('P1'),RDF.type,URIRef('urn:uuid:Prop1')))
        >>> aNode2 = AlphaNode((Variable('P2'),RDF.type,URIRef('urn:uuid:Prop1')))
        >>> aNode3 = AlphaNode((Variable('P1'),Variable('P2'),RDFS.Class))
        >>> token1 = ReteToken((RDFS.domain,RDFS.domain,RDFS.Class))
        >>> token2 = ReteToken((RDFS.domain,RDF.type,URIRef('urn:uuid:Prop1')))
        >>> token3 = ReteToken((RDFS.range,RDF.type,URIRef('urn:uuid:Prop1')))
        >>> token4 = ReteToken((RDFS.range,RDFS.domain,RDFS.Class))
        >>> token5 = ReteToken((RDFS.domain,RDF.type,URIRef('urn:uuid:Prop1'))).bindVariables(aNode2)
        >>> inst = PartialInstanciation([token2.bindVariables(aNode1),token3.bindVariables(aNode2),token5])
        >>> pprint(list(inst.tokens))
        [<ReteToken: P2->http://www.w3.org/2000/01/rdf-schema#range>,
         <ReteToken: P1->http://www.w3.org/2000/01/rdf-schema#domain>,
         <ReteToken: P2->http://www.w3.org/2000/01/rdf-schema#domain>]
        >>> newInst = inst.newJoin(token1.bindVariables(aNode3),[Variable('P2')])
        >>> token1
        <ReteToken: P1->http://www.w3.org/2000/01/rdf-schema#domain,P2->http://www.w3.org/2000/01/rdf-schema#domain>
        >>> newInst
        <PartialInstanciation (joined on ?P2): Set([<ReteToken: P1->http://www.w3.org/2000/01/rdf-schema#domain,P2->http://www.w3.org/2000/01/rdf-schema#domain>, <ReteToken: P1->http://www.w3.org/2000/01/rdf-schema#domain>, <ReteToken: P2->http://www.w3.org/2000/01/rdf-schema#domain>])>
        >>> pprint(list(newInst.tokens))
        [<ReteToken: P1->http://www.w3.org/2000/01/rdf-schema#domain,P2->http://www.w3.org/2000/01/rdf-schema#domain>,
         <ReteToken: P1->http://www.w3.org/2000/01/rdf-schema#domain>,
         <ReteToken: P2->http://www.w3.org/2000/01/rdf-schema#domain>]
        """
        newJoinDict = self.joinedBindings.copy()
        if newJoinVariables:
            #only a subset of the tokens in this partial instanciation will be 'merged' with
            #the new token - joined on the new join variables
            newJoinDict.update(project(rightWME.bindingDict,newJoinVariables))
            newPInst = PartialInstanciation([],consistentBindings=newJoinDict)
            for token in self.tokens:
                commonVars = False
                for newVar in ifilter(
                    lambda x:x in token.bindingDict and rightWME.bindingDict[x] == token.bindingDict[x],
                    newJoinVariables):
                    #consistent token
                    commonVars = True
                    newPInst.add(token,noPostProcessing=True)
                if not commonVars:
                    #there are no common variables, no need to check
                    newPInst.add(token,noPostProcessing=True)
        else:
            #all of the tokens in this partial instanciation are already bound consistently with
            #respect to the new token
            newPInst = PartialInstanciation([],consistentBindings=newJoinDict)
            for token in self.tokens:
                newPInst.add(token,noPostProcessing=True)
        newPInst.add(rightWME)
        return newPInst            
            
class BetaNode(Node):      
    """
    Performs a rete network join between partial instanciations in its left memory and tokens in its memories

    "The data structure for a join node, therefore, must contain pointers to its two memory
    nodes (so they can be searched), a specification of any variable binding consistency tests to be
    performed, and a list of the node's children. .. (the beta memory is always its parent)."
    
    Setup 3 alpha nodes (Triple Patterns):
        
        aNode1 = ?X rdf:value 1
        aNode2 = ?X rdf:type ?Y
        aNode3 = ?Z <urn:uuid:Prop1> ?W
    
    >>> aNode1 = AlphaNode((Variable('X'),RDF.value,Literal(2)))
    >>> aNode2 = AlphaNode((Variable('X'),RDF.type,Variable('Y')))                            
    >>> aNode3 = AlphaNode((Variable('Z'),URIRef('urn:uuid:Prop1'),Variable('W')))
    

    Rete Network
    ------------

   aNode1 
     |
  joinNode1
       \   aNode2  
        \   /    aNode3
       joinNode2  / 
           \     /
            \   /
         joinNode3    
        
    joinNode3 is the Terminal node
    
    >>> joinNode1 = BetaNode(None,aNode1,aPassThru=True)
    >>> joinNode1.connectIncomingNodes(None,aNode1)
    >>> joinNode2 = BetaNode(joinNode1,aNode2)
    >>> joinNode2.connectIncomingNodes(joinNode1,aNode2)    
    >>> joinNode3 = BetaNode(joinNode2,aNode3)
    >>> joinNode3.connectIncomingNodes(joinNode2,aNode3)

    >>> joinNode1
    <BetaNode (pass-thru): CommonVariables: [?X] (0 in left, 0 in right memories)>
    >>> joinNode2
    <BetaNode : CommonVariables: [?X] (0 in left, 0 in right memories)>

    Setup tokens (RDF triples):
        
        token1 = <urn:uuid:Boo> rdf:value 2
        token2 = <urn:uuid:Foo> rdf:value 2
        token3 = <urn:uuid:Foo> rdf:type <urn:uuid:Baz>             (fires network)
         
        token3 is set with a debug 'trace' so its path through the network is printed along the way
        
        token4 = <urn:uuid:Bash> rdf:type <urn:uuid:Baz>            
        token5 = <urn:uuid:Bar> <urn:uuid:Prop1> <urn:uuid:Beezle>  (fires network)
        token6 = <urn:uuid:Bar> <urn:uuid:Prop1> <urn:uuid:Bundle>  (fires network)

    >>> token1 = ReteToken((URIRef('urn:uuid:Boo'),RDF.value,Literal(2)))
    >>> token2 = ReteToken((URIRef('urn:uuid:Foo'),RDF.value,Literal(2)))
    >>> token3 = ReteToken((URIRef('urn:uuid:Foo'),RDF.type,URIRef('urn:uuid:Baz')),debug=True)
    >>> token4 = ReteToken((URIRef('urn:uuid:Bash'),RDF.type,URIRef('urn:uuid:Baz')))
    >>> token5 = ReteToken((URIRef('urn:uuid:Bar'),URIRef('urn:uuid:Prop1'),URIRef('urn:uuid:Beezle')),debug=True)
    >>> token6 = ReteToken((URIRef('urn:uuid:Bar'),URIRef('urn:uuid:Prop1'),URIRef('urn:uuid:Bundle')))
    >>> tokenList = [token1,token2,token3,token4,token5,token6]

    Setup the consequent (RHS) of the rule:
        { ?X rdf:value 1. ?X rdf:type ?Y. ?Z <urn:uuid:Prop1> ?W } => { ?X a <urn:uuid:SelectedVar> }
        
    a Network 'stub' is setup to capture the conflict set at the time the rule is fired
    
    >>> joinNode3.consequent.update([(Variable('X'),RDF.type,URIRef('urn:uuid:SelectedVar'))])
    >>> class NetworkStub:
    ...     def __init__(self):
    ...         self.firings = 0
    ...         self.conflictSet = Set()
    ...     def fireConsequent(self,tokens,termNode,debug):
    ...         self.firings += 1
    ...         self.conflictSet.add(tokens)
    >>> testHelper = NetworkStub()
    >>> joinNode3.network = testHelper

    Add the tokens sequentially to the top of the network (the alpha nodes).
    token3 triggers a trace through it's path down to the terminal node (joinNode2) 

    >>> aNode1.descendentMemory[0]
    <AlphaMemory: 0 item(s)>
    >>> aNode1.descendentMemory[0].position
    2
    >>> aNode1.activate(token1.unboundCopy())
    >>> aNode1.activate(token2.unboundCopy())
\    >>> joinNode1.memories[LEFT_MEMORY]
    <BetaMemory: 0 item(s)>
    >>> joinNode2.memories[LEFT_MEMORY]
    <BetaMemory: 2 item(s)>
    >>> aNode1.activate(token3.unboundCopy())
    Propagated from <AlphaNode: (u'X', u'http://www.w3.org/1999/02/22-rdf-syntax-ns#type', u'Y'). Feeds 1 beta nodes>
    (u'urn:uuid:Foo', u'http://www.w3.org/1999/02/22-rdf-syntax-ns#type', u'urn:uuid:Baz')
    <BetaNode : CommonVariables: [u'X'] (2 in left, 1 in right memories)>.propagate(right,None,<ReteToken: X->urn:uuid:Foo,Y->urn:uuid:Baz>)
    activating with <PartialInstanciation (joined on ?X): Set([<ReteToken: X->urn:uuid:Foo>, <ReteToken: X->urn:uuid:Foo,Y->urn:uuid:Baz>])>
    
    Add the remaining 3 tokens (each fires the network)
    
    >>> aNode2.activate(token4.unboundCopy())
    >>> list(joinNode3.memories[LEFT_MEMORY])[0]
    <PartialInstanciation (joined on ?X): Set([<ReteToken: X->urn:uuid:Foo>, <ReteToken: X->urn:uuid:Foo,Y->urn:uuid:Baz>])>
    >>> aNode3.activate(token5.unboundCopy()))
    Propagated from <AlphaNode: (u'Z', u'urn:uuid:Prop1', u'W'). Feeds 1 beta nodes>
    (u'urn:uuid:Bar', u'urn:uuid:Prop1', u'urn:uuid:Beezle')
    <TerminalNode : CommonVariables: [] (1 in left, 1 in right memories)>.propagate(right,None,<ReteToken: Z->urn:uuid:Bar,W->urn:uuid:Beezle>)
    activating with <PartialInstanciation (joined on ?X): Set([<ReteToken: Z->urn:uuid:Bar,W->urn:uuid:Beezle>, <ReteToken: X->urn:uuid:Foo>, <ReteToken: X->urn:uuid:Foo,Y->urn:uuid:Baz>])>

    >>> aNode3.activate(token6.unboundCopy())
    >>> joinNode3
    <TerminalNode : CommonVariables: [] (1 in left, 2 in right memories)>
    >>> testHelper.firings
    2
    >>> pprint(testHelper.conflictSet)
    Set([<PartialInstanciation (joined on ?X): Set([<ReteToken: Z->urn:uuid:Bar,W->urn:uuid:Beezle>, <ReteToken: X->urn:uuid:Foo>, <ReteToken: X->urn:uuid:Foo,Y->urn:uuid:Baz>])>, <PartialInstanciation (joined on ?X): Set([<ReteToken: Z->urn:uuid:Bar,W->urn:uuid:Bundle>, <ReteToken: X->urn:uuid:Foo>, <ReteToken: X->urn:uuid:Foo,Y->urn:uuid:Baz>])>])
    """
    def __init__(self,leftNode,rightNode,aPassThru=False):
        self.instanciatingTokens = set()
        self.aPassThru = aPassThru 
        self.name = BNode()
        self.network = None
        self.consequent = Set() #List of tuples in RHS
        self.leftNode = leftNode
        self.rightNode = rightNode #The incoming right input of a BetaNode is always an AlphaNode
        self.memories = {}
        self.descendentMemory = []
        self.descendentBetaNodes = Set()
        self.leftUnlinkedNodes = Set()
        self.unlinkedMemory = None
        self.fedByBuiltin = None
        if isinstance(leftNode,BuiltInAlphaNode):
            self.fedByBuiltin = LEFT_MEMORY
            assert not isinstance(rightNode,BuiltInAlphaNode),"Both %s and %s are builtins feeding a beta node!"%(leftNode,rightNode)
            self.memories[RIGHT_MEMORY] = ReteMemory((self,RIGHT_MEMORY,leftNode.n3builtin))
        else:
            self.memories[RIGHT_MEMORY] = ReteMemory(self,RIGHT_MEMORY)
            
        assert not(self.fedByBuiltin),"No support for 'built-ins', function symbols, or non-equality tests"
        if isinstance(rightNode,BuiltInAlphaNode):
            self.fedByBuiltin = RIGHT_MEMORY
            assert not isinstance(leftNode,BuiltInAlphaNode),"Both %s and %s are builtins feeding a beta node!"%(leftNode,rightNode)
            self.memories[LEFT_MEMORY]  = ReteMemory(self,LEFT_MEMORY,rightNode.n3builtin)
        else:
            self.memories[LEFT_MEMORY]  = ReteMemory(self,LEFT_MEMORY)        
        if aPassThru:
            if rightNode:
                self.leftVariables = Set()
                self.rightVariables = collectVariables(self.rightNode)
                self.commonVariables = list(self.rightVariables)
            else:
                self.leftVariables = self.rightVariables = Set()
                self.commonVariables = []
        else: 
            self.leftVariables = collectVariables(self.leftNode)
            self.rightVariables = collectVariables(self.rightNode)        
            self.commonVariables = [leftVar for leftVar in self.leftVariables if leftVar in self.rightVariables]
        self.leftIndex  = {}
        self.rightIndex = {}

    def connectIncomingNodes(self,leftNode,rightNode):
        if leftNode:
            if self.leftNode and LEFT_UNLINKING:
                #candidate for left unlinking
                self.leftUnlinkedNodes.add(leftNode) 
                leftNode.unlinkedMemory = ReteMemory(self,LEFT_MEMORY)
#                print "unlinked %s from %s"%(leftNode,self)
            elif self.leftNode:            
                leftNode.descendentMemory.append(self.memories[LEFT_MEMORY])
                leftNode.descendentBetaNodes.add(self)        
        rightNode.descendentMemory.append(self.memories[RIGHT_MEMORY])
        rightNode.descendentBetaNodes.add(self)
        
    def __repr__(self):
        if self.consequent and self.fedByBuiltin:
            nodeType = 'TerminalBuiltin(%s)'%(self.memories[self._oppositeMemory(self.fedByBuiltin)].filter)
        elif self.consequent:
            nodeType = 'TerminalNode'
        elif self.fedByBuiltin:
            nodeType = 'Builtin(%s)'%(self.memories[self._oppositeMemory(self.fedByBuiltin)].filter)
        else:            
            nodeType = 'BetaNode'
        if self.unlinkedMemory is not None:
            nodeType = 'LeftUnlinked-' + nodeType
        leftLen = self.memories[LEFT_MEMORY] and len(self.memories[LEFT_MEMORY]) or 0
        return "<%s %s: CommonVariables: %s (%s in left, %s in right memories)>"%(nodeType,self.aPassThru and "(pass-thru)" or '',self.commonVariables,leftLen,len(self.memories[RIGHT_MEMORY]))

    def _activate(self,partInstOrList,debug=False):
            if debug:
                print "activating with %s"%(partInstOrList)
            if self.unlinkedMemory is not None:
                if debug:
                    print "adding %s into unlinked memory"%(partInstOrList)                
                self.unlinkedMemory.addToken(partInstOrList,debug)                
            for memory in self.descendentMemory:  
                if debug:
                    print "\t",memory.successor
                #print self,partInstOrList
                memory.addToken(partInstOrList,debug)
                if memory.successor.aPassThru or not memory.successor.checkNullActivation(memory.position):
                    if memory.position == LEFT_MEMORY:
                        memory.successor.propagate(memory.position,debug,partInstOrList)
                    else:
                        #print partInstOrList
                        memory.successor.propagate(None,debug,partInstOrList)
            
            if self.consequent:
                self.network.fireConsequent(partInstOrList,self,debug)

    def _unrollTokens(self,iterable):
        for token in iterable:
            if isinstance(token,PartialInstanciation):
                for i in token:
                    yield i
            else:
                yield token
                                             
    def _oppositeMemory(self,memoryPosition):
        if memoryPosition == LEFT_MEMORY:
            return RIGHT_MEMORY
        else:
            return LEFT_MEMORY
            
    def _checkOpposingMemory(self,memoryPosition):
        return bool(len(self.memories[self._oppositeMemory(memoryPosition)]))

    def checkNullActivation(self,source):
        """
        Checks whether this beta node is involved in a NULL activation relative to the source.
        NULL activations are where one of the opposing memories that feed
        this beta node are empty.  Takes into account built-in filters/function.
        source is the position of the 'triggering' memory (i.e., the memory that had a token added)
        """        
        oppositeMem = self.memories[self._oppositeMemory(source)]
        return not self.fedByBuiltin and not oppositeMem
            
    def propagate(self,propagationSource,debug = False,partialInst=None,wme=None):
        """
        .. 'activation' of Beta Node - checks for consistent 
        variable bindings between memory of incoming nodes ..
        Beta (join nodes) with no variables in common with both ancestors
        activate automatically upon getting a propagation 'signal'

        """
        if debug and propagationSource:
            print "%s.propagate(%s,%s,%s)"%(self,memoryPosition[propagationSource],partialInst,wme)
            print "### Left Memory ###"
            pprint(list(self.memories[LEFT_MEMORY]))
            print "###################"
            print "### Right Memory ###"
            pprint(list(self.memories[RIGHT_MEMORY]))
            print "####################"
        if self.aPassThru:
            if self.consequent:
                assert not partialInst,"%s,%s"%(partialInst,wme)
                self._activate(PartialInstanciation([wme],consistentBindings=wme.bindingDict.copy()),debug)                
                
            elif self.memories[RIGHT_MEMORY]:
                #pass on wme as an unjoined partInst
                #print self
                if wme:
                    self._activate(PartialInstanciation([wme],consistentBindings=wme.bindingDict.copy()),debug)
                elif partialInst:
                    #print "## Problem ###"
                    #print "%s.propagate(%s,%s,%s)"%(self,memoryPosition[propagationSource],partialInst,wme)
                    self._activate(partialInst,debug)                
        elif not propagationSource:
            #Beta node right activated by another beta node
            #Need to unify on common variable hash, using the bindings
            #provided by the partial instanciation that triggered the activation
            if partialInst:
                for binding in partialInst.bindings:
                    commonVals = tuple([binding[var] for var in self.commonVariables])
                    lTokens = self.memories[RIGHT_MEMORY].substitutionDict.get(commonVals,Set())
                    rTokens = self.memories[LEFT_MEMORY].substitutionDict.get(commonVals,Set())
                    joinedTokens = Set(self._unrollTokens(rTokens | lTokens))
                    if joinedTokens:                    
                        commonDict = dict([(var,list(commonVals)[self.commonVariables.index(var)]) for var in self.commonVariables])
                        newP = PartialInstanciation(joinedTokens,consistentBindings=commonDict)
                        self._activate(newP,debug)            
            
        elif propagationSource == LEFT_MEMORY:
            #Doesn't check for null left activation! - cost is mitigated by 
            #left activation, partialInst passed down
            #procedure join-node-left-activation (node: join-node, t: token)
            #     for each w in node.amem.items do
            #         if perform-join-tests (node.tests, t, w) then
            #             for each child in node.children do left-activation (child, t, w)
            # end            
            matches = Set()
            if self.fedByBuiltin:
                filter = self.memories[self._oppositeMemory(self.fedByBuiltin)].filter
                newConsistentBindings = [term for term in [filter.argument,
                                                           filter.result] 
                                                if isinstance(term,Variable) and \
                                                term not in partialInst.joinedBindings]
                partialInst.addConsistentBinding(newConsistentBindings)
                for binding in partialInst.bindings:
                    lhs = filter.argument
                    rhs = filter.result
                    lhs = isinstance(lhs,Variable) and binding[lhs] or lhs
                    rhs = isinstance(rhs,Variable) and binding[rhs] or rhs
                    assert lhs is not None and rhs is not None
                    if filter.func(lhs,rhs):
                        matches.add(partialInst)
            else:
                for binding in partialInst.bindings:
                    #iterate over the binding combinations 
                    #and use the substitutionDict in the right memory to find matching WME'a
                    if debug:
                        print "\t", binding
                        
                    substitutedTerm=[]
                    commonDictKV=[]
                    for var in self.commonVariables:
                        if var not in binding:
                            continue
                        else:
                            commonDictKV.append((var,binding[var]))
                            substitutedTerm.append(binding[var])
                    rWMEs = self.memories[RIGHT_MEMORY].substitutionDict.get(tuple(substitutedTerm),
                                                                             Set())
                    commonDict = dict(commonDictKV)
                    if debug:
                        print commonDict,rWMEs, self.memories[RIGHT_MEMORY].substitutionDict.keys()
                    for rightWME in rWMEs:
                        if isinstance(rightWME,ReteToken):
                            matches.add(partialInst.newJoin(
                                rightWME,
                                ifilter(lambda x:x not in partialInst.joinedBindings,
                                    self.commonVariables)))
                            # [var for var in self.commonVariables if var not in partialInst.joinedBindings]))
                        else:
                            #Joining two Beta/Join nodes!
                            joinedTokens = list(partialInst.tokens | rightWME.tokens)
                            #print "### joining two tokens ###"
                            #pprint(joinedTokens)
                            if self.consequent:
                                for consequent in self.consequent:
                                    consVars = ifilter(lambda x:isinstance(x,Variable),consequent)
                                    # [i for i in consequent if isinstance(i,Variable)]                                
                                failed = True
                                for binding in PartialInstanciation(joinedTokens,consistentBindings=commonDict).bindings:
                                    if any(consVars,lambda x:x not in binding):# [key for key in consVars if key not in binding]:
                                        continue
                                    else:
                                        failed = False                                                                    
                                if not failed:                                        
                                    newP = PartialInstanciation(joinedTokens,consistentBindings=commonDict)
                                    matches.add(newP)
                            else:
                                newP = PartialInstanciation(joinedTokens,consistentBindings=commonDict)
                                matches.add(newP)
                                
            for pInst in matches:
                self._activate(pInst,debug)                    
        else:            
            #right activation, partialInst & wme passed down
            #procedure join-node-right-activation (node: join-node, w: WME)
            #    for each t in node.parent.items do {"parent" is the beta memory node}
            #        if perform-join-tests (node.tests, t, w) then
            #            for each child in node.children do left-activation (child, t, w)
            #end
            #pprint(self.memories[self._oppositeMemory(propagationSource)])
            matches = Set()
            lPartInsts = self.memories[LEFT_MEMORY].substitutionDict.get(tuple([wme.bindingDict[var] for var in self.commonVariables]))
            if lPartInsts:
                for partialInst in lPartInsts:
                    if not isinstance(partialInst,PartialInstanciation):
                        singleToken = PartialInstanciation([partialInst],consistentBindings=partialInst.bindingDict.copy())
                        matches.add(singleToken)
                    else:
                        assert isinstance(partialInst,PartialInstanciation),repr(partialInst)
                        matches.add(partialInst.newJoin(
                                        wme,
                                        ifilter(lambda x:x not in partialInst.joinedBindings,
                                                self.commonVariables)))
                                    # [var for var in self.commonVariables if var not in partialInst.joinedBindings]))
            for pInst in matches:
                self._activate(pInst,debug)  

TEST_NS = Namespace('http://example.com/text1/')

def PopulateTokenFromANode(aNode,bindings):
    #print aNode, bindings
    termList = [isinstance(term,Variable) and bindings[term] or term
                    for term in aNode.triplePattern]
    token = ReteToken(tuple(termList))
    token.bindVariables(aNode)
    return token

class PartialInstanciationTests(unittest.TestCase):
    def testConsistentBinding(self):
        allBindings = {}
        allBindings.update(self.joinedBindings)
        allBindings.update(self.unJoinedBindings)
        aNodes = [self.aNode1,
                  self.aNode2,
                  self.aNode5,
                  self.aNode6,
                  self.aNode7,
                  self.aNode8,
                  self.aNode9,
                  self.aNode10,
                  self.aNode11]
        pToken = PartialInstanciation(
                      tokens = [PopulateTokenFromANode(aNode,
                                                       allBindings) 
                                  for aNode in aNodes],
                      consistentBindings = self.joinedBindings)
        #print pToken
        pToken.addConsistentBinding(self.unJoinedBindings.keys())
        #print pToken.joinedBindings
        for binding in pToken.bindings:
            for key in self.unJoinedBindings:
                self.failUnless(key in binding, "Missing key %s from %s"%(key,binding))
                        
    def setUp(self):
        self.aNode1 = AlphaNode((Variable('HOSP'),
                                 TEST_NS.contains,
                                 Variable('HOSP_START_DATE')))                
        self.aNode2 = AlphaNode((Variable('HOSP'),
                                 RDF.type,
                                 TEST_NS.Hospitalization))                
        self.aNode5 = AlphaNode((Variable('HOSP_START_DATE'),
                                 TEST_NS.dateTimeMin,
                                 Variable('ENCOUNTER_START')))                
        self.aNode6 = AlphaNode((Variable('HOSP_STOP_DATE'),
                                 RDF.type,
                                 TEST_NS.EventStopDate))                
        self.aNode7 = AlphaNode((Variable('HOSP_STOP_DATE'),
                                 TEST_NS.dateTimeMax,
                                 Variable('ENCOUNTER_STOP')))                
        self.aNode8 = AlphaNode((Variable('EVT_DATE'),
                                 RDF.type,
                                 TEST_NS.EventStartDate))                
        self.aNode9 = AlphaNode((Variable('EVT_DATE'),
                                 TEST_NS.dateTimeMin,
                                 Variable('EVT_START_MIN')))                
        self.aNode10 =AlphaNode((Variable('EVT'),
                                 TEST_NS.contains,
                                 Variable('EVT_DATE')))                
        self.aNode11 =AlphaNode((Variable('EVT'),
                                 RDF.type,
                                 Variable('EVT_KIND')))

        self.joinedBindings = {Variable('HOSP_START_DATE'):
                               BNode(),
                               Variable('HOSP_STOP_DATE'):
                               BNode(),
                               Variable('HOSP'):
                               BNode()}
        self.unJoinedBindings = {Variable('EVT'):
                                 BNode(),
                                 Variable('EVT_DATE'):
                                 BNode(),
                                 Variable('EVT_KIND'):
                                 TEST_NS.ICUStay}
        for dtVariable in [Variable('ENCOUNTER_START'),
                           Variable('ENCOUNTER_STOP'),
                           Variable('EVT_START_MIN')]:
            self.unJoinedBindings[dtVariable]=Literal("2007-02-14T10:00:00",
                                                      datatype=_XSD_NS.dateTime)
                                  
def test():
#    import doctest
#    doctest.testmod()
    suite = unittest.makeSuite(PartialInstanciationTests)
    unittest.TextTestRunner(verbosity=5).run(suite)    

if __name__ == '__main__':
    test()