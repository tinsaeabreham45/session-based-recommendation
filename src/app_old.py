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
import random # For choosing a random starting product
import json

app = Flask(__name__)
socketio = SocketIO(app, cors_allowed_origins="*")

# =========================================
# CONFIGURATION
# =========================================
# CRITICAL: Flask sessions require a secret key for session tracking to work.
app.secret_key = 'your_super_secret_key_for_demo_project_2025' 

# Neo4j connection details
URI = "bolt://127.0.0.1:7687"
AUTH = ("neo4j", "12345678")

# A short list of high-co-occurrence PIDs for the user to 'view'
DEMO_PRODUCTS = [119736, 186702, 40870, 235559, 274443, 417927, 190000]

# Global driver instance
driver = None

def get_driver():
    """Get or create Neo4j driver instance."""
    global driver
    if driver is None:
        driver = get_neo4j_driver(URI, AUTH)
    return driver

# =========================================
# HTML TEMPLATES (Consolidated)
# =========================================

MAIN_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Session-Based Recommender</title>
  <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.2/dist/css/bootstrap.min.css" rel="stylesheet">
  <style>
    body { background: #f8fafc; color: #0f172a; }
    .navbar { background: #2563eb; }
    .card { background: #ffffff; border: 1px solid #e5e7eb; }
    .table { color: #0f172a; }
    .table thead th { color: #1d4ed8; border-bottom-color: #e5e7eb; }
    .table tbody td { border-top-color: #e5e7eb; }
    .brand-gradient { background: linear-gradient(90deg, #2563eb, #a855f7); -webkit-background-clip: text; -webkit-text-fill-color: transparent; }
    .muted { color: #475569; }
    .footer { color: #64748b; }
  </style>
  <script>
    function gotoPredict(event) {
      event.preventDefault();
      const pid = document.getElementById('pidInput').value.trim();
      if (!pid) return;
      window.location.href = '/predict/' + encodeURIComponent(pid);
    }
  </script>
  </head>
<body>
  <nav class="navbar navbar-expand-lg navbar-dark">
    <div class="container">
      <a class="navbar-brand" href="/"><span class="brand-gradient fw-bold">Graph Recommender</span></a>
      <button class="navbar-toggler" type="button" data-bs-toggle="collapse" data-bs-target="#navbarsExample" aria-controls="navbarsExample" aria-expanded="false" aria-label="Toggle navigation">
        <span class="navbar-toggler-icon"></span>
      </button>
      <div class="collapse navbar-collapse" id="navbarsExample">
        <ul class="navbar-nav ms-auto mb-2 mb-lg-0">
          <li class="nav-item"><a class="nav-link" href="/start_session">Interactive Demo</a></li>
          <li class="nav-item"><a class="nav-link" href="/patterns">Patterns</a></li>
          <li class="nav-item"><a class="nav-link" href="/predict/119736">Try 119736</a></li>
        </ul>
      </div>
    </div>
  </nav>

  <main class="container py-5">
    <div class="row g-4">
      <div class="col-12 col-lg-8">
        <div class="card shadow-sm">
          <div class="card-body p-4">
            <h1 class="h3 mb-3">Session-Based Recommendation System</h1>
            <p class="muted mb-4">A co-occurrence graph approach inspired by "A Graph-based Method for Session-based Recommendations". All product and property values are numeric (hashed).</p>

            <form class="row gy-2 gx-3 align-items-center" onsubmit="gotoPredict(event)">
              <div class="col-auto">
                <label class="form-label" for="pidInput">Product ID</label>
                <input id="pidInput" type="number" class="form-control form-control-lg bg-dark text-light" placeholder="e.g. 119736" required />
              </div>
              <div class="col-auto pt-4">
                <button class="btn btn-primary btn-lg" type="submit">Get Recommendations</button>
              </div>
            </form>

            <hr class="my-4" />
            <div class="row text-center">
              <div class="col-12 col-md-4">
                <div class="p-3">
                  <div class="brand-gradient h2 mb-0">{{ mrr_score }}</div>
                  <div class="muted">MRR</div>
                </div>
              </div>
              <div class="col-12 col-md-4">
                <div class="p-3">
                  <div class="h2 mb-0">Co-occurrence</div>
                  <div class="muted">Real-time Top-K</div>
                </div>
              </div>
              <div class="col-12 col-md-4">
                <div class="p-3">
                  <div class="h2 mb-0">Patterns</div>
                  <div class="muted">Sequential (3-step)</div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>

      <div class="col-12 col-lg-4">
        <div class="card shadow-sm mb-3">
          <div class="card-body">
            <h2 class="h5">Quick Links</h2>
            <div class="d-grid gap-2">
              <a class="btn btn-outline-primary" href="/predict/119736">Predict for 119736</a>
              <a class="btn btn-outline-primary" href="/predict/186702">Predict for 186702</a>
              <a class="btn btn-outline-primary" href="/predict/40870">Predict for 40870</a>
              <a class="btn btn-outline-success" href="/start_session">Interactive Session</a>
              <a class="btn btn-outline-info" href="/patterns">Top Patterns</a>
              <a class="btn btn-outline-warning" href="/graph">Real-time Graph</a>
            </div>
          </div>
        </div>
        <div class="card shadow-sm">
          <div class="card-body">
            <h2 class="h5">About</h2>
            <p class="muted mb-0">MRR is computed using a 10% session split with the co-occurrence model. The graph includes Visitor, Session, Product, Category, PropertyType, and PropertyValue nodes.</p>
          </div>
        </div>
      </div>
    </div>
  </main>

  <footer class="container py-4 footer">
    <div class="text-center">Built with Neo4j, Flask, and Bootstrap.</div>
  </footer>
  <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.2/dist/js/bootstrap.bundle.min.js"></script>
</body>
</html>
"""

PREDICTION_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Recommendations for {{ current_pid }}</title>
  <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.2/dist/css/bootstrap.min.css" rel="stylesheet">
  <style>
    body { background: #f8fafc; color: #0f172a; }
    .navbar { background: #2563eb; }
    .card { background: #ffffff; border: 1px solid #e5e7eb; }
    .table { color: #0f172a; }
    .table thead th { color: #1d4ed8; border-bottom-color: #e5e7eb; }
    .table tbody td { border-top-color: #e5e7eb; }
    .brand-gradient { background: linear-gradient(90deg, #2563eb, #a855f7); -webkit-background-clip: text; -webkit-text-fill-color: transparent; }
  </style>
  </head>
<body>
  <nav class="navbar navbar-expand-lg navbar-dark">
    <div class="container">
      <a class="navbar-brand" href="/"><span class="brand-gradient fw-bold">Graph Recommender</span></a>
      <div class="collapse navbar-collapse"></div>
    </div>
  </nav>
  <main class="container py-5">
    <div class="card shadow-sm">
      <div class="card-body p-4">
        <div class="d-flex justify-content-between align-items-center mb-3">
          <h1 class="h4 mb-0">Recommendations for Product {{ current_pid }}</h1>
          <a class="btn btn-outline-light" href="/">Back</a>
        </div>
        {% if recommendations %}
        <div class="table-responsive">
          <table class="table align-middle">
            <thead>
              <tr>
                <th>Rank</th>
                <th>Recommended PID</th>
                <th>Co-occurrence</th>
                <th>Avg Time Diff</th>
                <th>Explain</th>
              </tr>
            </thead>
            <tbody>
              {% for rec in recommendations %}
              <tr>
                <td class="text-secondary">{{ loop.index }}</td>
                <td><span class="badge text-bg-primary">{{ rec[0] }}</span></td>
                <td>{{ rec[1] }}</td>
                <td>{{ "%.2f"|format(rec[2]/1000) }} s</td>
                <td>
                  <a class="btn btn-sm btn-outline-info" href="{{ url_for('explain', viewed_pid=current_pid, recommended_pid=rec[0]) }}">Why?</a>
                </td>
              </tr>
              {% endfor %}
            </tbody>
          </table>
        </div>
        {% else %}
          <div class="alert alert-warning">No recommendations found for this product.</div>
        {% endif %}
      </div>
    </div>
  </main>
  <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.2/dist/js/bootstrap.bundle.min.js"></script>
  </body>
  </html>
"""

EXPLANATION_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Explanation</title>
  <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.2/dist/css/bootstrap.min.css" rel="stylesheet">
  <style>
    body { background: #f8fafc; color: #0f172a; }
    .navbar { background: #2563eb; }
    .card { background: #ffffff; border: 1px solid #e5e7eb; }
    .brand-gradient { background: linear-gradient(90deg, #2563eb, #a855f7); -webkit-background-clip: text; -webkit-text-fill-color: transparent; }
  </style>
  </head>
<body>
  <nav class="navbar navbar-expand-lg navbar-dark">
    <div class="container">
      <a class="navbar-brand" href="/"><span class="brand-gradient fw-bold">Graph Recommender</span></a>
    </div>
  </nav>
  <main class="container py-5">
    <div class="card shadow-sm">
      <div class="card-body p-4">
        <div class="d-flex justify-content-between align-items-center mb-3">
          <h1 class="h4 mb-0">Why recommend {{ recommended_pid }} for {{ viewed_pid }}?</h1>
          <a class="btn btn-outline-light" href="{{ url_for('predict', pid=viewed_pid) }}">Back</a>
        </div>
        <pre class="p-3 bg-dark text-light rounded" style="white-space: pre-wrap;">{{ prompt_string }}</pre>
      </div>
    </div>
  </main>
  <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.2/dist/js/bootstrap.bundle.min.js"></script>
  </body>
  </html>
"""

PATTERNS_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Top Patterns</title>
  <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.2/dist/css/bootstrap.min.css" rel="stylesheet">
  <style>
    body { background: #f8fafc; color: #0f172a; }
    .navbar { background: #2563eb; }
    .card { background: #ffffff; border: 1px solid #e5e7eb; }
    .table { color: #0f172a; }
    .table thead th { color: #1d4ed8; border-bottom-color: #e5e7eb; }
    .table tbody td { border-top-color: #e5e7eb; }
  </style>
  </head>
<body>
  <nav class="navbar navbar-expand-lg navbar-dark">
    <div class="container">
      <a class="navbar-brand" href="/"><span class="brand-gradient fw-bold">Graph Recommender</span></a>
    </div>
  </nav>
  <main class="container py-5">
    <div class="card shadow-sm">
      <div class="card-body p-4">
        <div class="d-flex justify-content-between align-items-center mb-3">
          <h1 class="h4 mb-0">Top Recurring 3-Step Patterns</h1>
          <a class="btn btn-outline-light" href="/">Back</a>
        </div>
        {% if patterns %}
        <div class="table-responsive">
          <table class="table align-middle">
            <thead>
              <tr>
                <th>#</th>
                <th>Pattern (A → B → C)</th>
                <th>Count</th>
              </tr>
            </thead>
            <tbody>
              {% for pattern in patterns %}
              <tr>
                <td>{{ loop.index }}</td>
                <td><code>{{ pattern[0] }} → {{ pattern[1] }} → {{ pattern[2] }}</code></td>
                <td>{{ pattern[3] }}</td>
              </tr>
              {% endfor %}
            </tbody>
          </table>
        </div>
        {% else %}
          <div class="alert alert-warning">No patterns found.</div>
        {% endif %}
      </div>
    </div>
  </main>
  <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.2/dist/js/bootstrap.bundle.min.js"></script>
  </body>
  </html>
"""

# Real-time Graph Visualization Template
GRAPH_VIZ_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Real-time Graph Visualization</title>
  <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.2/dist/css/bootstrap.min.css" rel="stylesheet">
  <script type="text/javascript" src="https://unpkg.com/vis-network/standalone/umd/vis-network.min.js"></script>
  <style>
    body { background: #f8fafc; color: #0f172a; }
    .navbar { background: #2563eb; }
    .card { background: #ffffff; border: 1px solid #e5e7eb; }
    #graphContainer { height: 600px; border: 1px solid #e5e7eb; border-radius: 8px; }
    .controls { margin-bottom: 20px; }
    .status { margin-top: 10px; }
  </style>
</head>
<body>
  <nav class="navbar navbar-expand-lg navbar-dark">
    <div class="container">
      <a class="navbar-brand" href="/"><span class="brand-gradient fw-bold">Graph Recommender</span></a>
      <div class="navbar-nav ms-auto">
        <a class="nav-link" href="/">Dashboard</a>
        <a class="nav-link" href="/predict/119736">Predict</a>
        <a class="nav-link" href="/patterns">Patterns</a>
      </div>
    </div>
  </nav>
  
  <main class="container py-4">
    <div class="row">
      <div class="col-12">
        <div class="card shadow-sm">
          <div class="card-body">
            <div class="d-flex justify-content-between align-items-center mb-3">
              <h1 class="h4 mb-0">Real-time Graph Visualization</h1>
              <div class="controls">
                <button class="btn btn-primary btn-sm" onclick="loadGraph()">Refresh Graph</button>
                <button class="btn btn-success btn-sm" onclick="startLiveUpdates()">Start Live Updates</button>
                <button class="btn btn-warning btn-sm" onclick="stopLiveUpdates()">Stop Updates</button>
              </div>
            </div>
            
            <div class="row">
              <div class="col-md-8">
                <div id="graphContainer"></div>
                <div class="status">
                  <small class="text-muted">Status: <span id="status">Ready</span></small>
                </div>
              </div>
              <div class="col-md-4">
                <div class="card">
                  <div class="card-body">
                    <h5 class="card-title">Graph Info</h5>
                    <div id="graphInfo">
                      <p><strong>Nodes:</strong> <span id="nodeCount">-</span></p>
                      <p><strong>Edges:</strong> <span id="edgeCount">-</span></p>
                      <p><strong>Last Update:</strong> <span id="lastUpdate">-</span></p>
                    </div>
                  </div>
                </div>
                
                <div class="card mt-3">
                  <div class="card-body">
                    <h5 class="card-title">Live Recommendations</h5>
                    <div id="liveRecommendations">
                      <p class="text-muted">Click on a product node to see recommendations</p>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  </main>

  <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.2/dist/js/bootstrap.bundle.min.js"></script>
  <script src="https://cdnjs.cloudflare.com/ajax/libs/socket.io/4.0.1/socket.io.js"></script>
  
  <script>
    let network = null;
    let nodes = null;
    let edges = null;
    let liveUpdateInterval = null;
    let socket = io();
    
    // Initialize the graph
    function initGraph() {
      const container = document.getElementById('graphContainer');
      const data = { nodes: nodes, edges: edges };
      const options = {
        nodes: {
          shape: 'dot',
          size: 20,
          font: { size: 12, color: '#000000' },
          borderWidth: 2,
          shadow: true
        },
        edges: {
          width: 2,
          color: { inherit: 'from' },
          smooth: { type: 'continuous' }
        },
        physics: {
          stabilization: { iterations: 100 }
        },
        interaction: {
          hover: true,
          tooltipDelay: 200
        }
      };
      
      network = new vis.Network(container, data, options);
      
      // Add click event for recommendations
      network.on("click", function (params) {
        if (params.nodes.length > 0) {
          const nodeId = params.nodes[0];
          const node = nodes.get(nodeId);
          if (node && node.group === 'product') {
            showRecommendations(nodeId);
          }
        }
      });
    }
    
    // Load graph data from API
    function loadGraph() {
      document.getElementById('status').textContent = 'Loading...';
      fetch('/api/graph-data')
        .then(response => response.json())
        .then(data => {
          nodes = new vis.DataSet(data.nodes);
          edges = new vis.DataSet(data.edges);
          initGraph();
          updateGraphInfo();
          document.getElementById('status').textContent = 'Loaded';
        })
        .catch(error => {
          console.error('Error loading graph:', error);
          document.getElementById('status').textContent = 'Error loading graph';
        });
    }
    
    // Update graph information
    function updateGraphInfo() {
      document.getElementById('nodeCount').textContent = nodes.length;
      document.getElementById('edgeCount').textContent = edges.length;
      document.getElementById('lastUpdate').textContent = new Date().toLocaleTimeString();
    }
    
    // Show recommendations for a product
    function showRecommendations(productId) {
      fetch(`/api/recommendations/${productId}`)
        .then(response => response.json())
        .then(data => {
          const recDiv = document.getElementById('liveRecommendations');
          if (data.recommendations && data.recommendations.length > 0) {
            let html = `<h6>Recommendations for Product ${productId}:</h6><ul>`;
            data.recommendations.slice(0, 5).forEach(rec => {
              html += `<li>Product ${rec[0]} (Score: ${rec[1]})</li>`;
            });
            html += '</ul>';
            recDiv.innerHTML = html;
          } else {
            recDiv.innerHTML = '<p class="text-muted">No recommendations found</p>';
          }
        })
        .catch(error => {
          console.error('Error loading recommendations:', error);
        });
    }
    
    // Start live updates
    function startLiveUpdates() {
      if (liveUpdateInterval) return;
      liveUpdateInterval = setInterval(() => {
        socket.emit('request_update');
      }, 5000); // Update every 5 seconds
      document.getElementById('status').textContent = 'Live updates active';
    }
    
    // Stop live updates
    function stopLiveUpdates() {
      if (liveUpdateInterval) {
        clearInterval(liveUpdateInterval);
        liveUpdateInterval = null;
      }
      document.getElementById('status').textContent = 'Live updates stopped';
    }
    
    // Socket event handlers
    socket.on('graph_update', function(data) {
      if (nodes && edges) {
        nodes.update(data.nodes);
        edges.update(data.edges);
        updateGraphInfo();
      }
    });
    
    // Load initial graph
    loadGraph();
  </script>
</body>
</html>
"""

# New: LLM Prompt Page Template
PROMPT_TEMPLATE = """
<!DOCTYPE html>
<html lang=\"en\">
<head>
  <meta charset=\"utf-8\">
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">
  <title>LLM Prompt</title>
  <link href=\"https://cdn.jsdelivr.net/npm/bootstrap@5.3.2/dist/css/bootstrap.min.css\" rel=\"stylesheet\">
  <style>
    body { background: #f8fafc; color: #0f172a; }
    .navbar { background: #2563eb; }
    .card { background: #ffffff; border: 1px solid #e5e7eb; }
  </style>
  </head>
<body>
  <nav class=\"navbar navbar-expand-lg navbar-dark\">
    <div class=\"container\">
      <a class=\"navbar-brand\" href=\"/\">LLM Prompt</a>
    </div>
  </nav>
  <main class=\"container py-5\">
    <div class=\"card shadow-sm\">
      <div class=\"card-body p-4\">
        <form method=\"post\" class=\"mb-4\">
          <label for=\"prompt\" class=\"form-label\">Enter prompt for Gemini</label>
          <textarea id=\"prompt\" name=\"prompt\" class=\"form-control\" rows=\"6\" placeholder=\"Type your prompt...\">{{ default_prompt }}</textarea>
          <div class=\"mt-3\">
            <button class=\"btn btn-primary\" type=\"submit\">Submit</button>
            <a class=\"btn btn-outline-secondary\" href=\"/\">Back</a>
          </div>
        </form>
        {% if output %}
        <h2 class=\"h5\">LLM Output</h2>
        <pre class=\"p-3 bg-light\" style=\"white-space: pre-wrap;\">{{ output }}</pre>
        {% endif %}
      </div>
    </div>
  </main>
  <script src=\"https://cdn.jsdelivr.net/npm/bootstrap@5.3.2/dist/js/bootstrap.bundle.min.js\"></script>
  </body>
  </html>
"""
SESSION_DEMO_TEMPLATE = """

<!DOCTYPE html>
<html>
<head>
    <title>Interactive Session Simulation</title>
    <style>
        /* ... Styles ... */
        .session-history { border: 1px solid #ccc; padding: 15px; margin-bottom: 20px; background-color: #e6f7ff; border-radius: 5px; }
        .product-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(150px, 1fr)); gap: 10px; margin-top: 15px; }
        .product-btn { padding: 10px; background: #007bff; color: white; text-align: center; border-radius: 5px; text-decoration: none; display: block; }
        .product-btn:hover { background: #0056b3; }
        .prediction-section { margin-top: 30px; border-top: 2px solid #28a745; padding-top: 20px; }
        .table-embed { padding: 0 20px; } /* New class to contain the embedded table */
        table { width: 100%; border-collapse: collapse; margin-top: 20px; }
        th, td { border: 1px solid #ddd; padding: 12px; text-align: left; }
        th { background-color: #f2f2f2; }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>Interactive Session Simulation (Real-Time Demo)</h1>
            <p><strong>Visitor ID: DUMMY_USER</strong></p>
        </div>
        
        <div class="back-link">
            <a href="{{ url_for('start_session') }}">← START NEW SESSION (Reset)</a>
        </div>
        
        <div class="session-history">
            <h3>Current Session History ({{ session_history|length }} Clicks):</h3>
            <p>{{ session_history }}</p>
        </div>
        
        {% if last_pid %}
        <div class="prediction-section">
            <h2>Live Recommendation for PID: {{ last_pid }}</h2>
            <p>Prediction triggered after last action: <strong>{{ last_action_type }}</strong> on Product <strong>{{ last_pid }}</strong>.</p>
            
            {% if recommendations %}
                <div class="table-embed">
                    <!-- The embedded table is now passed directly as HTML string -->
                    {{ prediction_table | safe }}
                </div>
            {% else %}
                <p>No co-occurrence recommendations found for this item.</p>
            {% endif %}
        </div>
        {% else %}
        <h2>Start Your Session:</h2>
        {% endif %}

        <div class="links">
            <h3>Available Products to Interact With:</h3>
            <div class="product-grid">
                {% for pid in DEMO_PRODUCTS %}
                    <a class="product-btn" href="{{ url_for('user_action', pid=pid, action_type='view') }}">View PID {{ pid }}</a>
                {% endfor %}
            </div>
        </div>
    </div>
</body>
</html>
"""


# =========================================
# FLASK ROUTES
# =========================================

@app.route('/')
def index():
    """Main dashboard."""
    return render_template_string(MAIN_TEMPLATE, mrr_score="0.2503")

# --- INTERACTIVE SESSION ROUTES ---
@app.route('/start_session')
def start_session():
    """Starts a new dummy session."""
    session.pop('history', None) 
    # Add a random starting product to give the user something to build a session on
    session['history'] = [{'pid': random.choice(DEMO_PRODUCTS), 'type': 'view'}]
    return redirect(url_for('session_demo'))

@app.route('/action/<int:pid>/<action_type>')
def user_action(pid, action_type):
    """Adds an action to the session and redirects to the demo page."""
    if 'history' not in session:
        session['history'] = []
    
    session['history'].append({'pid': pid, 'type': action_type})
    
    return redirect(url_for('session_demo'))

@app.route('/session_demo')
def session_demo():
    """Main page showing session history and live recommendation (Interactive)."""
    history = session.get('history', [])
    
    if not history:
        return redirect(url_for('start_session'))

    last_item = history[-1]
    last_pid = last_item['pid']
    last_action_type = last_item['type']
    
    recs_list = [] # List of tuples: (pid, count, duration)
    prediction_table = "" # HTML string of the table
    
    # LIVE PREDICTION BLOCK: Corrected logic to generate the embedded table
    if last_pid:
        try:
            driver = get_driver()
            recs_list = get_next_item_prediction(driver, last_pid, k=5) 
            
            if recs_list:
                # 1. Render the PREDICTION_TEMPLATE to get the full HTML output
                prediction_full_html = render_template_string(
                    PREDICTION_TEMPLATE, 
                    current_pid=last_pid, 
                    recommendations=recs_list # Pass the correct list format
                )
                
                # 2. Extract ONLY the necessary table portion to embed it.
                # Find the start of the table content (after the back link/header)
                # This is fragile but necessary when not using proper template files.
                table_start_marker = '<div class="header">' 
                
                # Find the end of the container
                container_end_marker = '</div>' 
                
                # This is a HACK to safely extract the table portion and prevent HTML nesting issues.
                # A proper solution uses Flask's template rendering system.
                # Since we are using render_template_string, this hack minimizes the full-page render.
                
                # For safety, let's just render the table rows/header and omit the full HTML tags.
                table_content = f"""
                <table>
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
                        { "".join([f'<tr><td class="rank">{i+1}</td><td><strong>{rec[0]}</strong></td><td class="popularity">{rec[1]}</td><td>{rec[2]/1000:.2f}s</td><td><a class="explain-btn" href="{url_for('explain', viewed_pid=last_pid, recommended_pid=rec[0])}">Explain Why</a></td></tr>' 
                                for i, rec in enumerate(recs_list)]) }
                    </tbody>
                </table>
                """
                prediction_table = table_content

            
        except Exception as e:
            prediction_table = f"<p style='color:red;'>Error retrieving live recommendations: {str(e)}</p>"


    return render_template_string(SESSION_DEMO_TEMPLATE, 
                                  DEMO_PRODUCTS=DEMO_PRODUCTS,
                                  session_history=[f"PID: {item['pid']} ({item['type']})" for item in history], 
                                  last_pid=last_pid,
                                  last_action_type=last_action_type,
                                  recommendations=recs_list, 
                                  prediction_table=prediction_table)
# --- END INTERACTIVE SESSION ROUTES ---


@app.route('/predict/<int:pid>')
def predict(pid):
    """Static prediction route."""
    try:
        driver = get_driver()
        recommendations = get_next_item_prediction(driver, pid, k=10)
        return render_template_string(PREDICTION_TEMPLATE, current_pid=pid, recommendations=recommendations)
    except Exception as e:
        return f"Error: {str(e)}", 500

@app.route('/explain/<int:viewed_pid>/<int:recommended_pid>')
def explain(viewed_pid, recommended_pid):
    """Hybrid LLM prompt generation route."""
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
        
        return render_template_string(EXPLANATION_TEMPLATE, 
                                    viewed_pid=viewed_pid, 
                                    recommended_pid=recommended_pid,
                                    prompt_string=llm_output)
    except Exception as e:
        return f"Error generating explanation: {str(e)}", 500

@app.route('/patterns')
def patterns():
    """Recurring patterns route."""
    try:
        driver = get_driver()
        patterns = find_recurring_patterns(driver, limit=5)
        return render_template_string(PATTERNS_TEMPLATE, patterns=patterns)
    except Exception as e:
        return f"Error: {str(e)}", 500

@app.route('/prompt', methods=['GET', 'POST'])
def prompt_page():
    """Simple page to accept a prompt and show Gemini output."""
    output = None
    default_prompt = "Explain how our co-occurrence graph generates next-item recommendations."
    if 'POST' == __import__('flask').request.method:
        prompt_text = __import__('flask').request.form.get('prompt') or ''
        try:
            output = generate_llm_output(prompt_text)
        except Exception as e:
            output = f"LLM error: {str(e)}"
    return render_template_string(PROMPT_TEMPLATE, output=output, default_prompt=default_prompt)

@app.route('/graph')
def graph_visualization():
    """Real-time graph visualization page."""
    return render_template_string(GRAPH_VIZ_TEMPLATE)

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
        LIMIT 100
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
                'width': min(weight / 10, 10),  # Scale width
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

# WebSocket events
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
        LIMIT 100
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

if __name__ == '__main__':
    # Run the app nicely
    print("Starting Session-Based Recommendation Demo...")
    print("Open http://localhost:5000/start_session in your browser.")
    print("Real-time Graph: http://localhost:5000/graph")
    socketio.run(app, debug=True, host='0.0.0.0', port=5000)
    
