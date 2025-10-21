from flask import Flask, render_template, jsonify, session, redirect, url_for, request
from flask_socketio import SocketIO, emit
from .utils import get_neo4j_driver, run_cypher_query
from .recommender_engine import (
    get_next_item_prediction, 
    find_recurring_patterns, 
    generate_llm_prompt
)
from .llm_service import generate_llm_output
import pandas as pd
import random
import json
import os

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
TEMPLATES_PATH = os.path.join(BASE_DIR, 'templates')
STATIC_PATH = os.path.join(BASE_DIR, 'static')

app = Flask(__name__, template_folder=TEMPLATES_PATH, static_folder=STATIC_PATH)
socketio = SocketIO(app, cors_allowed_origins="*")

# =========================================
# CONFIGURATION
# =========================================
app.secret_key = 'my_super_secret_key_for_demo_project_session-rec'

# Neo4j connection details
URI = "bolt://127.0.0.1:7687"
AUTH = ("neo4j", "12345678")

# Demo products for interactive session
DEMO_PRODUCTS = [461686, 409804, 29196, 119736, 186702, 40870, 235559, 274443, 417927, 190000]

# Global driver instance
driver = None

def get_driver():
    global driver
    if driver is None:
        driver = get_neo4j_driver(URI, AUTH)
    return driver

# =========================================
# MAIN ROUTES
# =========================================

@app.route('/')
def index():
    """Main dashboard."""
    return render_template('index.html', mrr_score="0.2503")

@app.route('/predict/<int:pid>')
def predict(pid):
    """Get recommendations for a specific product."""
    try:
        driver = get_driver()
        recommendations = get_next_item_prediction(driver, pid, k=10)
        return render_template('prediction.html', current_pid=pid, recommendations=recommendations)
    except Exception as e:
        return f"Error: {str(e)}", 500

@app.route('/explain/<int:viewed_pid>/<int:recommended_pid>')
def explain(viewed_pid, recommended_pid):
    """Generate LLM explanation for a recommendation."""
    try:
        driver = get_driver()
        prompt_result = generate_llm_prompt(driver, viewed_pid, recommended_pid)
        
        # Extract the prompt string from the Neo4j result
        if isinstance(prompt_result, list) and len(prompt_result) > 0:
            final_prompt = prompt_result[0].get('LLM_Prompt', str(prompt_result))
        else:
            final_prompt = str(prompt_result)
        
        # Call Gemini to get real LLM output
        try:
            llm_output = generate_llm_output(final_prompt)
        except Exception as e:
            llm_output = f"LLM error: {str(e)}\n\nPrompt:\n{final_prompt}"
        
        return render_template('explanation.html', 
                            viewed_pid=viewed_pid, 
                            recommended_pid=recommended_pid,
                            prompt_string=llm_output)
    except Exception as e:
        return f"Error generating explanation: {str(e)}", 500

@app.route('/patterns')
def patterns():
    """Show recurring patterns."""
    try:
        driver = get_driver()
        patterns = find_recurring_patterns(driver, limit=10)
        return render_template('patterns.html', patterns=patterns)
    except Exception as e:
        return f"Error: {str(e)}", 500

@app.route('/graph')
def graph_visualization():
    """Real-time graph visualization page."""
    return render_template('graph.html')

@app.route('/prompt', methods=['GET', 'POST'])
def prompt_page():
    """LLM prompt interface."""
    output = None
    default_prompt = "Explain how our co-occurrence graph generates next-item recommendations."
    
    if request.method == 'POST':
        prompt_text = request.form.get('prompt') or ''
        try:
            output = generate_llm_output(prompt_text)
        except Exception as e:
            output = f"LLM error: {str(e)}"
    
    return render_template('prompt.html', output=output, default_prompt=default_prompt)

# =========================================
# INTERACTIVE SESSION ROUTES
# =========================================

@app.route('/start_session')
def start_session():
    """Start a new interactive session."""
    session.pop('history', None) 
    session['history'] = [{'pid': random.choice(DEMO_PRODUCTS), 'type': 'view'}]
    return redirect(url_for('session_demo'))

@app.route('/action/<int:pid>/<action_type>')
def user_action(pid, action_type):    
    current_history = session.get('history', [])
    current_history.append({'pid': pid, 'type': action_type})
    session['history'] = current_history 
    return redirect(url_for('session_demo'))

