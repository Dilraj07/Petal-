from flask import Flask, request, Response, send_from_directory
from flask_cors import CORS
import subprocess
import os
import tempfile
import json
import time

app = Flask(__name__, static_folder='../frontend', static_url_path='')
CORS(app)

BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))
BASE_DIR = os.path.dirname(BACKEND_DIR)

@app.route('/')
def index():
    return send_from_directory(os.path.join(BASE_DIR, 'frontend'), 'report/index.html')

@app.route('/compile', methods=['GET', 'POST'])
def compile_code():
    if request.method == 'POST':
        data = request.json or {}
    else:
        data = request.args
        
    source_code = data.get('source_code', '')
    
    # Validate non-empty source code
    if not source_code or not source_code.strip():
        return Response(f"event: error\ndata: {{\"error\": \"Source code cannot be empty\"}}\n\n", status=400, mimetype='text/event-stream')
    
    tdp = data.get('tdp', None)
    optimize = data.get('optimize', 'energy')
    policy = data.get('policy', 'balanced')
    collector = data.get('collector', 'auto')
    try:
        runs = max(1, min(int(data.get('runs', 5)), 10))  # client-controlled, capped at 10
    except (ValueError, TypeError):
        runs = 5
    
    # Save the incoming source code to a file
    test_dir = os.path.join(BASE_DIR, "data", "test_workloads")
    os.makedirs(test_dir, exist_ok=True)
    fd, test_file = tempfile.mkstemp(prefix="matrix_mult_", suffix=".c", dir=test_dir, text=True)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(source_code)
        
        def generate():
            main_py = os.path.join(BACKEND_DIR, "main.py")
            root, _ = os.path.splitext(test_file)
            opt_file = f"{root}_optimized.c"
            output_bin = f"{root}_petal_out"
            metadata_file = f"{root}_run_metadata.json"
            if os.name == "nt":
                output_bin += ".exe"
            import sys
            cmd = [
                sys.executable,
                "-u",
                main_py,
                test_file,
                f"--optimize={optimize}",
                f"--policy={policy}",
                f"--collector={collector}",
                f"--output-bin={output_bin}",
                f"--metadata-file={metadata_file}",
                f"--runs={runs}",
            ]
            if tdp:
                cmd.append(f"--tdp={tdp}")
                
            process = None
            try:
                # Run main.py and stream output line by line
                process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)
                
                for line in iter(process.stdout.readline, ''):
                    line = line.strip()
                    if line.startswith("@@RUN_UPDATE@@: "):
                        run_update_data = line.replace("@@RUN_UPDATE@@: ", "")
                        yield f"event: run_update\ndata: {run_update_data}\n\n"
                        continue

                    if line:
                        time.sleep(0.1)  # Add a tiny realistic delay for the "compilation feeling"
                    yield f"data: {line}\n\n"
                    
                process.stdout.close()
                process.wait()

                # Surface pipeline failure to the client
                if process.returncode != 0:
                    yield f"data: [Petal] Pipeline exited with code {process.returncode}\n\n"

                # Send optimized source if generated
                if os.path.exists(opt_file):
                    with open(opt_file, "r", encoding="utf-8") as f:
                        opt_code = f.read()
                    # Encode optimized code so it doesn't break SSE framing
                    yield f"event: optimized_code\ndata: {json.dumps({'code': opt_code})}\n\n"

                metadata = {}
                if os.path.exists(metadata_file):
                    with open(metadata_file, "r", encoding="utf-8") as f:
                        metadata = json.load(f)
                    yield f"event: run_metadata\ndata: {json.dumps(metadata)}\n\n"
            finally:
                if process and process.poll() is None:
                    process.kill()
                for path in (test_file, opt_file, output_bin, metadata_file):
                    if os.path.exists(path):
                        try:
                            os.remove(path)
                        except OSError:
                            pass
                pipeline_ok = process is None or process.returncode == 0
                done_payload = {
                    "status": "ok" if pipeline_ok else "error",
                    "error": None if pipeline_ok else f"Pipeline exited with code {process.returncode}",
                    "comparison": metadata.get("comparison", {}),
                    "correctness": metadata.get("correctness", {})
                }
                yield f"event: done\ndata: {json.dumps(done_payload)}\n\n"

    return Response(generate(), mimetype='text/event-stream')

if __name__ == '__main__':
    # Ensure test_workloads directory exists
    test_dir = os.path.join(BASE_DIR, "data", "test_workloads")
    os.makedirs(test_dir, exist_ok=True)
    debug_mode = os.getenv('PETAL_DEBUG', 'false').lower() == 'true'
    app.run(debug=debug_mode, port=5000)
