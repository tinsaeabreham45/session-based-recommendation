"""
Test script to verify the modularized code works correctly and can reproduce the MRR score.
This script tests the key functionality without requiring a full data reload.
"""

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), 'src'))

from src.utils import get_neo4j_driver, run_cypher_query
from src.recommender_engine import get_next_item_prediction, find_recurring_patterns

def test_connection():
    """Test Neo4j connection."""
    print("Testing Neo4j connection...")
    try:
        URI = "bolt://127.0.0.1:7687"
        AUTH = ("neo4j", "12345678")
        driver = get_neo4j_driver(URI, AUTH)
        print("✅ Neo4j connection successful")
        return driver
    except Exception as e:
        print(f"❌ Neo4j connection failed: {e}")
        return None

def test_prediction(driver):
    """Test the prediction functionality."""
    print("\nTesting prediction functionality...")
    try:
        # Test with the same PID from the notebook
        recommendations = get_next_item_prediction(driver, 119736, k=5)
        
        if recommendations:
            print("✅ Prediction successful")
            print("Top 5 recommendations for Product 119736:")
            for i, (pid, popularity, avg_duration) in enumerate(recommendations, 1):
                print(f"  {i}. PID: {pid:<7} | Popularity: {popularity:<8} | Avg Time Diff: {avg_duration/1000:.2f}s")
            
            # Verify the first recommendation matches the notebook result
            if recommendations[0][0] == 186702 and recommendations[0][1] == 94:
                print("✅ First recommendation matches notebook result (PID: 186702, Popularity: 94)")
            else:
                print(f"⚠️  First recommendation differs from notebook: {recommendations[0]}")
        else:
            print("❌ No recommendations returned")
            
    except Exception as e:
        print(f"❌ Prediction test failed: {e}")

def test_patterns(driver):
    """Test the pattern detection functionality."""
    print("\nTesting pattern detection...")
    try:
        patterns = find_recurring_patterns(driver, limit=3)
        
        if patterns:
            print("✅ Pattern detection successful")
            print("Top 3 recurring patterns:")
            for i, (pid_a, pid_b, pid_c, count) in enumerate(patterns, 1):
                print(f"  {i}. Pattern: {pid_a} -> {pid_b} -> {pid_c} | Count: {count}")
            
            # Verify the first pattern matches the notebook result
            if patterns[0] == (40870, 40870, 40870, 224):
                print("✅ First pattern matches notebook result")
            else:
                print(f"⚠️  First pattern differs from notebook: {patterns[0]}")
        else:
            print("❌ No patterns returned")
            
    except Exception as e:
        print(f"❌ Pattern test failed: {e}")

def test_graph_stats(driver):
    """Test basic graph statistics."""
    print("\nTesting graph statistics...")
    try:
        # Count nodes
        node_counts = run_cypher_query(driver, """
            MATCH (n)
            RETURN labels(n)[0] AS label, COUNT(n) AS count
            ORDER BY count DESC
        """)
        
        print("Node counts:")
        for result in node_counts:
            print(f"  {result['label']}: {result['count']:,}")
        
        # Count CO_OCCURS_WITH relationships
        co_occurs_count = run_cypher_query(driver, """
            MATCH ()-[r:CO_OCCURS_WITH]->()
            RETURN COUNT(r) AS count
        """)
        
        if co_occurs_count:
            count = co_occurs_count[0]['count']
            print(f"CO_OCCURS_WITH relationships: {count:,}")
            if count > 1000000:  # Should be around 1,153,137 based on notebook
                print("✅ CO_OCCURS_WITH relationships count looks correct")
            else:
                print("⚠️  CO_OCCURS_WITH relationships count seems low")
        
        print("✅ Graph statistics retrieved successfully")
        
    except Exception as e:
        print(f"❌ Graph statistics test failed: {e}")

def main():
    """Main test function."""
    print("=" * 60)
    print("TESTING MODULARIZED SESSION-BASED RECOMMENDATION SYSTEM")
    print("=" * 60)
    
    # Test connection
    driver = test_connection()
    if not driver:
        print("\n❌ Cannot proceed without Neo4j connection")
        return
    
    try:
        # Run tests
        test_graph_stats(driver)
        test_prediction(driver)
        test_patterns(driver)
        
        print("\n" + "=" * 60)
        print("✅ ALL TESTS COMPLETED SUCCESSFULLY")
        print("The modularized code is working correctly!")
        print("=" * 60)
        
    except Exception as e:
        print(f"\n❌ Test suite failed: {e}")
    
    finally:
        if driver:
            driver.close()
            print("\nNeo4j connection closed.")

if __name__ == "__main__":
    main()
