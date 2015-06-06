# Genealogy of FOL and LP #

A diagram summarizing the genealogy of First-order Logic (FOL), Description Logic (DL), and Logic Programming (LP) as a basis for (an) [open-source](http://code.google.com/p/python-dlp/wiki/FuXi), [enterprise-scale](http://reports-archive.adm.cs.cmu.edu/anon/1995/CMU-CS-95-113.pdf) [EvaluationSemantics4RETE](EvaluationSemantics4RETE.md) which outperforms tableau-based algorithms and implements the restricted intersection of Description Logics ([OWL-DL](http://www.w3.org/TR/owl-ref/#OWLDL) primarily) and Horn Logic ([RIF Basic Logic Dialect](http://www.w3.org/2005/rules/wg/wiki/Core/Positive_Conditions) @@WORKINPROGRESS): DescriptionLogicPrograms

The diagram is also [available](http://python-dlp.googlecode.com/files/KR-Geneology.svg) in its original SVG format

## Notes ##

Cardinality (see: [owl:cardinality](http://www.w3.org/TR/owl-semantics/rdfs.html#owl_cardinality_rdf)) and Disjoint semantics (see: [DisjointClasses(d1 … dn)](http://www.w3.org/TR/owl-semantics/direct.html#owl_disjointWith_semantics)) cannot be expressed in DLP!:

> "These constructors cannot, in general, be mapped into def-Horn.
> The case of negation is obvious as negation is not allowed in either
> the head or body of a def-Horn rule. As can be seen in Figure 4,
> cardinality restrictions correspond to assertions of variable equality
> and inequality in FOL, and this is again outside of the def-Horn
> framework."

[![](http://python-dlp.googlecode.com/files/MT-KR-Geneology.png)](http://www.cs.man.ac.uk/~horrocks/Publications/download/2003/p117-grosof.pdf)