@app.route('/session_demo')
def session_demo():
    history = session.get('history', [])
    print("CURRENT SESSION HISTORY:", history) 
    
    if not history:
        return redirect(url_for('start_session'))

    last_item = history[-1]
    last_pid = last_item['pid']
    last_action_type = last_item['type']
    
    recs_list = []
    prediction_table = ""
    
    # Get live recommendations
    if last_pid:
        try:
            driver = get_driver()
            recs_list = get_next_item_prediction(driver, last_pid, k=5) 
            
            if recs_list:
                table_content = f"""
                <table class="table align-middle">
                    <thead>
                        <tr>
                            <th>Rank</th>
                            <th>Recommended PID</th>
                            <th>Score (Co-occurrence)</th>
                            <th>Avg Time Diff</th>
                            <th>Reasoning (Bonus)</th>
                        </tr>
                    </thead>
                    <tbody>
                        { "".join([f'<tr><td class="rank">{i+1}</td><td><strong>{rec[0]}</strong></td><td class="popularity">{rec[1]}</td><td>{rec[2]/1000:.2f}s</td><td><a class="explain-btn" href="{url_for("explain", viewed_pid=last_pid, recommended_pid=rec[0])}">Explain Why</a></td></tr>' 
                                for i, rec in enumerate(recs_list)]) }
                    </tbody>
                </table>
                """
                prediction_table = table_content
        except Exception as e:
            prediction_table = f"<p style='color:red;'>Error retrieving live recommendations: {str(e)}</p>"

    return render_template('session_demo.html', 
                          DEMO_PRODUCTS=DEMO_PRODUCTS,
                          session_history=[f"PID: {item['pid']} ({item['type']})" for item in history], 
                          last_pid=last_pid,
                          last_action_type=last_action_type,
                          recommendations=recs_list, 
                          prediction_table=prediction_table)

# =========================================
# API ENDPOINTS
# =========================================

@app.route('/api/graph-data')
def api_graph_data():
    """API endpoint to get graph data for visualization."""
    try:
        driver = get_driver()
        
        # Get sample of products and their co-occurrence relationships
        query = """
        MATCH (p1:Product)-[co:CO_OCCURS_WITH]->(p2:Product)
        WHERE co.popularity > 10
        RETURN p1.pid as from_pid, p2.pid as to_pid, co.popularity as weight
        ORDER BY co.popularity DESC
        LIMIT 500
        """
        
        results = run_cypher_query(driver, query)
        
        # Create nodes and edges for vis.js
        nodes = []
        edges = []
        node_ids = set()
        
        for result in results:
            from_pid = result['from_pid']
            to_pid = result['to_pid']
            weight = result['weight']
            
            # Add nodes
            if from_pid not in node_ids:
                nodes.append({
                    'id': from_pid,
                    'label': str(from_pid),
                    'group': 'product',
                    'title': f'Product {from_pid}'
                })
                node_ids.add(from_pid)
                
            if to_pid not in node_ids:
                nodes.append({
                    'id': to_pid,
                    'label': str(to_pid),
                    'group': 'product',
                    'title': f'Product {to_pid}'
                })
                node_ids.add(to_pid)
            
            # Add edge
            edges.append({
                'from': from_pid,
                'to': to_pid,
                'width': min(weight / 10, 10), 
                'title': f'Co-occurrence: {weight}'
            })
        
        return jsonify({'nodes': nodes, 'edges': edges})
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/recommendations/<int:pid>')
def api_recommendations(pid):
    """API endpoint to get recommendations for a specific product."""
    try:
        driver = get_driver()
        recommendations = get_next_item_prediction(driver, pid, k=10)
        return jsonify({'recommendations': recommendations})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# =========================================
# WEBSOCKET EVENTS
# =========================================

@socketio.on('request_update')
def handle_update_request():
    """Handle WebSocket requests for graph updates."""
    try:
        driver = get_driver()
        
        # Get updated graph data
        query = """
        MATCH (p1:Product)-[co:CO_OCCURS_WITH]->(p2:Product)
        WHERE co.popularity > 10
        RETURN p1.pid as from_pid, p2.pid as to_pid, co.popularity as weight
        ORDER BY co.popularity DESC
        LIMIT 500
        """
        
        results = run_cypher_query(driver, query)
        
        # Create nodes and edges
        nodes = []
        edges = []
        node_ids = set()
        
        for result in results:
            from_pid = result['from_pid']
            to_pid = result['to_pid']
            weight = result['weight']
            
            if from_pid not in node_ids:
                nodes.append({
                    'id': from_pid,
                    'label': str(from_pid),
                    'group': 'product',
                    'title': f'Product {from_pid}'
                })
                node_ids.add(from_pid)
                
            if to_pid not in node_ids:
                nodes.append({
                    'id': to_pid,
                    'label': str(to_pid),
                    'group': 'product',
                    'title': f'Product {to_pid}'
                })
                node_ids.add(to_pid)
            
            edges.append({
                'from': from_pid,
                'to': to_pid,
                'width': min(weight / 10, 10),
                'title': f'Co-occurrence: {weight}'
            })
        
        # Emit update to all connected clients
        emit('graph_update', {'nodes': nodes, 'edges': edges})
        
    except Exception as e:
        emit('error', {'message': str(e)})

# =========================================
# APPLICATION STARTUP
# =========================================

if __name__ == '__main__':
    socketio.run(app, debug=True, host='0.0.0.0', port=5000)
