from __future__ import generators
from rdflib import BNode, OWL, RDF, RDFS, plugin
from rdflib.store import Store,VALID_STORE, CORRUPTED_STORE, NO_STORE, UNKNOWN
from rdflib.Literal import Literal, XSDToPython
from pprint import pprint
import sys
from rdflib.term_utils import *
from rdflib.Graph import QuotedGraph
from rdflib.store.REGEXMatching import REGEXTerm, NATIVE_REGEX, PYTHON_REGEX
from rdflib.store.AbstractSQLStore import *
from rdflib.sparql.sql.RdfSqlBuilder import DEFAULT_OPT_FLAGS
from rdflib.sparql.sql.DatabaseStats import LoadCachedStats, GetDatabaseStats
from FOPLRelationalModel.RelationalHash import IdentifierHash, LiteralHash, RelationalHash, GarbageCollectionQUERY
from FOPLRelationalModel.BinaryRelationPartition import *
from FOPLRelationalModel.QuadSlot import *
import cPickle, time, datetime

try:
    from hashlib import sha1 as createDigest
except:
    from sha import new as createDigest

def createSHADigest(value):
    return createDigest(
            value.encode('utf-8') if isinstance(value, unicode) else value).hexdigest()

Any = None

class TimeStamp(object):
  def __init__(self):
    self.start = datetime.datetime.now()
    self.checkpoint = self.start

  def delta(self):
    print >> sys.stderr, 'LAST DELTA:', datetime.datetime.now() - self.checkpoint
    self.checkpoint = datetime.datetime.now()

  def elapsed(self):
    print >> sys.stderr, 'ELAPSED:', datetime.datetime.now() - self.start
    self.start = datetime.datetime.now()
    self.checkpoint = self.start

def ParseConfigurationString(config_string):
    """
    Parses a configuration string in the form:
    key1=val1,key2=val2,key3=val3,...
    The following configuration keys are expected (not all are required):
    user
    password
    db
    host
    port (optional - defaults to 3306)
    """
    kvDict = dict([(part.split('=')[0],part.split('=')[-1]) for part in config_string.split(',')])
    for requiredKey in ['user','db','host']:
        assert requiredKey in kvDict
    if 'port' not in kvDict:
        kvDict['port']=3306
    if 'password' not in kvDict:
        kvDict['password']=''
    return kvDict

def createTerm(termString,termType,store,objLanguage=None,objDatatype=None):
    if termType == 'L':
        cache = store.literalCache.get((termString,objLanguage,objDatatype))
        if cache is not None:
            #store.cacheHits += 1
            return cache
        else:
            #store.cacheMisses += 1
            rt = Literal(termString,objLanguage,objDatatype)
            store.literalCache[((termString,objLanguage,objDatatype))] = rt
            return rt
    elif termType=='F':
        cache = store.otherCache.get((termType,termString))
        if cache is not None:
            #store.cacheHits += 1
            return cache
        else:
            #store.cacheMisses += 1
            rt = QuotedGraph(store,URIRef(termString))
            store.otherCache[(termType,termString)] = rt
            return rt
    elif termType == 'B':
        cache = store.bnodeCache.get((termString))
        if cache is not None:
            #store.cacheHits += 1
            return cache
        else:
            #store.cacheMisses += 1
            rt = TERM_INSTANCIATION_DICT[termType](termString)
            store.bnodeCache[(termString)] = rt
            return rt
    elif termType =='U':
        cache = store.uriCache.get((termString))
        if cache is not None:
            #store.cacheHits += 1
            return cache
        else:
            #store.cacheMisses += 1
            rt = URIRef(termString)
            store.uriCache[(termString)] = rt
            return rt
    else:
        cache = store.otherCache.get((termType,termString))
        if cache is not None:
            #store.cacheHits += 1
            return cache
        else:
            #store.cacheMisses += 1
            rt = TERM_INSTANCIATION_DICT[termType](termString)
            store.otherCache[(termType,termString)] = rt
            return rt

def extractTriple(tupleRt,store,hardCodedContext=None):
    subject,sTerm,predicate,pTerm,obj,oTerm,rtContext,cTerm,objDatatype,objLanguage = tupleRt
    context = rtContext is not None and rtContext or hardCodedContext.identifier

    s=createTerm(subject,sTerm,store)
    p=createTerm(predicate,pTerm,store)
    o=createTerm(obj,oTerm,store,objLanguage,objDatatype)

    graphKlass, idKlass = constructGraph(cTerm)
    return s,p,o,(graphKlass,idKlass,context)

        
