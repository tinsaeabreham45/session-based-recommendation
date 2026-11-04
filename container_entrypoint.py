"""Container entrypoint for the existing Flask/SocketIO application.

The application module (src/app.py) still owns all configuration and routes.
This entrypoint only supplies the runtime options that flask-socketio requires
when it is not running behind an async server:

* ``allow_unsafe_werkzeug=True`` - needed by Flask-SocketIO 5.x when the
  Werkzeug development server is used outside an interactive terminal.
* ``debug=False`` / ``use_reloader=False`` - the auto-reloader is not useful
  inside a container and would start a second process.
"""

from src.app import app, socketio


if __name__ == "__main__":
    socketio.run(
        app,
        host="0.0.0.0",
        port=5000,
        debug=False,
        use_reloader=False,
        allow_unsafe_werkzeug=True,
    )
