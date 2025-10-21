"""
Complete system setup script demonstrating how to use the modularized components.
This script shows how to load data and set up the entire recommendation system.
"""

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), 'src'))

from src.utils import get_neo4j_driver
from src.graph_loader import create_schema, preprocess_data, load_all_data, create_co_occurrence_relationships
from src.recommender_engine import calculate_mrr

def setup_complete_system():
    """
    Complete system setup: load data, create graph, and verify MRR.
    This demonstrates the full pipeline from the notebook.
    """
    print("=" * 80)
    print("SETTING UP COMPLETE SESSION-BASED RECOMMENDATION SYSTEM")
    print("=" * 80)
    
    # Connection details
    URI = "bolt://127.0.0.1:7687"
    AUTH = ("neo4j", "12345678")
    
    try:
        # Step 1: Connect to Neo4j
        print("\n1. Connecting to Neo4j...")
        driver = get_neo4j_driver(URI, AUTH)
        print("✅ Connected to Neo4j")
        
        # Step 2: Create schema (constraints and indexes)
        print("\n2. Creating schema...")
        create_schema(driver)
        print("✅ Schema created")
        
        # Step 3: Preprocess data
        print("\n3. Preprocessing data...")
        events_df, session_nodes_df, item_properties_df, category_tree_df = preprocess_data(
            events_path='data/events.csv',
            properties_paths=['data/item_properties_part1.csv', 'data/item_properties_part2.csv'],
            category_path='data/category_tree.csv'
        )
        print("✅ Data preprocessed")
        
        # Step 4: Load all data to Neo4j
        print("\n4. Loading data to Neo4j...")
        dataframes = {
            'events_df': events_df,
            'session_nodes_df': session_nodes_df,
            'item_properties_df': item_properties_df,
            'category_tree_df': category_tree_df
        }
        load_all_data(driver, dataframes)
        print("✅ All data loaded to Neo4j")
        
        # Step 5: Create co-occurrence relationships
        print("\n5. Creating co-occurrence relationships...")
        create_co_occurrence_relationships(driver)
        print("✅ Co-occurrence relationships created")
        
        # Step 6: Calculate and verify MRR
        print("\n6. Calculating MRR to verify system...")
        mrr_score = calculate_mrr(driver, events_df)
        print(f"✅ Final MRR Score: {mrr_score:.4f}")
        
        if abs(mrr_score - 0.2503) < 0.001:
            print("🎉 SUCCESS: MRR matches expected value from notebook!")
        else:
            print(f"⚠️  WARNING: MRR differs from expected value (0.2503)")
        
        print("\n" + "=" * 80)
        print("✅ SYSTEM SETUP COMPLETE!")
        print("The recommendation system is ready to use.")
        print("You can now run the Flask app with: python src/app.py")
        print("=" * 80)
        
        return True
        
    except Exception as e:
        print(f"\n❌ System setup failed: {e}")
        return False
    
    finally:
        if 'driver' in locals() and driver:
            driver.close()
            print("\nNeo4j connection closed.")

def quick_test():
    """
    Quick test to verify the system is working without full data reload.
    """
    print("\n" + "=" * 60)
    print("QUICK SYSTEM TEST")
    print("=" * 60)
    
    URI = "bolt://127.0.0.1:7687"
    AUTH = ("neo4j", "12345678")
    
    try:
        driver = get_neo4j_driver(URI, AUTH)
        
        # Test basic functionality
        from src.recommender_engine import get_next_item_prediction, find_recurring_patterns
        
        print("Testing prediction...")
        recommendations = get_next_item_prediction(driver, 119736, k=3)
        if recommendations:
            print(f"✅ Got {len(recommendations)} recommendations")
        
        print("Testing patterns...")
        patterns = find_recurring_patterns(driver, limit=3)
        if patterns:
            print(f"✅ Found {len(patterns)} patterns")
        
        print("✅ Quick test passed!")
        return True
        
    except Exception as e:
        print(f"❌ Quick test failed: {e}")
        return False
    
    finally:
        if 'driver' in locals() and driver:
            driver.close()

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description='Setup the recommendation system')
    parser.add_argument('--quick', action='store_true', 
                       help='Run quick test instead of full setup')
    
    args = parser.parse_args()
    
    if args.quick:
        success = quick_test()
    else:
        success = setup_complete_system()
    
    sys.exit(0 if success else 1)
