MATCH (a:RetAuth) REMOVE a:RetAuth
RETURN count(a) AS n
