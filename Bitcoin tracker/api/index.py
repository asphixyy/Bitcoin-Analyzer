import sys
import os

# Add the project root directory to the Python path
# This allows server.py and its dependencies (analysis_engine, etc.) to be imported correctly.
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(project_root)

# Import the Flask app instance from server.py
from server import app
