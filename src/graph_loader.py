import pandas as pd
from .utils import run_cypher_query, load_data_to_neo4j


def create_schema(driver):
    schema_queries = [
        # 1. Visitor Node Constraint (Unique visitorId)
        "CREATE CONSTRAINT visitorId_is_unique IF NOT EXISTS FOR (v:Visitor) REQUIRE v.visitorId IS UNIQUE;",

        # 2. Session Node Constraint (Unique sid)
        "CREATE CONSTRAINT sid_is_unique IF NOT EXISTS FOR (s:Session) REQUIRE s.sid IS UNIQUE;",

        # 3. Product Node Constraint (Unique pid)
        "CREATE CONSTRAINT pid_is_unique IF NOT EXISTS FOR (p:Product) REQUIRE p.pid IS UNIQUE;",

        # 4. Category Node Constraint (Unique catid)
        "CREATE CONSTRAINT catid_is_unique IF NOT EXISTS FOR (c:Category) REQUIRE c.catid IS UNIQUE;",

        # 5. PropertyValue Node Constraint (Unique value)
        "CREATE CONSTRAINT prop_val_is_unique IF NOT EXISTS FOR (pv:PropertyValue) REQUIRE pv.value IS UNIQUE;",

        # 6. PropertyType Index (To quickly look up property names)
        "CREATE INDEX prop_type_index IF NOT EXISTS FOR (pt:PropertyType) ON (pt.name);"
    ]

    # Execute the queries
    print("Creating Neo4j Constraints and Indexes...")
    for query in schema_queries:
        try:
            run_cypher_query(driver, query)
            parts = query.split(' ')
            label_prop = next(p for p in parts if ')' in p)
            print(f"  - SUCCESS: {parts[2]} on {label_prop}")
        except Exception as e:
            print(f"  - ERROR with query: {query.split(' ')[2]} - {e}")

    print("Neo4j schema foundation is complete.")


def preprocess_data(events_path, properties_paths, category_path):
    """
    Performs all Pandas logic, including:
    - Loading/merging CSVs
    - CRITICAL: Sessionization Logic (using the 5-minute timeout)
    - Calculates session_nodes_df, events_df, etc.
    
    Args:
        events_path (str): Path to events.csv
        properties_paths (list): List of paths to item properties CSV files
        category_path (str): Path to category_tree.csv
    
    Returns:
        tuple: (events_df, session_nodes_df, item_properties_df, category_tree_df)
    """
    # Load the datasets
    events_df = pd.read_csv(events_path)
    item_properties1_df = pd.read_csv(properties_paths[0])
    item_properties2_df = pd.read_csv(properties_paths[1])
    category_tree_df = pd.read_csv(category_path)

    item_properties_df = pd.concat([item_properties1_df, item_properties2_df], ignore_index=True)

    # Rename columns for clarity and consistency with the graph model
    events_df = events_df.rename(columns={
        'timestamp': 'timestamp_ms', 
        'visitorid': 'visitorId', 
        'itemid': 'pid', 
        'event': 'action'
    })
    category_tree_df = category_tree_df.rename(columns={
        'categoryid': 'catid', 
        'parentid': 'parentCatid'
    })

    # Convert timestamps from milliseconds to seconds
    events_df['timestamp_s'] = (events_df['timestamp_ms'] / 1000).astype(int)
    item_properties_df['timestamp_s'] = (item_properties_df['timestamp'] / 1000).astype(int)

    print(f"Events loaded: {len(events_df)} rows")
    print(f"Item Properties loaded: {len(item_properties_df)} rows")
    print(f"Category Tree loaded: {len(category_tree_df)} rows")

    SESSION_TIMEOUT_S = 5 * 60  # 5 minutes in seconds

    # Sort events by visitor and then by time
    events_df = events_df.sort_values(['visitorId', 'timestamp_s']).reset_index(drop=True)

    # Calculate the time difference (delta) between consecutive events for each visitor
    events_df['time_diff'] = events_df.groupby('visitorId')['timestamp_s'].diff().fillna(0)

    # Identify the start of a new session: either the first event for a visitor (time_diff=0)
    # or if the time difference is greater than the session timeout.
    events_df['new_session'] = events_df['time_diff'] > SESSION_TIMEOUT_S

    # Create a session counter that increments every time 'new_session' is True
    events_df['session_count'] = events_df.groupby('visitorId')['new_session'].cumsum()

    # Create the unique Session ID (sid)
    events_df['sid'] = events_df['visitorId'].astype(str) + '_' + events_df['session_count'].astype(str)

    # Calculate the sequential step for the PERFORMED relationship
    events_df['step'] = events_df.groupby('sid').cumcount() + 1

    # Extract the unique Session starting/ending times for the Session nodes
    session_nodes_df = events_df.groupby('sid').agg(
        visitorId=('visitorId', 'first'),
        startTime=('timestamp_ms', 'min'),
        endTime=('timestamp_ms', 'max'),
    ).reset_index()

    print(f"Total Sessions created: {len(session_nodes_df)}")
    
    return events_df, session_nodes_df, item_properties_df, category_tree_df


