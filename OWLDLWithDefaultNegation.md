# Introduction #

> The SPARQL specification indicates that it is possible to test if a graph pattern does not match a dataset, via a combination of optional patterns and filter conditions (like negation as failure in logic programming)([9](9.md) Sec. 11.4.1).  In this section we analyze in depth the scope and limitations of this approach.  We will introduce a syntax for the “difference” of two graph patterns P1 and P2, denoted (P1 MINUS P2), with the intended informal meaning: “the set of mappings that match P1 and does not match P2”.

Uses telescope to construct the SPARQL MINUS BGP expressions for body conditions with default negation formulae

```
   .. setup a network ..
   from FuXi.DLP.DLNormalization import NormalFormReduction
   from FuXi.Syntax.InfixOWL import *
   .. build-up an InfixOWL graph ..
   ruleStore,ruleGraph,network=SetupRuleStore(makeNetwork=True)
   #Reduce OWL-DL with negation into general logic programs
   NormalFormReduction(Individual.factoryGraph)
   network.setupDescriptionLogicProgramming(Individual.factoryGraph,
                                              addPDSemantics=False,
                                              derivedPreds=[ .. ],
                                              ignoreNegativeStratus=True)
   .. database is an RDF graph of all the relevant facts  ..
   network.calculateStratifiedModel(..database..)
```