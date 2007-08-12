#!/usr/local/bin/python
# -*- coding: utf-8 -*-
"""
This module defines a Description Horn Logic implementation as defined
by Grosof, B. et.al. ("Description Logic Programs: Combining Logic Programs with 
Description Logic" [1]) in section 4.4.  As such, it implements recursive mapping
functions "T", "Th" and "Tb" which result in "custom" (dynamic) rulesets, RIF Basic 
Logic Dialect: Horn rulesets [2], [3].  The rulesets are evaluated against an efficient RETE-UL
network.

As such, it is a Description Logic Programming [1] Implementation on top of RETE-UL:

"A DLP is directly defined as the LP-correspondent of a def-Horn
ruleset that results from applying the mapping T ."

The mapping is as follows:

== Core (Description Horn Logic) ==

Th(A,x)                      -> A(x)
Th((C1 ^ C2 ^ ... ^ Cn),x)   -> Th(C1,x) ^ Th(C2,x) ^ ... ^ Th(Cn,x) 
Th((∀R.C),x)                 -> Th(C(y)) :- R(x,y)
Tb(A(x))                     -> A(x)
Tb((C1 ^ C2 ^ ... ^ Cn),x)   -> Tb(C1,x) ^ Tb(C2,x) ^ ... ^ Tb(Cn,x)
Tb((C1 v C2 v ... v Cn),x)   -> Tb(C1,x) v Tb(C2,x) v ... v Tb(Cn,x)
Tb((∃R.C),x)                ->  R(x,y) ^ Tb(C,y) 

In addition, basic logic tautologies are included in the DHL definition:

(H ^ H0) :- B                 -> { H  :- B
                                   H0 :- B }
(H :- H0) :- B                -> H :- B ^ H0

H :- (B v B0)                 -> { H :- B
                                   H :- B0 }

== Class Equivalence ==

T(owl:equivalentClass(C,D)) -> { T(rdfs:subClassOf(C,D) 
                                 T(rdfs:subClassOf(D,C) }
                                 
== Domain and Range Axioms (Base Description Logic: "ALC") ==                                                                                                       

T(rdfs:range(P,D))  -> D(y) := P(x,y)
T(rdfs:domain(P,D)) -> D(x) := P(x,y)

== Property Axioms (Role constructors: "I") ==

T(rdfs:subPropertyOf(P,Q))     -> Q(x,y) :- P(x,y)
T(owl:equivalentProperty(P,Q)) -> { Q(x,y) :- P(x,y)
                                    P(x,y) :- Q(x,y) }
T(owl:inverseOf(P,Q))          -> { Q(x,y) :- P(y,x)
                                    P(y,x) :- Q(x,y) }
T(owl:TransitiveProperty(P))   -> P(x,z) :- P(x,y) ^ P(y,z)                                                                        

[1] http://www.cs.man.ac.uk/~horrocks/Publications/download/2003/p117-grosof.pdf
[2] http://www.w3.org/2005/rules/wg/wiki/Core/Positive_Conditions
[3] http://www.w3.org/2005/rules/wg/wiki/asn06

"""

from __future__ import generators
from sets import Set
from rdflib import BNode, RDF, Namespace, Variable, RDFS
from rdflib.Collection import Collection
from rdflib.store import Store,VALID_STORE, CORRUPTED_STORE, NO_STORE, UNKNOWN
from rdflib.Literal import Literal
from pprint import pprint, pformat
import sys
from rdflib.term_utils import *
from rdflib.Graph import QuotedGraph, Graph
from rdflib.store.REGEXMatching import REGEXTerm, NATIVE_REGEX, PYTHON_REGEX
from FuXi.Rete.RuleStore import Formula
from FuXi.Rete.AlphaNode import AlphaNode
from FuXi.Horn.PositiveConditions import And, Or, Uniterm, Condition, Atomic
from FuXi.Horn.HornRules import Clause
from cStringIO import StringIO

