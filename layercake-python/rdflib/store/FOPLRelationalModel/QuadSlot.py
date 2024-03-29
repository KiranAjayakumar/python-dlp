"""
Utility functions associated with RDF terms:

- normalizing (to 64 bit integers via half-md5-hashes)
- escaping literal's for SQL persistence
"""
from rdflib.BNode import BNode
from rdflib import RDF
from rdflib.Literal import Literal
from rdflib.URIRef import URIRef
from rdflib.term_utils import *
from rdflib.Graph import QuotedGraph
from rdflib.store.REGEXMatching import REGEXTerm

try:
    from hashlib import md5 as createDigest
except:
    from md5 import new as createDigest

Any = None

SUBJECT    = 0
PREDICATE  = 1
OBJECT     = 2
CONTEXT    = 3

DATATYPE_INDEX = CONTEXT + 1
LANGUAGE_INDEX = CONTEXT + 2

SlotPrefixes = {
     SUBJECT   : 'subject',
     PREDICATE : 'predicate',
     OBJECT    : 'object',
     CONTEXT   : 'context',
     DATATYPE_INDEX : 'dataType',
     LANGUAGE_INDEX : 'language'
}

POSITION_LIST = [SUBJECT,PREDICATE,OBJECT,CONTEXT]

def EscapeQuotes(qstr):
    """
    Ported from Ft.Lib.DbUtil
    """
    if qstr is None:
        return ''
    tmp = qstr.replace("\\","\\\\")
    tmp = tmp.replace("'", "\\'")
    tmp = tmp.replace('"', '\\"')
    return tmp

def dereferenceQuad(index,quad):
    assert index <= LANGUAGE_INDEX, "Invalid Quad Index"
    if index == DATATYPE_INDEX:
        return isinstance(quad[OBJECT],Literal) and quad[OBJECT].datatype or None
    elif index == LANGUAGE_INDEX:
        return isinstance(quad[OBJECT],Literal) and quad[OBJECT].language or None
    else:
        return quad[index]

def genQuadSlots(quads, useSignedInts=False):
    return [QuadSlot(index, quads[index], useSignedInts)
            for index in POSITION_LIST]

def makeMD5Digest(value):
    return createDigest(
            isinstance(value, unicode) and value.encode('utf-8')
            or value).hexdigest()

def normalizeValue(value, termType, useSignedInts=False):
    if value is None:
        value = u'http://www.w3.org/2002/07/owl#NothingU'
    else:
        value = (isinstance(value,Graph) and value.identifier or str(value)) + termType
    unsigned_hash = int(makeMD5Digest(value)[:16], 16)

    if useSignedInts:
        return makeSigned(unsigned_hash)
    else:
        return unsigned_hash

bigint_signed_max = 2**63
def makeSigned(bigint):
  if bigint > bigint_signed_max:
    return bigint_signed_max - bigint
  else:
    return bigint

def normalizeNode(node, useSignedInts=False):
    return normalizeValue(node, term2Letter(node), useSignedInts)

class QuadSlot(object):
    def __repr__(self):
        #NOTE: http://docs.python.org/ref/customization.html
        return "QuadSlot(%s,%s,%s)"%(SlotPrefixes[self.position],self.term,self.md5Int)

    def __init__(self, position, term, useSignedInts=False):
        assert position in POSITION_LIST, "Unknown quad position: %s"%position
        self.position = position
        self.term = term
        self.termType = term2Letter(term)
        self.useSignedInts = useSignedInts
        self.md5Int = normalizeValue(term, term2Letter(term), useSignedInts)

    def EscapeQuotes(self,qstr):
        """
        Ported from Ft.Lib.DbUtil
        """
        if qstr is None:
            return ''
        tmp = qstr.replace("\\","\\\\")
        tmp = tmp.replace("'", "\\'")
        tmp = tmp.replace('"', '\\"')
        return tmp

    def normalizeTerm(self):
        if isinstance(self.term,(QuotedGraph,Graph)):
            return self.term.identifier.encode('utf-8')
        elif isinstance(self.term,Literal):
            return self.EscapeQuotes(self.term).encode('utf-8')
        elif self.term is None or isinstance(self.term,(list,REGEXTerm)):
            return self.term
        else:
            return self.term.encode('utf-8')
        
    def getDatatypeQuadSlot(self):
        if self.termType == 'L' and self.term.datatype:
            return self.__class__(SUBJECT, self.term.datatype,
                                  self.useSignedInts)
        return None
