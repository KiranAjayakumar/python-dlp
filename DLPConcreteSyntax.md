# Introduction #

#[KRGeneology](KRGeneology.md) covers the semantics and 'abstract' syntax, this covers a #[BisonGen](http://copia.ogbuji.net/blog/2005-04-27/Of_BisonGe) -powered concrete syntax to #use in addition to Notation 3:

## Concrete (non-XML) EBNF for DLP (via subset of RIF BLD: Positive Conditions) ##
```
  CONDITION   ::= CONJUNCTION | DISJUNCTION | EXISTENTIAL | ATOMIC
  CONJUNCTION ::= 'And' '(' CONDITION* ')'
  DISJUNCTION ::= 'Or' '(' CONDITION* ')'
  EXISTENTIAL ::= 'Exists' Var+ '(' CONDITION ')'
  ATOMIC      ::= Uniterm
  Uniterm     ::= Const '(' TERM* ')'
  TERM        ::= Const | Var | Uniterm
  Const       ::= CONSTNAME | '"'CONSTNAME'"''^^'TYPENAME
  Var         ::= '?'VARNAME

  Ruleset  ::= RULE*
  RULE     ::= 'Forall' Var* CLAUSE
  CLAUSE   ::= Implies | ATOMIC
  Implies  ::= ATOMIC ':-' CONDITION
```

We can introduce Curies, RDF Literals, and IRI's into CONSTNAME:

```
CONSTNAME ::= CURIE | '<' IRI '>' | RDFLiteral
```