def load_all_data(driver, dataframes):
    """
    Combines all loading steps from Notebook Part 3, creating all nodes 
    (Visitor, Session, etc.) and the sequential relationships 
    (:PERFORMED, :HAS_PROPERTY, etc.).
    
    Args:
        driver: Neo4j driver object
        dataframes (dict): Dictionary containing all processed DataFrames
    """
    events_df = dataframes['events_df']
    session_nodes_df = dataframes['session_nodes_df']
    item_properties_df = dataframes['item_properties_df']
    category_tree_df = dataframes['category_tree_df']

    # -----------------------------------------------------------
    # 1. Load Visitor and Session Nodes & HAS_SESSION
    # -----------------------------------------------------------
    session_cypher = """
    UNWIND $data AS row
    MERGE (v:Visitor {visitorId: row.visitorId})
    MERGE (s:Session {sid: row.sid})
    SET s.startTime = row.startTime,
        s.endTime = row.endTime
    MERGE (v)-[:HAS_SESSION]->(s)
    """
    load_data_to_neo4j(driver, session_nodes_df, session_cypher, batch_size=10000, key='data')
    print("Loaded Visitor and Session Nodes.")

    # -----------------------------------------------------------
    # 2. Load Product Nodes
    # -----------------------------------------------------------
    unique_pids = events_df[['pid']].drop_duplicates()
    product_cypher = """
    UNWIND $data AS row
    MERGE (p:Product {pid: row.pid})
    """
    load_data_to_neo4j(driver, unique_pids, product_cypher, batch_size=10000, key='data')
    print("Loaded Product Nodes.")

    # -----------------------------------------------------------
    # 3. Load PERFORMED Relationships (The sequential session actions)
    # -----------------------------------------------------------
    events_load_df = events_df[['sid', 'pid', 'step', 'action', 'timestamp_ms']]

    performed_cypher = """
    UNWIND $data AS row
    MATCH (s:Session {sid: row.sid})
    MATCH (p:Product {pid: row.pid})
    CREATE (s)-[:PERFORMED {
        step: row.step, 
        action: row.action, 
        timestamp: row.timestamp_ms
    }]->(p)
    """
    # THIS WILL BE THE LONGEST STEP
    load_data_to_neo4j(driver, events_load_df, performed_cypher, batch_size=10000, key='data')
    print("Loaded PERFORMED relationships.")

    # -----------------------------------------------------------
    # 4. Load Category Hierarchy and Links
    # -----------------------------------------------------------
    # IS_PARENT_OF
    category_links = category_tree_df.dropna(subset=['parentCatid']).to_dict('records')
    category_hierarchy_cypher = """
    UNWIND $data AS row
    MERGE (child:Category {catid: row.catid})
    MERGE (parent:Category {catid: row.parentCatid})
    MERGE (parent)-[:IS_PARENT_OF]->(child)
    """
    # This file is small, running directly without advanced batching
    run_cypher_query(driver, category_hierarchy_cypher, {'data': category_links}) 
    print("Loaded Category Nodes and IS_PARENT_OF relationships.")

    # BELONGS_TO (Product to Category)
    item_cat_df = item_properties_df[item_properties_df['property'] == 'categoryid'].copy()
    item_cat_df = item_cat_df.sort_values('timestamp').drop_duplicates(subset=['itemid'], keep='last')
    item_cat_df = item_cat_df.rename(columns={'itemid': 'pid', 'value': 'catid_str'})
    item_cat_df['catid'] = item_cat_df['catid_str'].str.replace('n', '').str.split('.').str[0].astype(int)

    belongs_to_cypher = """
    UNWIND $data AS row
    MATCH (p:Product {pid: row.pid})
    MATCH (c:Category {catid: row.catid})
    MERGE (p)-[:BELONGS_TO]->(c)
    """
    load_data_to_neo4j(driver, item_cat_df[['pid', 'catid']], belongs_to_cypher, batch_size=10000, key='data')
    print("Loaded BELONGS_TO relationships.")

    # -----------------------------------------------------------
    # 5. Load Item Properties (Context Layer)
    # -----------------------------------------------------------
    prop_load_df = item_properties_df.rename(columns={
        'itemid': 'pid', 
        'property': 'prop_name', 
        'value': 'prop_value', 
        'timestamp': 'timestamp_ms'
    })

    properties_cypher = """
    UNWIND $data AS row
    MATCH (p:Product {pid: row.pid})

    // Create or Match the PropertyType node
    MERGE (pt:PropertyType {name: row.prop_name})

    // Create or Match the PropertyValue node
    MERGE (pv:PropertyValue {value: row.prop_value})

    // Link PropertyValue to PropertyType
    MERGE (pv)-[:IS_TYPE_OF]->(pt) 

    // Link Product to PropertyValue with a timestamp property
    CREATE (p)-[:HAS_PROPERTY {
        timestamp: row.timestamp_ms
    }]->(pv)
    """
    load_data_to_neo4j(driver, prop_load_df[['pid', 'prop_name', 'prop_value', 'timestamp_ms']], 
                      properties_cypher, batch_size=10000, key='data')
    print("Loaded Item Properties and HAS_PROPERTY relationships.")

    print("\n--- CORE GRAPH MODELING COMPLETE ---")


