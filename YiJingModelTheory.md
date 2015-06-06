

# Introduction #

The [ontology](http://metacognition.info/owl/yijing.owl) documents a set of first-order constants interpreted as elements of a set of primordial forces defined by axioms on the (Zhou Yi) symbols which are written characters with a structural form that 'illustrate' the forces underlying all natural phenomena ( as purported and described by the authors of the text ).

![http://metacognition.info/images/yijing-conceptualization1.png](http://metacognition.info/images/yijing-conceptualization1.png)
![http://metacognition.info/images/yijing-conceptualization2.png](http://metacognition.info/images/yijing-conceptualization2.png)
![http://metacognition.info/images/yijing-conceptualization3.png](http://metacognition.info/images/yijing-conceptualization3.png)

## Example ##

Individual resource 'heaven'

![http://metacognition.info/images/HeavenGua.jpg](http://metacognition.info/images/HeavenGua.jpg)

## Rules ##

Accompanying rules in the [RIF BLD presentation syntax](http://www.w3.org/TR/rif-bld/#Direct_Specification_of_RIF-BLD_Presentation_Syntax)

```
Forall ?GUA ?INVERSE ?YAO ( 
    sixthLine(?INVERSE ?YAO) :- And( inverse(?GUA ?INVERSE) firstLine(?GUA ?YAO) ) 
)
Forall ?GUA ?INVERSE ?YAO ( 
    fifthLine(?INVERSE ?YAO) :- And( inverse(?GUA ?INVERSE) secondLine(?GUA ?YAO) ) 
)
Forall ?GUA ?INVERSE ?YAO ( 
    fourthLine(?INVERSE ?YAO) :- And( inverse(?GUA ?INVERSE) thirdLine(?GUA ?YAO) ) 
)
Forall ?GUA ?INVERSE ?YAO ( 
    thirdLine(?INVERSE ?YAO) :- And( inverse(?GUA ?INVERSE) fourthLine(?GUA ?YAO) ) 
)
Forall ?GUA ?INVERSE ?YAO ( 
    secondLine(?INVERSE ?YAO) :- And( inverse(?GUA ?INVERSE) fifthLine(?GUA ?YAO) ) 
)
Forall ?GUA ?INVERSE ?YAO ( 
    firstLine(?INVERSE ?YAO) :- And( inverse(?GUA ?INVERSE) sixthLine(?GUA ?YAO) ) 
)
Forall ?GUA ?OTHER ( 
    inverse(?OTHER ?GUA) :- inverse(?GUA ?OTHER) 
)
Forall ?UPPER ?LOWER ?GUA ?GUA2 ?GUA1 ( 
    NonInvertibleGua(?GUA2) :- And( lowerPrimaryGua(?GUA1 ?LOWER) 
                                    upperPrimaryGua(?GUA1 ?UPPER) 
                                    inverse(?GUA1 ?GUA2) lowerPrimaryGua(?GUA2 ?LOWER) 
                                    upperPrimaryGua(?GUA2 ?UPPER) ) 
)
Forall ?GUA ( 
    lowerPrimaryGua(?GUA huang:Heaven) :- And( firstLine(?GUA Yang) secondLine(?GUA Yang) thirdLine(?GUA Yang) ) 
)
Forall ?GUA ( 
    lowerPrimaryGua(?GUA huang:Earth) :- And( firstLine(?GUA Yin) secondLine(?GUA Yin) thirdLine(?GUA Yin) ) 
)
Forall ?GUA ( 
    lowerPrimaryGua(?GUA huang:Water) :- And( firstLine(?GUA Yin) secondLine(?GUA Yang) thirdLine(?GUA Yin) ) 
)
Forall ?GUA ( 
    lowerPrimaryGua(?GUA huang:Wind) :- And( firstLine(?GUA Yin) secondLine(?GUA Yang) thirdLine(?GUA Yang) ) 
)
Forall ?GUA ( 
    lowerPrimaryGua(?GUA huang:Thunder) :- And( firstLine(?GUA Yang) secondLine(?GUA Yin) thirdLine(?GUA Yin) ) 
)
Forall ?GUA ( 
    lowerPrimaryGua(?GUA huang:Fire) :- And( firstLine(?GUA Yang) secondLine(?GUA Yin) thirdLine(?GUA Yang) ) 
)
Forall ?GUA ( 
    lowerPrimaryGua(?GUA huang:Lake) :- And( firstLine(?GUA Yang) secondLine(?GUA Yang) thirdLine(?GUA Yin) ) 
)
Forall ?GUA ( 
    lowerPrimaryGua(?GUA huang:Mountain) :- And( firstLine(?GUA Yin) secondLine(?GUA Yin) thirdLine(?GUA Yang) ) 
)
Forall ?GUA ( 
    upperPrimaryGua(?GUA huang:Heaven) :- And( fourthLine(?GUA Yang) fifthLine(?GUA Yang) sixthLine(?GUA Yang) ) 
)
Forall ?GUA ( 
    upperPrimaryGua(?GUA huang:Mountain) :- And( fourthLine(?GUA Yin) fifthLine(?GUA Yin) sixthLine(?GUA Yang) ) 
)
Forall ?GUA ( 
    upperPrimaryGua(?GUA huang:Earth) :- And( fourthLine(?GUA Yin) fifthLine(?GUA Yin) sixthLine(?GUA Yin) ) 
)
Forall ?GUA ( 
    upperPrimaryGua(?GUA huang:Water) :- And( fourthLine(?GUA Yin) fifthLine(?GUA Yang) sixthLine(?GUA Yin) ) 
)
Forall ?GUA ( 
    upperPrimaryGua(?GUA huang:Wind) :- And( fourthLine(?GUA Yin) fifthLine(?GUA Yang) sixthLine(?GUA Yang) ) 
)
Forall ?GUA ( 
    upperPrimaryGua(?GUA huang:Thunder) :- And( fourthLine(?GUA Yang) fifthLine(?GUA Yin) sixthLine(?GUA Yin) ) 
)
Forall ?GUA ( 
    upperPrimaryGua(?GUA huang:Fire) :- And( fourthLine(?GUA Yang) fifthLine(?GUA Yin) sixthLine(?GUA Yang) ) 
)
Forall ?GUA ( 
    upperPrimaryGua(?GUA huang:Lake) :- And( fourthLine(?GUA Yang) fifthLine(?GUA Yang) sixthLine(?GUA Yin) ) 
)
```

## Summary of Classes (in Manchester OWL) ##

```
Class: NonInvertibleGua 
    ## Primitive Type (Vertically symmetric gua) ##
    SubClassOf: Hexagram / gua
Class: NaturalPhenomenon 
    ## Primitive Type (Natural phenomenon) ##
    The fundamental natural phenomena signified by the images / signs in the YiJing
    SubClassOf: snap:RealizableEntity
Class: InvertibleGua 
    ## Primitive Type (Paired gua) ##
    SubClassOf: ( 'inverse gua' SOME ( NOT Vertically symmetric gua ) )
                Hexagram / gua . 
    DisjointWith Vertically symmetric gua

Class: PrimaryEnergySymbol 
    ## Primitive Type (Symbol for Primary energy) ##
    SubClassOf: Symbol
Class: ChangeSymbol 
    ## Primitive Type (Symbol) ##
    The images set forth by the sages (FuXi and King Wen) that signify natural phenomena
    SubClassOf: ( obo:IAO_0000136 SOME Natural phenomenon )
                obo:IAO_0000030
Class: PrimaryGua 
    ## Primitive Type (Trigram) ##
    SubClassOf: ( foaf:maker VALUE dbpedia:Fu_X> )
                Symbol
Class: yijing:AccomplishedGua 
    ## A Defined Class (Hexagram / gua) ##
    SubClassOf: ( 'King Wen order' SOME xsd:integer )
                Symbol
                ( foaf:maker VALUE dbpedia:King_Wen_of_Zhou> )
                ( ( lowerPrimaryGua SOME Trigram ) AND 
                  ( upperPrimaryGua SOME Trigram ) ) . 
    EquivalentTo: ( ( firstLine SOME Symbol for Primary energy ) AND 
                            ( secondLine SOME Symbol for Primary energy ) AND 
                            ( thirdLine SOME Symbol for Primary energy ) AND 
                            ( fourthLine SOME Symbol for Primary energy ) AND 
                            ( fifthLine SOME Symbol for Primary energy ) AND 
                            ( sixthLine SOME Symbol for Primary energy ) )
```

# Heaven #

See: [乾](http://en.wiktionary.org/wiki/%E4%B9%BE)

# Earth #

See: [坤](http://en.wiktionary.org/wiki/%E5%9D%A4)

# Water #

See: [坎](http://en.wiktionary.org/wiki/%E5%9D%8E)

# Fire #

See: [離](http://en.wiktionary.org/wiki/%E9%9B%A2)

# Wind #

See: [巽](http://en.wiktionary.org/wiki/%E5%B7%BD)

# Mountain #

See: [艮](http://en.wiktionary.org/wiki/%E8%89%AE)

# Lake #

See: [兌](http://en.wiktionary.org/wiki/%E5%85%8C)

# Thunder #

See: [震](http://en.wiktionary.org/wiki/%E9%9C%87)