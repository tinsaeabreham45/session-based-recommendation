# """
# Utility functions for database connectivity and batch operations.
# Foundation module for the session-based recommendation system.
# """

# from neo4j import GraphDatabase
# from tqdm import tqdm
# import pandas as pd


# def get_neo4j_driver(uri, auth):
#     """
#     Initializes and returns the Neo4j driver object.
#     MUST handle connection failure.
    
#     Args:
#         uri (str): Neo4j connection URI
#         auth (tuple): Authentication tuple (username, password)
    
#     Returns:
#         GraphDatabase.driver: Neo4j driver object
        
#     Raises:
#         Exception: If connection fails
#     """
#     try:
#         driver = GraphDatabase.driver(uri, auth=auth)
#         # Test the connection
#         with driver.session() as session:
#             session.run("RETURN 1")
#         return driver
#     except Exception as e:
#         raise Exception(f"Failed to connect to Neo4j: {e}")


# def run_cypher_query(driver, query, params=None, timeout_s=3600):
#     """
#     Wrapper for driver.session().run() with timeout support.
#     MUST include the timeout_s parameter (set to 3600 for safety).
    
#     Args:
#         driver: Neo4j driver object
#         query (str): Cypher query string
#         params (dict): Query parameters
#         timeout_s (int): Query timeout in seconds (default: 3600)
    
#     Returns:
#         list: Query results as list of records
#     """
#     with driver.session() as session:
#         result = session.run(query, params, timeout=timeout_s)
#         return [record for record in result]


# def load_data_to_neo4j(driver, df, cypher_query, batch_size=10000, key='data'):
#     """
#     The efficient UNWIND/MERGE batch loader with tqdm integration.
    
#     Args:
#         driver: Neo4j driver object
#         df (pd.DataFrame): DataFrame to load
#         cypher_query (str): Cypher query with UNWIND clause
#         batch_size (int): Batch size for loading (default: 10000)
#         key (str): Parameter key for the batch data (default: 'data')
#     """
#     total_batches = len(df) // batch_size + (1 if len(df) % batch_size else 0)

#     with tqdm(total=total_batches, desc=f"Loading {key}") as pbar:
#         for i in range(0, len(df), batch_size):
#             batch = df.iloc[i:i + batch_size].to_dict('records')
#             run_cypher_query(driver, cypher_query, {key: batch})
#             pbar.update(1)

from neo4j import GraphDatabase
from neo4j.exceptions import ServiceUnavailable
from tqdm import tqdm

# --- Core Neo4j Driver and Execution Utilities ---

def get_neo4j_driver(uri, auth):
    """Initializes and returns the Neo4j driver object."""
    try:
        # Using the direct bolt protocol
        driver = GraphDatabase.driver(uri, auth=auth)
        driver.verify_connectivity()
        return driver
    except ServiceUnavailable as e:
        print(f"ERROR: Could not connect to Neo4j database at {uri}.")
        print(f"Ensure the database is running and credentials are correct. Error: {e}")
        return None

def run_cypher_query(driver, query, params=None, timeout_s=3600):
    """
    Wrapper for running Cypher queries. 
    Returns a list of neo4j Records.
    """
    if driver is None:
        raise ServiceUnavailable("Neo4j Driver is not connected.")
        
    # We use a context manager to handle sessions automatically
    with driver.session() as session:
        # Execute with the defined timeout
        result = session.run(query, params, timeout=timeout_s)
        # Convert to a list of records to ensure result is accessible outside the session
        return [record for record in result]