def create_co_occurrence_relationships(driver):
    """
    Implements the final aggregation query from Notebook Part 4, including 
    the calculation of popularity and avgDuration on the :CO_OCCURS_WITH relationship.
    
    Args:
        driver: Neo4j driver object
    """
    co_occurrence_cypher = """
    // CO_OCCURS_WITH aggregation between products based on shared sessions
    MATCH (s:Session)-[r1:PERFORMED]->(p1:Product)
    MATCH (s)-[r2:PERFORMED]->(p2:Product)

    // Ensure the two products are NOT the same (pure co-occurrence pair)
    WHERE elementId(p1) < elementId(p2)

    // Aggregate the session counts and collected durations for the pair
    WITH p1, p2, 
         COUNT(s) AS popularity, 
         COLLECT(toInteger(abs(r1.timestamp - r2.timestamp))) AS durations
         
    // Calculate the average duration
    WITH p1, p2, popularity, 
         CASE 
             WHEN size(durations) > 0 
             THEN reduce(total = 0, d IN durations | total + d) / size(durations)
             ELSE 0 
         END AS avgDurationMs

    // Create or update the CO_OCCURS_WITH relationship
    MERGE (p1)-[co:CO_OCCURS_WITH]->(p2)
    SET co.popularity = popularity,
        co.avgDuration = avgDurationMs
    """

    print("\n--- Starting CO_OCCURS_WITH aggregation (This will be CPU intensive) ---")
    try:
        run_cypher_query(driver, co_occurrence_cypher)
        print("✅ SUCCESS: CO_OCCURS_WITH relationships created!")

        # Optional: count created relationships
        count_result = run_cypher_query(driver, "MATCH ()-[r:CO_OCCURS_WITH]->() RETURN COUNT(r) AS count")
        print(f"🔗 Total CO_OCCURS_WITH relationships: {count_result[0]['count']}")

    except Exception as e:
        print(f"❌ ERROR creating CO_OCCURS_WITH: {e}")
        raise e