class _variable_cluster(object):
  """
  A `_variable_cluster` instance represents the mapping from a single triple
  pattern to the appropriate SQL components necessary for forming a SQL
  query that incorporates the triple pattern.

  A triple pattern can cover more than one variable, and each instance of
  this class maintains information about all the variables that are present
  in the corresponding triple pattern.  For each variable in a triple
  pattern, that variable is either newly visible in this triple pattern or
  was visible in a previous triple pattern (in a sequence of triple
  patterns).  Also, each variable may correspond to either a Literal or a
  non-Literal.  Managing the consequences of these requirements and the
  corresponding SQL artifacts are the most important aspects of this class.
  """
  def __init__(self, component_name, db_prefix,
               subject, predicate, object_, context):
    '''
    Initialize a `_variable_cluster` instance based upon the syntactic parts
    of the triple pattern and additional information linking the triple
    pattern to its query context.

    Parameters:

    - `component_name`: A name prefix used to construct the SQL phrases
       produced by this instance.  This prefix must be unique to the set of
       `_variable_cluster` instances corresponding to a complete SPARQL
       query.  These prefixes might be of the form "component_N" for some N,
       and are used to identify which SQL columns correspond to which
       SPARQL variable.
    - `db_prefix`: A name prefix used to fully qualify SQL table references
       in the current DB.
    - `subject`, `predicate`, `object_`, `context`: The subject, predicate,
       object, and the name of the graph for the current triple pattern,
       respectively.  Each of these will be RDFLib `node` objects, and at
       least one should be an RDFLib `variable`.
    '''

    self.component_name = component_name
    self.db_prefix = db_prefix
    self.subject = subject
    self.subject_name = 'subject'
    self.predicate = predicate
    self.object_ = object_
    self.object_name = 'object'
    self.context = context

    # If the predicate of this triple pattern is `rdf:type`, then the SQL
    # table uses 'member' for the subject and 'class' for the object.
    if RDF.type == self.predicate:
      self.subject_name = 'member'
      self.object_name = 'class'

    self.subset_name = None
    '''String indicating the base name of the table or view containing RDF
    statements that this triple pattern will reference.'''

    self.object_may_be_literal = False
    '''This will be True if and only if it is determined that the object of
    the represented triple pattern is a variable that could resolve to a
    literal.'''

    self.index = None
    '''The manager of this object must maintain a list of all
    `_variable_cluster` instances that contain variables.  Once the manager
    processes this `_variable_cluster` in context, this variable contains
    the index of this object within that list.'''

    self.non_object_columns = []
    '''SQL column phrases that are not relevant to the object of the triple
    pattern that this object represents.'''
    self.object_columns = []
    '''SQL column phrases that are relevant to the object of the triple
    pattern that this object represents.'''
    self.join_fragment = None
    '''SQL phrase that defines the table to use for the triple pattern that
    this object represents in the "from" clause of the full SQL query.'''
    self.where_fragments = []
    '''SQL condition phrases that will be conjunctively joined together in
    the "where" clause of the full SQL query.'''

    self.definitions = {}
    '''Map from variable name managed by this object to the full column
    reference that represents that variable.'''
    self.variable_columns = []
    '''List of 4-tuples consisting of the names of the variables managed by
    this instance, the column reference that represents the variable, a flag
    that is True if and only if the variable corresponds to the object of
    the triple pattern, and a reference to this object.'''

    self.substitutions = []
    '''List of all the static data that must be substituted into the query
    string by the query mechanism, in the proper order based upon
    placeholders in the query.'''

  def determine_initial_subset(self, store):
    '''
    Determine the most specific RDF statement subset that this triple
    pattern can use, based on the types of the parts of the statement and
    the information provided about properties provided by the SQL store (in
    the `store` parameter).  This is crucial to optimization, because
    specific subsets (SQL tables such as the 'relations' table) are very
    efficient but general subsets (SQL views such as the
    'URI_or_literal_objects' view) are very inefficient.

    :Parameters:
    - `store`: RDFLib SQL store containing the target data.
    '''

    if isinstance(self.subject, Literal):
      raise ValueError(
        'A subject cannot be a literal.')

    if isinstance(self.predicate, URIRef):
      # This is a good case, performance-wise, as we can be much more
      # specific about the subset that we use when we have a non-variable
      # predicate.
      if RDF.type == self.predicate:
        # TODO: find a constant for these somewhere
        self.subset_name = "associativeBox"
      elif isinstance(self.object_, Literal):
        self.subset_name = "literalProperties"
      elif isinstance(self.object_, Variable):
        if self.predicate in store.literal_properties:
          self.subset_name = "literalProperties"
        elif self.predicate in store.resource_properties:
          self.subset_name = "relations"
        else:
          self.subset_name = "URI_or_literal_object"
      else:
        self.subset_name = "relations"

    elif isinstance(self.predicate, Variable):
      if isinstance(self.object_, Literal):
        self.subset_name = "literalProperties"
      elif not isinstance(self.object_, Variable):
        self.subset_name = "relation_or_associativeBox"
      else:
        self.subset_name = "all"
      
    else:
      raise ValueError(
        'Each predicate must either a URIRef or a Variable.')

    # Once we know the initial subset to use, we can construct the join
    # fragment that this object will provide.
    self.join_fragment = (self.db_prefix + '_' + self.subset_name +
      ' as %s_statements' % (self.component_name,))

  def note_object_is_named(self):
    '''
    Note new information indicating that the object variable cannot be a
    literal.  In a list of triple patterns, a later triple pattern may refer
    to the same variable as a previous triple pattern, and the later
    variable reference may further constrain the potential type of the
    initial instance of the variable (in particular, that the variable
    cannot be a literal), in which case the manager of the later variable
    reference should call this method on the manager of the initial variable
    reference.
    '''

    if self.object_may_be_literal:
      self.object_may_be_literal = False

      if 'URI_or_literal_object' == self.subset_name:
        self.subset_name = 'relations'
        self.join_fragment = (self.db_prefix + '_' + self.subset_name +
          ' as %s_statements' % (self.component_name,))

      column_name = self.component_name + '_object'
      self.object_columns = ['%s_statements.%s as %s' %
        (self.component_name, self.object_name, column_name)]

  def get_SQL_clause(self):
    return '   ' + self.join_fragment

  def process_variable(self, variable, variable_bindings, role):
    '''
    Set up the state for managing one variable for the current triple
    pattern.  This method does not currently support object variables, as
    they present a sufficiently different case that they should be handled
    manually.

    :Parameters:
    - `variable`: The variable to manage.
    - `variable_bindings`: A map of previously existing variables.
    - `role`: String indicating the role that this variable plays in the
       managed triple pattern.  This should be one of 'subject', 'predicate',
       or 'context'.

    Returns a list containing the new variable name and manager tuple, or an
    empty list if this is a previously seen variable.

    This is a private method.
    '''

    if 'object' == role:
      raise ValueError(
        '`process_variable` cannot current handle object variables.  ' +
        'Please deal with them manually.')

    variable_name = str(variable)

    if 'subject' == role:
      statements_column = self.subject_name
    elif 'object' == role:
      statements_column = self.object_name
    else:
      statements_column = role

    if variable_name in variable_bindings:
      # Since the variable name was already seen, link the current occurance
      # of the variable to the initial occurance using a predicate in the
      # SQL 'where' phrase.

      initial_reference = variable_bindings[variable_name]

      self.where_fragments.append('%s_statements.%s = %s' % (
        self.component_name, statements_column,
        initial_reference.definitions[variable_name]))

      # Also, if the initial occurance of the variable was in the object
      # role and this occurance is not in the object role, then the variable
      # cannot refer to a literal, so communicate this to the manager of the
      # initial occurance.
      if initial_reference.definitions[variable_name].split(
          '.')[1] == 'object' and 'object' != role:
        initial_reference.note_object_is_named()

      return []
    else:
      # Note that this is the first occurance of the variable; this includes
      # adding appropriate SQL phrases that bind to this variable.

      defining_reference = self.component_name + "_statements.%s" % (
                                                   statements_column,)
      self.definitions[variable_name] = defining_reference
      column_name = self.component_name + '_' + role
      self.non_object_columns.append('%s as %s' % (
        defining_reference, column_name))
      self.non_object_columns.append('%s_term as %s_term' % (
        defining_reference, column_name))

      self.variable_columns.append((variable_name, column_name, False, self))
      return [(variable_name, self)]

  def make_SQL_components(self, variable_bindings, variable_clusters,
                          useSignedInts):
    '''
    Process all the terms from the managed RDF triple pattern in the
    appropriate context.

    :Parameters:
    - `variable_bindings`: Map of existing variable bindings.  It is crucial
       that the caller updates this map after each triple pattern is
       processed.
    - `variable_clusters`: List of existing `_variable_cluster` objects that
       manage variables.

    Returns a list of 2-tuples consisting of newly managed variables and a
    reference to this object (which may be empty if there are no new
    variables in this triple pattern).
    '''

    if self.index is not None:
      raise ValueError('`make_SQL_components` should only be run once per '
        + '`_variable_cluster` instance.')

    self.index = len(variable_clusters)
    local_binding_list = []

    # First, process subject, predicate, and context from the managed triple
    # pattern, as they are all similar cases in that they cannot be
    # literals.

    if isinstance(self.subject, Variable):
      local_binding_list.extend(
        self.process_variable(self.subject, variable_bindings, 'subject'))
    elif not isinstance(self.subject, Literal):
      self.where_fragments.append('%s_statements.%s = %%s' %
        (self.component_name, self.subject_name,))
      self.substitutions.append(normalizeNode(self.subject, useSignedInts))
    else:
      raise ValueError('The subject of a triple pattern cannot be a literal.')

    if isinstance(self.predicate, Variable):
      local_binding_list.extend(
        self.process_variable(self.predicate, variable_bindings, 'predicate'))
    elif RDF.type != self.predicate:
      self.where_fragments.append('%s_statements.predicate = %%s' %
        (self.component_name,))
      self.substitutions.append(normalizeNode(self.predicate, useSignedInts))

    if isinstance(self.context, Variable):
      local_binding_list.extend(
        self.process_variable(self.context, variable_bindings, 'context'))
    elif isinstance(self.context, URIRef) or isinstance(self.context, BNode):
      self.where_fragments.append('%s_statements.context = %%s' %
        (self.component_name,))
      self.substitutions.append(normalizeNode(self.context, useSignedInts))

    # Process the object of the triple pattern manually, as it could be a
    # literal and so requires special handling to query properly.

    if isinstance(self.object_, Variable):
      variable_name = str(self.object_)

      if variable_name in variable_bindings:
        initial_reference = variable_bindings[variable_name]

        self.where_fragments.append('%s_statements.%s = %s' % (
          self.component_name, self.object_name,
          initial_reference.definitions[variable_name]))

        if 'URI_or_literal_object' == self.subset_name:
          self.subset_name = 'relations'
          self.join_fragment = (
            self.db_prefix + '_' + self.subset_name + ' as %s_statements' %
              (self.component_name,))
      else:
        defining_reference = self.component_name + "_statements.%s" % (
                                                     self.object_name,)
        self.definitions[variable_name] = defining_reference

        column_name = self.component_name + '_object'

        if 'URI_or_literal_object' == self.subset_name:
          self.object_may_be_literal = True

        if 'literalProperties' != self.subset_name:
          self.non_object_columns.append('%s_statements.%s_term as %s_term'
            % (self.component_name, self.object_name, column_name))
        else:
          self.non_object_columns.append("'L' as %s_term" % (column_name,))

        self.object_columns.append('%s as %s' %
          (defining_reference, column_name))
        if not('relations' == self.subset_name or
               'associativeBox' == self.subset_name):
          self.object_columns.append('%s_statements.data_type as %s_datatype' %
            (self.component_name, column_name))
          self.object_columns.append('%s_statements.language as %s_language' %
            (self.component_name, column_name))

        self.variable_columns.append((variable_name, column_name, True, self))
        local_binding_list.append((variable_name, self))
    else:
      self.where_fragments.append('%s_statements.%s = %%s' %
        (self.component_name, self.object_name,))
      self.substitutions.append(normalizeNode(self.object_, useSignedInts))

    return local_binding_list