non_DHL_OWL_Semantics=\
"""
@prefix log: <http://www.w3.org/2000/10/swap/log#>.
@prefix math: <http://www.w3.org/2000/10/swap/math#>.
@prefix owl: <http://www.w3.org/2002/07/owl#>.
@prefix xsd: <http://www.w3.org/2001/XMLSchema#>.
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#>.
@prefix rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>.
@prefix : <http://eulersharp.sourceforge.net/2003/03swap/owl-rules#>.
@prefix list: <http://www.w3.org/2000/10/swap/list#>.
#Additional OWL-compliant semantics, mappable to Production Rules 

{?C owl:disjointWith ?B. ?M a ?C. ?Y a ?B } => {?M owl:differentFrom ?Y}.
{?P owl:inverseOf ?Q. ?P a owl:InverseFunctionalProperty} => {?Q a owl:FunctionalProperty}.
{?P owl:inverseOf ?Q. ?P a owl:FunctionalProperty} => {?Q a owl:InverseFunctionalProperty}.
{?P a owl:FunctionalProperty. ?S ?P ?O. ?S ?P ?Y} => {?O = ?Y}.
{?P a owl:InverseFunctionalProperty. ?S ?P ?O. ?Y ?P ?O} => {?S = ?Y}.
{?T1 = ?T2. ?S = ?T1} => {?S = ?T2}.
{?T1 ?P ?O. ?T1 = ?T2.} => {?T2 ?P ?O}.

#For OWL/InverseFunctionalProperty/premises004
{?C owl:oneOf ?L. ?L rdf:first ?X; rdf:rest rdf:nil. ?P rdfs:domain ?C} => {?P a owl:InverseFunctionalProperty}.
#For OWL/InverseFunctionalProperty/premises004
{?C owl:oneOf ?L. ?L rdf:first ?X; rdf:rest rdf:nil. ?P rdfs:range ?C} => {?P a owl:FunctionalProperty}.

#For OWL/oneOf
{?C owl:oneOf ?L. ?X list:in ?L} => {?X a ?C}.
{?L rdf:first ?I} => {?I list:in ?L}.
{?L rdf:rest ?R. ?I list:in ?R} => {?I list:in ?L}.

{?P a owl:SymmetricProperty. ?S ?P ?O} => {?O ?P ?S}.
{?S owl:differentFrom ?O} => {?O owl:differentFrom ?S}.
{?S owl:complementOf ?O} => {?O owl:complementOf ?S}.
{?S owl:disjointWith ?O} => {?O owl:disjointWith ?S}.
"""

OWL_NS    = Namespace("http://www.w3.org/2002/07/owl#")

LOG = Namespace("http://www.w3.org/2000/10/swap/log#")
Any = None

LHS = 0
RHS = 1

def NormalizeClause(clause):
    if not isinstance(clause.head,Condition):
        h=list(clause.head)
        assert len(h)==1
        clause.head = h[0]
    if not isinstance(clause.body,Condition):
        b=list(clause.body)
        assert len(b)==1
        clause.body = b[0]
    assert isinstance(clause.head,(Condition,Clause)),repr(clause.head)
    assert isinstance(clause.body,Condition),repr(clause.body)
    assert isinstance(clause.head,(Atomic,And,Clause)),repr(head)
    assert isinstance(clause.body,(Condition,Or)),repr(body)
    return clause

class Clause:
    """
    The RETE-UL algorithm supports conjunctions of facts in the head of a rule
    i.e.:   H1 ^ H2 ^ ... ^ H3 :- B1 ^  ^ Bm
    The Clause definition os overridden to permit this syntax (not allowed
    in definite LP or Horn rules)
    
    In addition, since we allow (in definite Horn) entailments beyond simple facts
    we ease restrictions on the form of the head to include Clauses
    """
    def __init__(self,body,head):
        self.body = body
        self.head = head
        
    def __repr__(self):
        return "%r :- %r"%(self.head,self.body)

def MapDLPtoNetwork(network,factGraph):
    for horn_clause in T(factGraph):
        print "## RIF BLD Horn Rules: Before LloydTopor: ##\n",horn_clause
        print "## RIF BLD Horn Rules: After LloydTopor: ##"
        for tx_horn_clause in LloydToporTransformation(horn_clause):
            ExtendN3Rules(network,tx_horn_clause)
            print tx_horn_clause
        print "#######################"

def ExtendN3Rules(network,horn_clause):
    """
    Extends the network with the given Horn clause
    """
    ruleStore = network.ruleStore
    lhs = BNode()
    rhs = BNode()
    assert isinstance(horn_clause.body,(And,Uniterm)),list(horn_clause.body)
    assert len(list(horn_clause.body))
    for term in horn_clause.body:
        ruleStore.formulae.setdefault(lhs,Formula(lhs)).append(term.toRDFTuple())
    assert isinstance(horn_clause.head,(And,Uniterm))
    for term in horn_clause.head:
        ruleStore.formulae.setdefault(rhs,Formula(rhs)).append(term.toRDFTuple())
    ruleStore.rules.append((ruleStore.formulae[lhs],ruleStore.formulae[rhs]))
    network.buildNetwork(iter(ruleStore.formulae[lhs]),
                         iter(ruleStore.formulae[rhs]),
                         ruleStore.formulae[lhs],
                         ruleStore.formulae[rhs])
    network.alphaNodes = [node for node in network.nodes.values() if isinstance(node,AlphaNode)]

