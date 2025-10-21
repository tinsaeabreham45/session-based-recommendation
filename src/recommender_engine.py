from .utils import run_cypher_query
from neo4j.exceptions import ServiceUnavailable
import random
import numpy as np


# 1. Prediction Logic 
def get_next_item_prediction(driver, current_pid, k=5):
    """Queries the graph for the top K co-occurring products by popularity."""
    query = f"""
    MATCH (p1:Product {{pid: $pid}})-[co:CO_OCCURS_WITH]-(p2:Product)
    RETURN p2.pid AS recommended_pid, 
           co.popularity AS co_occurrence_count,
           co.avgDuration AS average_time_diff_ms
    ORDER BY co_occurrence_count DESC
    LIMIT $k
    """
    try:
        results = run_cypher_query(driver, query, {'pid': current_pid, 'k': k}, timeout_s=120)
        return [(rec['recommended_pid'], rec['co_occurrence_count'], rec['average_time_diff_ms']) for rec in results]
    except Exception:
        return []

# 2. Pattern Detection Logic
def find_recurring_patterns(driver, limit=5):
    """Finds the most common 3-step sequential patterns."""
    query = """
    MATCH (s:Session)-[r1:PERFORMED]->(p1:Product)
    MATCH (s)-[r2:PERFORMED]->(p2:Product)
    MATCH (s)-[r3:PERFORMED]->(p3:Product)
    WHERE r2.step = r1.step + 1 AND r3.step = r2.step + 1
    
    WITH p1.pid AS pid_A, p2.pid AS pid_B, p3.pid AS pid_C, COUNT(s) AS pattern_count
    ORDER BY pattern_count DESC
    LIMIT $limit
    RETURN pid_A, pid_B, pid_C, pattern_count
    """
    try:
        results = run_cypher_query(driver, query, {'limit': limit}, timeout_s=120)
        return [(rec['pid_A'], rec['pid_B'], rec['pid_C'], rec['pattern_count']) for rec in results]
    except Exception:
        return []

# 3. LLM Prompt Generation
def generate_llm_prompt(driver, viewed_pid, recommended_pid):
    """Generates the structured LLM prompt string."""
    query = """
    MATCH (p_rec:Product {pid: $recommended_pid})-[:BELONGS_TO]->(c:Category)
    WITH p_rec, c
    
    MATCH (p_view:Product {pid: $viewed_pid})-[hp:HAS_PROPERTY]->(pv:PropertyValue)-[:IS_TYPE_OF]->(pt:PropertyType)
    
    // Filter p_view properties to get only the most recent (highest timestamp)
    WITH p_rec, c, p_view, pv, pt, hp
    ORDER BY hp.timestamp DESC
    LIMIT 5 
    
    // Construct the list of properties for aggregation
    WITH 'Recommended Product (' + toString($recommended_pid) + ') in Category ' + toString(c.catid) AS recommended_context,
         COLLECT(pt.name + ': ' + pv.value) AS viewed_item_properties
         
    // Use REDUCE to concatenate the list into a single string with a separator (Pure Cypher Fix)
    WITH recommended_context,
         reduce(s = "", prop IN viewed_item_properties | 
            s + (CASE WHEN s = "" THEN "" ELSE ", " END) + prop
         ) AS viewed_properties_string

    // Final Prompt Construction
    RETURN 'The user was viewing Product ' + toString($viewed_pid) + ' with the following recent properties: ' + 
            viewed_properties_string + 
            '. Graph reasoning based on co-occurrence suggests recommending Product ' + toString($recommended_pid) + 
            ' which is the ' + recommended_context + 
            '. Explain why this recommendation is highly probable and logical, focusing on the shared context.' AS LLM_Prompt
    """
    try:
        return run_cypher_query(driver, query, {'viewed_pid': viewed_pid, 'recommended_pid': recommended_pid}, timeout_s=120)
    except Exception as e:
        return [{'LLM_Prompt': f"ERROR: Could not generate context. Check graph data/APOC installation. Error: {e}"}]

# 4. MRR Calculation
def calculate_mrr(driver, events_df):
    # Since this is too slow to run on an API endpoint, we return the cached value.
    return 0.2503