class SQL(Store):
    """
    Abstract SQL implementation of the FOPL Relational Model as an rdflib
    Store.
    """
    context_aware = True
    formula_aware = True
    transaction_aware = True
    regex_matching = NATIVE_REGEX
    batch_unification = True
    def __init__(self, identifier=None, configuration=None,
                 debug=False, engine="ENGINE=InnoDB",
                 useSignedInts=False, hashFieldType='BIGINT unsigned',
                 declareEnums=False, perfLog=False,
                 optimizations=None,
                 scanForDatatypes=False):
        self.dataTypes={}
        self.scanForDatatypes=scanForDatatypes
        self.optimizations=optimizations
        self.debug = debug
        if debug:
          self.timestamp = TimeStamp()
                                
        #BE: performance logging
        self.perfLog = perfLog
        if self.perfLog:
            self.resetPerfLog()    

        self.identifier = identifier and identifier or 'hardcoded'
        
        #Use only the first 10 bytes of the digest
        self._internedId = INTERNED_PREFIX + createSHADigest(self.identifier)[:10]

        self.engine = engine
        self.showDBsCommand = 'SHOW DATABASES'
        self.findTablesCommand = "SHOW TABLES LIKE '%s'"
        self.findViewsCommand = "SHOW TABLES LIKE '%s'"
        self.defaultDB = 'mysql'
        self.select_modifier = 'straight_join' #BE: note this is MySQL specific syntax

        self.INDEX_NS_BINDS_TABLE = \
          'CREATE INDEX uri_index on %s_namespace_binds (uri(100))'

        #Setup FOPL RelationalModel objects
        self.useSignedInts = useSignedInts
        # TODO: derive this from `self.useSignedInts`?
        self.hashFieldType = hashFieldType
        self.idHash = IdentifierHash(self._internedId,
          self.useSignedInts, self.hashFieldType, self.engine, declareEnums)
        self.valueHash = LiteralHash(self._internedId,
          self.useSignedInts, self.hashFieldType, self.engine, declareEnums)
        self.binaryRelations = NamedBinaryRelations(
          self._internedId, self.idHash, self.valueHash,
          self.useSignedInts, self.hashFieldType, self.engine, declareEnums)
        self.literalProperties = NamedLiteralProperties(
          self._internedId, self.idHash, self.valueHash,
          self.useSignedInts, self.hashFieldType, self.engine, declareEnums)
        self.aboxAssertions = AssociativeBox(
          self._internedId, self.idHash, self.valueHash,
          self.useSignedInts, self.hashFieldType, self.engine, declareEnums)
                
        self.tables = [
                       self.binaryRelations,
                       self.literalProperties,
                       self.aboxAssertions,
                       self.idHash,
                       self.valueHash
                       ]
        self.createTables = [
                       self.idHash,
                       self.valueHash,
                       self.binaryRelations,
                       self.literalProperties,
                       self.aboxAssertions
                       ]
        self.hashes = [self.idHash,self.valueHash]
        self.partitions = [self.literalProperties,self.binaryRelations,self.aboxAssertions,]

        #This is a dictionary which caputures the relationships between 
        #the each view, it's prefix, the arguments to viewUnionSelectExpression
        #and the tables involved
        self.viewCreationDict={
            '_all'                       : (False,self.partitions),
            '_URI_or_literal_object'     : (False,[self.literalProperties,
                                                   self.binaryRelations]),
            '_relation_or_associativeBox': (True,[self.binaryRelations,
                                                  self.aboxAssertions]),
            '_all_objects'               : (False,self.hashes)                                               
        }

        #This parameter controls how exlusively the literal table is searched
        #If true, the Literal partition is searched *exclusively* if the object term
        #in a triple pattern is a Literal or a REGEXTerm.  Note, the latter case
        #prevents the matching of URIRef nodes as the objects of a triple in the store.
        #If the object term is a wildcard (None)
        #Then the Literal paritition is searched in addition to the others
        #If this parameter is false, the literal partition is searched regardless of what the object
        #of the triple pattern is
        self.STRONGLY_TYPED_TERMS = False
        self._db = None
        self.configuration = None
        if configuration is not None:
            self.open(configuration)


        self.cacheHits = 0
        self.cacheMisses = 0

        self.literalCache = {}
        self.uriCache = {}
        self.bnodeCache = {}
        self.otherCache = {}

        self.literal_properties = set()
        '''set of URIRefs of those RDF properties which are known to range
        over literals.'''
        self.resource_properties = set()
        '''set of URIRefs of those RDF properties which are known to range
        over resources.'''
        
        #update the two sets above with defaults
        self.literal_properties.update( OWL.literalProperties)
        self.literal_properties.update( RDF.literalProperties)
        self.literal_properties.update( RDFS.literalProperties)
        self.resource_properties.update(OWL.resourceProperties)
        self.resource_properties.update(RDF.resourceProperties)
        self.resource_properties.update(RDFS.resourceProperties)

        self.length = None

    def sparql_query(self,
                     queryString,
                     queryObj,
                     graph,
                     dataSetBase,
                     extensionFunctions,
                     initBindings={},
                     initNs={},
                     DEBUG=False):
        """
        The 'native' SPARQL implementation uses the various SPARQL-to-SQL methods
        """
        from rdflib.sparql.sql.RelationalAlgebra import TopEvaluate
        from rdflib.sparql.sql.RdfSqlBuilder import DEFAULT_OPT_FLAGS
        from rdflib.QueryResult import QueryResult
        opts = self.optimizations and self.optimizations or DEFAULT_OPT_FLAGS
        rt = TopEvaluate(queryObj,
                         graph,
                         initBindings,
                         DEBUG=DEBUG,
                         optimizations=opts,
                         dataSetBase=dataSetBase,
                         extensionFunctions=extensionFunctions)
        return plugin.get('SPARQLQueryResult',QueryResult)(rt)

    def scanProperties(self):
        """
        Via introspection, update the set of literal and resource properties
        using the assertions in the store
        """
        litTable   = self.literalProperties
        relTable   = self.binaryRelations
        idObjTable = self.idHash
        
        #@todo: perhaps these column names should not be hard-coded?
        idField = "id"
        lexField = "lexical"
        
        cursor = self._db.cursor()
        
        litProps = set()
        cursor.execute(""" 
            SELECT DISTINCT i.%s AS pred
            FROM %s t INNER JOIN %s i ON t.%s = i.%s;""" % 
            (lexField, litTable, idObjTable, litTable.columnNames[PREDICATE], idField))
        for (pred,) in cursor.fetchall():
            self.literal_properties.add(pred)
        
        resProps = set()
        cursor.execute(""" 
            SELECT DISTINCT i.%s AS pred
            FROM %s t INNER JOIN %s i ON t.%s = i.%s;""" % 
            (lexField, relTable, idObjTable, relTable.columnNames[PREDICATE], idField))
        for (pred,) in cursor.fetchall():
            self.resource_properties.add(pred)
            
    def resetPerfLog(self, clearCache=False): #BE: for performance logging
        self.mainQueryCount = 0
        self.mainQueryTime = 0
        self.rowPrepQueryCount = 0
        self.rowPrepQueryTime = 0
        self.mainQueries = []
        #TODO: clear the MySQL query cache to get more consistent results
        # RESET QUERY CACHE -- see http://dev.mysql.com/doc/refman/5.0/en/reset.html
        if clearCache:
            c=self._db.cursor()
            self.executeSQL(c, "RESET QUERY CACHE")
       
    def getPerfLog(self): #BE: for performance logging
        if self.perfLog:
            return dict(mainQueryCount=self.mainQueryCount,
                        mainQueryTime=self.mainQueryTime,
                        rowPrepQueryCount=self.rowPrepQueryCount,
                        rowPrepQueryTime=self.rowPrepQueryTime,
                        sqlQueries=self.mainQueries)
        return dict();

    def log_statement(self, statement):
        if self.debug:
            self.timestamp.delta()
            print >> sys.stderr, statement

            try:
                self.statement_log.write(statement + "\n")
            except Exception:
                pass

    def executeSQL(self,cursor,qStr,params=None,paramList=False):
        """
        Overridden in order to pass params seperate from query for the
        database to optimize.
        """
        #self._db.autocommit(False)
        self.log_statement(qStr)
        #return # XXX: Temporary!
        if params is None:
            cursor.execute(qStr)
        elif paramList:
            cursor.executemany(qStr,[tuple(item) for item in params])
        else:
            cursor.execute(qStr,tuple(params))

    def note_modified(self):
        """Indicate that the triples in this store have been modified.  This
        should be called after any operation that could add or remove
        triples in the store."""

        self.length = None

    def _dbState(self,db,configDict):
        c=db.cursor()
        self.log_statement(self.showDBsCommand)
        self.executeSQL(c, self.showDBsCommand)
        #FIXME This is a character set hack.  See: http://sourceforge.net/forum/forum.php?thread_id=1448424&forum_id=70461
        #self._db.charset = 'utf8'
        if (configDict['db'].encode('utf-8'),) in [
              tuple(item) for item in c.fetchall()]:
            for tn in self.tables:
                statement = self.findTablesCommand % (tn,) 
                self.log_statement(statement)
                self.executeSQL(c, statement)
                rt=c.fetchall()
                if not rt:
                    sys.stderr.write("table %s Doesn't exist\n" % (tn));
                    #The database exists, but one of the partitions doesn't exist
                    return CORRUPTED_STORE
            #Everything is there (the database and the partitions)
            return VALID_STORE
        #The database doesn't exist - nothing is there
        return NO_STORE
    
    def _createViews(self,cursor):
        """
        Helper function for creating views        
        """
        for suffix,(relations_only,tables) in self.viewCreationDict.items():
            query='create view %s%s as %s'%(self._internedId,
                                            suffix,
            ' union all '.join([t.viewUnionSelectExpression(relations_only) 
                                for t in tables]))
            if self.debug:
                print >> sys.stderr, "## Creating View ##\n",query
            self.executeSQL(cursor, query)

    def connect(user, passwd, db, port, host):
        raise NotImplementedError('SQL is an abstract base class.')

    #Database Management Methods
    def create(self, configuration, populate=True):
        self.configuration = configuration
        configDict = ParseConfigurationString(configuration)
        test_db = self.connect(user=configDict['user'],
                               passwd=configDict['password'],
                               db=self.defaultDB,
                               port=configDict['port'],
                               host=configDict['host'])
        c=test_db.cursor()
        self.executeSQL(c, 'COMMIT')
        self.executeSQL(c, self.showDBsCommand)
        if not (configDict['db'].encode('utf-8'),) in [
                tuple(item) for item in c.fetchall()]:
            print >> sys.stderr, "creating %s (doesn't exist)"%(configDict['db'])
            self.executeSQL(c, "CREATE DATABASE %s" % (configDict['db'],))
        c.close()
        test_db.close()

        db = self.connect(user=configDict['user'],
                          passwd=configDict['password'],
                          db=configDict['db'],
                          port=configDict['port'],
                          host=configDict['host'])
        c=db.cursor()
        self.executeSQL(c, 'COMMIT')
        self.executeSQL(c, 'START TRANSACTION')
        self.executeSQL(c, CREATE_NS_BINDS_TABLE %
                             (self._internedId, self.engine))
        self.executeSQL(c, self.INDEX_NS_BINDS_TABLE % (self._internedId,))
        for kb in self.createTables:
            for statement in kb.createStatements():
                if self.debug:
                    print >> sys.stderr, "## Creating View ##\n",statement
                self.executeSQL(c, statement)

            if populate:
                for statement in kb.defaultStatements():
                    self.executeSQL(c, statement)
        self._createViews(c)
        self.executeSQL(c, 'COMMIT')
        c.close()
        self._db = db

    def applyIndices(self):
        c = self._db.cursor()
        # Do we need to do this (that is, the transaction)?!  Really?
        for kb in self.createTables:
            for statement in kb.indexingStatements():
                self.executeSQL(c, statement)

    def removeIndices(self):
        c = self._db.cursor()
        for kb in self.createTables:
            for statement in kb.removeIndexingStatements():
                self.executeSQL(c, statement)

    def applyForeignKeys(self):
        c = self._db.cursor()
        for kb in self.createTables:
            for statement in kb.foreignKeyStatements():
                self.executeSQL(c, statement)

    def removeForeignKeys(self):
        c = self._db.cursor()
        for kb in self.createTables:
            for statement in kb.removeForeignKeyStatements():
                self.executeSQL(c, statement)

    def open(self, configuration, create=False):
        """
        Opens the store specified by the configuration string. If
        create is True a store will be created if it does not already
        exist. If create is False and a store does not already exist
        an exception is raised. An exception is also raised if a store
        exists, but there is insufficient permissions to open the
        store.
        """
        if self._db is not None:
            self._db.close()
        self.configuration = configuration
        configDict = ParseConfigurationString(configuration)
        if create:
            self.create(configuration)
            self.applyIndices()
            self.applyForeignKeys()
        else:
            #This branch is needed for backward compatibility
            #which didn't use SQL views
            _db=self.connect(user=configDict['user'],
                             passwd=configDict['password'],
                             db=configDict['db'],
                             port=configDict['port'],
                             host=configDict['host'])
            if self._dbState(_db,configDict) == VALID_STORE:
                c=_db.cursor()
                self.executeSQL(c, 'COMMIT')
                self.executeSQL(c, 'START TRANSACTION')
                existingViews=[]
                #check which views already exist
                views=[]
                for suffix in self.viewCreationDict:
                    view = self._internedId+suffix
                    views.append(view)
                    self.executeSQL(c, self.findViewsCommand % (view,))
                    rt=c.fetchall()
                    if rt:
                        existingViews.append(view)
                c.close()
                
                if self.scanForDatatypes:
                    cursor=_db.cursor()
                    cursor.execute(""" 
                        SELECT DISTINCT i.id, i.lexical
                        FROM %s lp INNER JOIN 
                            %s i ON lp.data_type = i.id;""" %(self.literalProperties, 
                                                              self.idHash))
                    for (id,text) in cursor.fetchall():
                        self.dataTypes[id] = text
                    cursor.close()
                else:
                    self.dataTypes=dict([(normalizeNode(dType, 
                                                        self.useSignedInts),dType) 
                                                for dType in XSDToPython.keys()])
                    self.scanForDatatypes={}
                _db.close()
                if not existingViews:
                    #None of the views have been defined - so this is
                    #an old (but valid) store
                    #we need to create the missing views 
                    db = self.connect(user = configDict['user'],
                                      passwd = configDict['password'],
                                      db=configDict['db'],
                                      port=configDict['port'],
                                      host=configDict['host'])
                    c=db.cursor()
                    self.executeSQL(c, 'COMMIT')
                    self.executeSQL(c, 'START TRANSACTION')
                    self._createViews(c)
                    db.commit()
                    c.close()
                elif len(existingViews)!=len(views):
                    #Not all the views have been setup
                    return CORRUPTED_STORE                        
        try:
            port = int(configDict['port'])
        except:
            raise ArithmeticError('server port must be a valid integer')
        self._db = self.connect(user=configDict['user'],
                                passwd=configDict['password'],
                                db=configDict['db'],
                                port=port,
                                host=configDict['host'])
        c = self._db.cursor()
        self.executeSQL(c, 'COMMIT')
        #self._db.autocommit(False)
        
        #Manage triple pattern statistics
        self.stats = None
        statsFName = configDict.get('sparqlStatsFile')
        if statsFName:
            self.stats = LoadCachedStats(statsFName)
            if not self.stats:
                #Need to generate DB statistics for SPARQL
                self.stats = GetDatabaseStats(self)
                f = open(statsFName, 'w')
                cPickle.dump(version, f)
                cPickle.dump(self.stats, f)
                f.close()
        
        return self._dbState(self._db, configDict)

    def destroy(self, configuration):
        """
        FIXME: Add documentation
        """
        configDict = ParseConfigurationString(configuration)
        db = self.connect(user=configDict['user'],
                          passwd=configDict['password'],
                          db=configDict['db'],
                          port=configDict['port'],
                          host=configDict['host'])
        #db.autocommit(False)
        c=db.cursor()
        self.executeSQL(c, 'COMMIT')
        self.executeSQL(c, 'START TRANSACTION')

        for suffix in self.viewCreationDict:
            view = self._internedId+suffix
            try:
                self.executeSQL(c, 'DROP view %s' % (view,))
            except Exception, e:
                print >> sys.stderr, "unable to drop table: %s"%(view)
                print >> sys.stderr, e

        for tbl in self.tables + ["%s_namespace_binds"%self._internedId]:
            try:
                self.executeSQL(c, 'DROP table %s' % (tbl,))
                #print "dropped table: %s"%(tblsuffix%(self._internedId))
            except Exception, e:
                print >> sys.stderr, "unable to drop table: %s"%(tbl)
                print >> sys.stderr, e

        #Note, this only removes the associated tables for the closed world universe given by the identifier
        print >> sys.stderr, "Destroyed Close World Universe %s ( in SQL database %s)"%(self.identifier,configDict['db'])
        self.executeSQL(c, 'COMMIT')
        db.close()
        self.note_modified()

    #Transactional interfaces
    def commit(self):
        """ """
        self._db.commit()

    def rollback(self):
        """ """
        self._db.rollback()

    def gc(self):
        """
        Purges unreferenced identifiers / values - expensive
        """
        c=self._db.cursor()
        purgeQueries = GarbageCollectionQUERY(
                                               self.idHash,
                                               self.valueHash,
                                               self.binaryRelations,
                                               self.aboxAssertions,
                                               self.literalProperties)

        for q in purgeQueries:
            self.executeSQL(c,q)

    def get_table(self, triple):
        subject, predicate, obj = triple
        if predicate == RDF.type:
            kb = self.aboxAssertions
        elif isinstance(obj, Literal):
            kb = self.literalProperties
        else:
            kb = self.binaryRelations
        return kb

    def add(self, (subject, predicate, obj), context=None, quoted=False):
        """ Add a triple to the store of triples. """
        qSlots = genQuadSlots([subject, predicate, obj, context],
                              self.useSignedInts)
        kb = self.get_table((subject, predicate, obj))
        kb.insertRelations([qSlots])
        kb.flushInsertions(self._db)
        self.note_modified()

    def addN(self, quads):
        """
        Adds each item in the list of statements to a specific context. The quoted argument
        is interpreted by formula-aware stores to indicate this statement is quoted/hypothetical.
        Note that the default implementation is a redirect to add
        """
        for s,p,o,c in quads:
            assert c is not None, "Context associated with %s %s %s is None!"%(s,p,o)
            qSlots = genQuadSlots([s, p, o, c],
                                  self.useSignedInts)

            kb = self.get_table((s, p, o))
            kb.insertRelations([qSlots])

        for kb in self.partitions:
            if kb.pendingInsertions:
                kb.flushInsertions(self._db)
        self.note_modified()

    def remove(self, (subject, predicate, obj), context):
        """ Remove a triple from the store """
        targetBRPs = BinaryRelationPartitionCoverage((subject,predicate,obj,context),self.partitions)
        c=self._db.cursor()
        for brp in targetBRPs:
            query = "DELETE from %s WHERE "%(
                                          brp,
                                          #brp.generateHashIntersections()
                                        )
            whereClause,whereParameters = brp.generateWhereClause((subject,predicate,obj,context))
            self.executeSQL(c,query+whereClause,params=whereParameters)

        c.close()
        self.note_modified()

    def triples(self, (subject, predicate, obj), context=None):
        c=self._db.cursor()
        if context is None or isinstance(context.identifier,REGEXTerm):
            rt=PatternResolution((subject,predicate,obj,context),c,self.partitions,fetchall=False)
        else:
            #No need to order by triple (expensive), all result sets will be in the same context
            rt=PatternResolution((subject,predicate,obj,context),c,self.partitions,orderByTriple=False,fetchall=False)
        while rt:
            s,p,o,(graphKlass,idKlass,graphId) = extractTriple(rt,self,context)
            if context is None or isinstance(context.identifier,REGEXTerm):
                currentContext = graphKlass(self,idKlass(graphId))
            else:
                currentContext = context
            contexts = [currentContext]
            rt = next = c.fetchone()
            if context is None or isinstance(context.identifier,REGEXTerm):
                sameTriple = next and extractTriple(next,self,context)[:3] == (s,p,o)
                while sameTriple:
                    s2,p2,o2,(graphKlass,idKlass,graphId) = extractTriple(next,self,context)
                    c2 = graphKlass(self,idKlass(graphId))
                    contexts.append(c2)
                    rt = next = c.fetchone()
                    sameTriple = next and extractTriple(next,self,context)[:3] == (s,p,o)

            yield (s,p,o),(con for con in contexts)
        c.close()

    def triples_choices(self, (subject, predicate, object_),context=None):
        """
        A variant of triples that can take a list of terms instead of a single
        term in any slot.  Stores can implement this to optimize the response time
        from the import default 'fallback' implementation, which will iterate
        over each term in the list and dispatch to tripless
        """
        if isinstance(object_,list):
            assert not isinstance(subject,list), "object_ / subject are both lists"
            assert not isinstance(predicate,list), "object_ / predicate are both lists"
            if not object_:
                object_ = None
            for (s1, p1, o1), cg in self.triples((subject,predicate,object_),context):
                yield (s1, p1, o1), cg

        elif isinstance(subject,list):
            assert not isinstance(predicate,list), "subject / predicate are both lists"
            if not subject:
                subject = None
            for (s1, p1, o1), cg in self.triples((subject,predicate,object_),context):
                yield (s1, p1, o1), cg

        elif isinstance(predicate,list):
            assert not isinstance(subject,list), "predicate / subject are both lists"
            if not predicate:
                predicate = None
            for (s1, p1, o1), cg in self.triples((subject,predicate,object_),context):
                yield (s1, p1, o1), cg

    def get_summary(self):
        c=self._db.cursor()

        rtDict = {}
        countRows = "select count(*) from %s"
        countContexts = "select DISTINCT %s from %s"
        unionSelect = ' union '.join([countContexts%(part.columnNames[CONTEXT],str(part)) for part in self.partitions])
        self.executeSQL(c,unionSelect)
        ctxCount = len(c.fetchall())
        for part in self.partitions:
            self.executeSQL(c,countRows%part)
            rowCount = c.fetchone()[0]
            rtDict[str(part)]=rowCount
        return "<Parititioned SQL N3 Store: %s context(s), %s classification(s), %s property/value assertion(s), and %s other relation(s)>"%(
            ctxCount,
            rtDict[str(self.aboxAssertions)],
            rtDict[str(self.literalProperties)],
            rtDict[str(self.binaryRelations)],
        )

    def __len__(self, context=None):
        if context is None and self.length is not None:
          return self.length

        rows = []
        countRows = "select count(*) from %s"
        c=self._db.cursor()
        for part in self.partitions:
            if context is not None:
                whereClause,whereParams = part.generateWhereClause((None,None,None,context.identifier)) 
                self.executeSQL(c,countRows%part + " where " + whereClause,whereParams)
            else:
                self.executeSQL(c,countRows%part)
            rowCount = c.fetchone()[0]
            rows.append(rowCount)
        length = reduce(lambda x,y: x+y,rows)
        if context is None:
            self.length = length
        return length

    def contexts(self, triple=None):
        c=self._db.cursor()
        if triple:
            subject,predicate,obj = triple
        else:
            subject = predicate = obj = None
        contextQuery = "select distinct uris.lexical, uris.term_type from %s uris inner join %s facts on uris.id = facts.context and uris.term_type = facts.context_term"
        if not triple:
            _contexts = set()
            for part in self.partitions:
                self.executeSQL(c,contextQuery%(self.idHash,part))
                _contexts.update(c.fetchall())
            for ctxId,termType in _contexts:
                yield Graph(self,TERM_INSTANCIATION_DICT[termType](ctxId))
        else:
            rt=PatternResolution((subject,predicate,obj,None),
                                  c,
                                  self.partitions,
                                  fetchall=False,
                                  fetchContexts=True)
            fetchedGraphNames=[]
            while rt:
                contextId,cTerm = rt
                if contextId not in fetchedGraphNames:
                    graphKlass, idKlass = constructGraph(cTerm)
                    yield graphKlass(self,idKlass(contextId))
                    fetchedGraphNames.append(contextId)
                rt = c.fetchone()

    #Namespace persistence interface implementation
    def bind(self, prefix, namespace):
        """ """
        c=self._db.cursor()
        try:
            self.executeSQL(
                c,
                "INSERT INTO %s_namespace_binds VALUES ('%s', '%s')"%(
                self._internedId,
                prefix,
                namespace)
            )
        except:
            pass
        c.close()

    def prefix(self, namespace):
        """ """
        c=self._db.cursor()
        self.executeSQL(c,"select prefix from %s_namespace_binds where uri = '%s'"%(
            self._internedId,
            namespace)
        )
        rt = [rtTuple[0] for rtTuple in c.fetchall()]
        c.close()
        return rt and rt[0] or None

    def namespace(self, prefix):
        """ """
        c=self._db.cursor()
        try:
            self.executeSQL(c,"select uri from %s_namespace_binds where prefix = '%s'"%(
                self._internedId,
                prefix)
                      )
        except:
            return None
        rt = [rtTuple[0] for rtTuple in c.fetchall()]
        c.close()
        return rt and rt[0] or None

    def namespaces(self):
        """ """
        c=self._db.cursor()
        self.executeSQL(c,"select prefix, uri from %s_namespace_binds where 1;"%(
            self._internedId
            )
        )
        rt=c.fetchall()
        c.close()
        for prefix,uri in rt:
            yield prefix,uri


