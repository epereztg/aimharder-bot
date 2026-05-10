import os
import subprocess
import json
from http.server import BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
from datetime import datetime
import pytz

class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        # Authenticate Vercel Cron request using a secret key
        # You should set CRON_SECRET in Vercel Environment Variables
        auth_header = self.headers.get("Authorization")
        cron_secret = os.environ.get("CRON_SECRET")
        
        if cron_secret and auth_header != f"Bearer {cron_secret}":
            self.send_response(401)
            self.end_headers()
            self.wfile.write(b"Unauthorized: Invalid CRON_SECRET")
            return

        parsed = urlparse(self.path)
        qs = parse_qs(parsed.query)
        
        box_suffix = qs.get("box", ["10002"])[0]
        days_ahead = qs.get("days", ["2"])[0]
        
        schedule_file = f"schedule_{box_suffix}.json"
        
        # Point to the root directory where main.py is (assuming api/cron.py is deployed from root)
        # In Vercel, the current working directory is usually the project root
        cmd = [
            "python", "main.py",
            "--days-ahead", days_ahead,
            "--schedule", schedule_file,
            "--skip-wait" # Critical! Vercel Serverless times out after 10-60s, so we must skip sleeping!
        ]
        
        try:
            # We add all Vercel environment variables directly to the subprocess child
            result = subprocess.run(cmd, capture_output=True, text=True, check=False)
            status = 200 if result.returncode == 0 else 500
            
            response_data = {
                "success": result.returncode == 0,
                "stdout": result.stdout,
                "stderr": result.stderr
            }
            
            self.send_response(status)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps(response_data).encode("utf-8"))
            
        except Exception as e:
            self.send_response(500)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({"error": str(e)}).encode("utf-8"))
