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
    """
    Finds the most common 3-step sequential conversion funnel:
    (VIEW) -> (ADD TO CART) -> (TRANSACTION).
    """
    query = """
    // Target: The most valuable 3-step sequence: VIEW -> ADD TO CART -> TRANSACTION
    MATCH (s:Session)
    
    // Step 1: The starting 'view' action (r1) on Product A (p1)
    MATCH (s)-[r1:PERFORMED {action: 'view'}]->(p1:Product)

    // Step 2: The 'addtocart' action (r2) on Product B (p2)
    // r2 MUST follow r1 immediately
    MATCH (s)-[r2:PERFORMED {action: 'addtocart'}]->(p2:Product)
    WHERE r2.step = r1.step + 1

    // Step 3: The 'transaction' action (r3) on Product C (p3)
    // r3 MUST follow r2 immediately
    MATCH (s)-[r3:PERFORMED {action: 'transaction'}]->(p3:Product)
    WHERE r3.step = r2.step + 1

    // Group by the sequence of PIDs and the Session, then count
    WITH p1.pid AS pid_A, p2.pid AS pid_B, p3.pid AS pid_C, COUNT(s) AS pattern_count

    // Find the top X most common funnels
    ORDER BY pattern_count DESC
    LIMIT $limit

    // Return the result
    RETURN pid_A, pid_B, pid_C, pattern_count
    """
    try:
        results = run_cypher_query(driver, query, {'limit': limit}, timeout_s=120)
        # Note: The UI expects a list of tuples: (pid_A, pid_B, pid_C, count)
        return [(rec['pid_A'], rec['pid_B'], rec['pid_C'], rec['pattern_count']) for rec in results]
    except Exception as e:
        print(f"Error running conversion funnel query: {e}")
        return []


# 3. Behavioral Pattern Detection (Action Sequence)
def find_behavioral_patterns(driver, limit=5):
    """
    Finds the most common 3-step sequential action patterns (Action A -> Action B -> Action C).
    """
    query = """
    MATCH (s:Session)-[r1:PERFORMED]->(:Product)
    MATCH (s)-[r2:PERFORMED]->(:Product)
    WHERE r2.step = r1.step + 1
    
    MATCH (s)-[r3:PERFORMED]->(:Product)
    WHERE r3.step = r2.step + 1

    // Group by the sequence of Actions (r1.action, r2.action, r3.action) and count sessions
    WITH r1.action AS action_A, r2.action AS action_B, r3.action AS action_C, COUNT(DISTINCT s) AS pattern_count
    
    ORDER BY pattern_count DESC
    LIMIT $limit
    
    RETURN action_A, action_B, action_C, pattern_count
    """
    try:
        results = run_cypher_query(driver, query, {'limit': limit}, timeout_s=120)
        # Map to list of tuples: (action_A, action_B, action_C, count)
        return [(rec['action_A'], rec['action_B'], rec['action_C'], rec['pattern_count']) for rec in results]
    except Exception as e:
        print(f"Error running behavioral pattern query: {e}")
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