class MySQL(SQL):
    """
    MySQL implementation of FOPL Relational Model as an rdflib Store
    """
    try:
        import MySQLdb
        def connect(self, user, passwd, db, port, host):
            return MySQL.MySQLdb.connect(user=user, passwd=passwd, db=db,
                                         port=int(port), host=host,
                                         charset='utf8')
    except ImportError:
        def connect(self, user, passwd, db, port, host):
            raise NotImplementedError(
              'We need the MySQLdb module to connect to MySQL databases.')
    
    def _createViews(self,cursor):
      for suffix, (relations_only, tables) in self.viewCreationDict.items():
        query = ('CREATE SQL SECURITY INVOKER VIEW %s%s AS %s' %
                  (self._internedId, suffix, ' UNION ALL '.join(
                     [t.viewUnionSelectExpression(relations_only)
                      for t in tables])))
        if self.debug:
          print >> sys.stderr, "## Creating View ##\n",query
        self.executeSQL(cursor, query)

# TODO: break this out into a separate module, which will allow us to do
# away with the import chicanery.
class PostgreSQL(SQL):
    def __init__(self, identifier=None, configuration=None,
                 debug=False):
        super(PostgreSQL, self).__init__(identifier=identifier,
          configuration=None, debug=False, engine="", useSignedInts=True,
          hashFieldType='BIGINT', declareEnums=True)

        self.showDBsCommand = 'SELECT datname FROM pg_database'
        self.findTablesCommand = """SELECT tablename FROM pg_tables WHERE
                                    tablename = lower('%s')"""
        self.findViewsCommand = """SELECT viewname FROM pg_views WHERE
                                    viewname = lower('%s')"""
        self.defaultDB = 'template1'
        self.select_modifier = ''

        self.INDEX_NS_BINDS_TABLE = \
          'CREATE INDEX uri_index on %s_namespace_binds (uri)'

    try:
        import pgdb
        def connect(self, user, passwd, db, port, host):
            return PostgreSQL.pgdb.connect(
                     user=user, password=passwd, database=db,
                     host=host + ':' + str(port))
    except ImportError:
        try:
            from postgresql.interface.proboscis import dbapi2
            def connect(self, user, passwd, db, port, host):
                return PostgreSQL.dbapi2.connect(
                         user=user, password=passwd, database=db,
                         host=host, port=port)
        except ImportError:
            def connect(self, user, passwd, db, port, host):
                raise NotImplementedError(
                  'We need the PyGreSQL module to connect to PostgreSQL databases.')

if False:
  class InnoDB(MySQL):
    pass

  class MyISAM(MySQL):
    pass


CREATE_NS_BINDS_TABLE = """
CREATE TABLE %s_namespace_binds (
    prefix        varchar(20) UNIQUE not NULL,
    uri           text,
    PRIMARY KEY (prefix)) %s"""        