def T(owlGraph):
    """
    T(rdfs:subClassOf(C,D))       -> Th(D(y)) :- Tb(C(y))
    
    T(owl:equivalentClass(C,D)) -> { T(rdfs:subClassOf(C,D) 
                                     T(rdfs:subClassOf(D,C) }
    
    A generator over the Logic Programming rules which correspond
    to the DL subsumption axiom denoted via rdfs:subClassOf
    """
    for c,p,d in owlGraph.triples((None,RDFS.subClassOf,None)):
        yield NormalizeClause(Clause(Tb(owlGraph,c),Th(owlGraph,d)))
        assert isinstance(c,URIRef) 
    for c,p,d in owlGraph.triples((None,OWL_NS.equivalentClass,None)):
        yield NormalizeClause(Clause(Tb(owlGraph,c),Th(owlGraph,d)))
        yield NormalizeClause(Clause(Tb(owlGraph,d),Th(owlGraph,c)))
    for s,p,o in owlGraph.triples((None,OWL_NS.intersectionOf,None)):
        if isinstance(s,URIRef):
            #special case, owl:intersectionOf is a neccessary and sufficient
            #criteria and should thus work in *both* directions
            body = And([Uniterm(RDF.type,[Variable("X"),i],newNss=owlGraph.namespaces()) \
                           for i in Collection(owlGraph,o)])
            head = Uniterm(RDF.type,[Variable("X"),s],newNss=owlGraph.namespaces())
            yield Clause(body,head)
            yield Clause(head,body)
        
    for s,p,o in owlGraph.triples((None,OWL_NS.unionOf,None)):
        if isinstance(s,URIRef):
            #special case, owl:unionOf is a neccessary and sufficient
            #criteria and should thus work in *both* directions
            body = Or([Uniterm(RDF.type,[Variable("X"),i],newNss=owlGraph.namespaces()) \
                           for i in Collection(owlGraph,o)])
            head = Uniterm(RDF.type,[Variable("X"),s],newNss=owlGraph.namespaces())
            yield Clause(body,head)
    for s,p,o in owlGraph.triples((None,OWL_NS.inverseOf,None)):
        #    T(owl:inverseOf(P,Q))          -> { Q(x,y) :- P(y,x)
        #                                        P(y,x) :- Q(x,y) }
        newVar = Variable(BNode())
        body1 = Uniterm(s,[newVar,Variable("X")],newNss=owlGraph.namespaces())
        head1 = Uniterm(o,[Variable("X"),newVar],newNss=owlGraph.namespaces())
        yield Clause(body1,head1)
        newVar = Variable(BNode())
        body2 = Uniterm(o,[Variable("X"),newVar],newNss=owlGraph.namespaces())
        head2 = Uniterm(s,[newVar,Variable("X")],newNss=owlGraph.namespaces())
        yield Clause(body2,head2)
    for s,p,o in owlGraph.triples((None,RDF.type,OWL_NS.TransitiveProperty)):
        #T(owl:TransitiveProperty(P))   -> P(x,z) :- P(x,y) ^ P(y,z)
        y = Variable(BNode())
        z = Variable(BNode())
        x = Variable("X")
        body = And([Uniterm(s,[x,y],newNss=owlGraph.namespaces()),\
                    Uniterm(s,[y,z],newNss=owlGraph.namespaces())])
        head = Uniterm(s,[x,z],newNss=owlGraph.namespaces())
        yield Clause(body,head)
            
def LloydToporTransformation(clause):
    """
    (H ^ H0) :- B                 -> { H  :- B
                                       H0 :- B }
    (H :- H0) :- B                -> H :- B ^ H0
    
    H :- (B v B0)                 -> { H :- B
                                       H :- B0 }
    """
    assert isinstance(clause,Clause),repr(clause)
    if isinstance(clause.body,Or):
        for atom in clause.body.formulae:
            yield Clause(atom,clause.head)
    elif isinstance(clause.head,Clause):
        yield Clause(And([clause.body,clause.head.body]),clause.head.head)
    elif isinstance(clause.head,Or) or \
         not isinstance(clause.body,Condition):
        print clause.head
        raise
    else:
        yield clause
    

