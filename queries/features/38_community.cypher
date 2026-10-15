// Label-propagation communities over BIB_COUPLED among AsOf papers; stored in the scratch property comm.
// FalkorDB's algorithm treats these edges as undirected (checked on a small test graph).
CALL algo.labelPropagation({nodeLabels:['AsOf'], relationshipTypes:['BIB_COUPLED'], maxIterations: 10})
YIELD node, communityId
SET node.comm = communityId
RETURN count(node) AS n