def commonConjunctionMapping(owlGraph,conjuncts,innerFunc,variable=Variable("X")):
    """
    DHL: T*((C1 ^ C2 ^ ... ^ Cn),x)    -> T*(C1,x) ^ T*(C2,x) ^ ... ^ T*(Cn,x)
    OWL: intersectionOf(c1 … cn) =>  EC(c1) ∩ … ∩ EC(cn)
    """
    conjuncts = Collection(owlGraph,conjuncts)
    return And([innerFunc(c,variable) for c in conjuncts])

def Th(owlGraph,_class,variable=Variable('X'),position=LHS):
    """
    Th(A,x)                      -> A(x)
    Th((C1 ^ C2 ^ ... ^ Cn),x)   -> Th(C1,x) ^ Th(C2,x) ^ ... ^ Th(Cn,x) 
    Th((∀R.C),x)                -> Th(C(y)) :- R(x,y)
    """
    props = list(set(owlGraph.predicates(subject=_class)))
    if OWL_NS.intersectionOf in props:
        #http://www.w3.org/TR/owl-semantics/#owl_intersectionOf
        for s,p,o in owlGraph.triples((_class,OWL_NS.intersectionOf,None)):
            rt=commonConjunctionMapping(owlGraph,o,Th,variable=variable)
            if isinstance(s,URIRef):
                rt = rt.formulae.append(Uniterm(RDF.type,[variable,s],newNss=owlGraph.namespaces()))
            yield rt
    elif OWL_NS.allValuesFrom in props:
        #http://www.w3.org/TR/owl-semantics/#owl_allValuesFrom
        #restriction(p allValuesFrom(r))    {x ∈ O | <x,y> ∈ ER(p) implies y ∈ EC(r)}
        for s,p,o in owlGraph.triples((_class,OWL_NS.allValuesFrom,None)):
            prop = list(owlGraph.objects(subject=_class,predicate=OWL_NS.onProperty))[0]
            newVar = Variable(BNode())
            body = Uniterm(prop,[variable,newVar],newNss=owlGraph.namespaces())
            for head in Th(owlGraph,o,variable=newVar):
                yield Clause(body,head)
    else:
        #Simple class
        yield Uniterm(RDF.type,[variable,_class],newNss=owlGraph.namespaces())
    
def Tb(owlGraph,_class,variable=Variable('X')):
    """
    Tb(A(x))                      -> A(x)
    Tb((C1 ^ C2 ^ ... ^ Cn),x)    -> Tb(C1,x) ^ Tb(C2,x) ^ ... ^ Tb(Cn,x)
    Tb((C1 v C2 v ... v Cn),x)    -> Tb(C1,x) v Tb(C2,x) v ... v Tb(Cn,x)
    Tb((∃R.C),x)                 ->  R(x,y) ^ Tb(C,y) 
    """
    props = list(set(owlGraph.predicates(subject=_class)))
    if OWL_NS.intersectionOf in props:
        #http://www.w3.org/TR/owl-semantics/#owl_intersectionOf
        for s,p,o in owlGraph.triples((_class,OWL_NS.intersectionOf,None)):
            rt=commonConjunctionMapping(owlGraph,o,Th,variable=variable)
            if isinstance(s,URIRef):
                rt = rt.formulae.append(Uniterm(RDF.type,[variable,s],newNss=owlGraph.namespaces()))
            yield rt
    elif OWL_NS.unionOf in props:
        #http://www.w3.org/TR/owl-semantics/#owl_unionOf
        #OWL semantics: unionOf(c1 … cn) => EC(c1) ∪ … ∪ EC(cn)
        for s,p,o in owlGraph.triples((_class,OWL_NS.unionOf,None)):
            yield Or([Tb(owlGraph,c,variable=variable) \
                           for c in Collection(owlGraph,o)])
    elif OWL_NS.someValuesFrom in props:
        #http://www.w3.org/TR/owl-semantics/#someValuesFrom
        #estriction(p someValuesFrom(e)) {x ∈ O | ∃ <x,y> ∈ ER(p) ∧ y ∈ EC(e)}
        prop = list(owlGraph.objects(subject=_class,predicate=OWL_NS.onProperty))[0]
        newVar = Variable(BNode())
        body = Uniterm(prop,[variable,newVar],newNss=owlGraph.namespaces())
        head = Th(owlGraph,o,variable=newVar)
        yield And([Uniterm(prop,[variable,newVar],newNss=owlGraph.namespaces()),
                    Tb(owlGraph,o,variable=newVar)])
    else:
        #simple class
        yield Uniterm(RDF.type,[variable,_class],newNss=owlGraph.namespaces())