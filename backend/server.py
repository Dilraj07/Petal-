from flask import Flask, request, Response
from flask_cors import CORS
import subprocess
import os

app = Flask(__name__, static_folder='../frontend', static_url_path='')
CORS(app)

BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))
BASE_DIR = os.path.dirname(BACKEND_DIR)

@app.route('/')
def index():
    return app.send_static_file('report/index.html')

@app.route('/compile', methods=['GET', 'POST'])
def compile_code():
    if request.method == 'POST':
        data = request.json or {}
    else:
        data = request.args
        
    source_code = data.get('source_code', '')
    tdp = data.get('tdp', None)
    optimize = data.get('optimize', 'energy')
    
    # Save the incoming source code to a file
    test_dir = os.path.join(BASE_DIR, "data", "test_workloads")
    os.makedirs(test_dir, exist_ok=True)
    test_file = os.path.join(test_dir, "matrix_mult.c")
    
    with open(test_file, "w", encoding="utf-8") as f:
        f.write(source_code)
        
    def generate():
        main_py = os.path.join(BACKEND_DIR, "main.py")
        cmd = ["python3", "-u", main_py, test_file, f"--optimize={optimize}"]
        if tdp:
            cmd.append(f"--tdp={tdp}")
            
        # Run main.py and stream output line by line
        process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)
        
        for line in iter(process.stdout.readline, ''):
            line = line.strip()
            if line:
                import time
                time.sleep(0.5) # Add a tiny realistic delay for the "compilation feeling"
            yield f"data: {line}\n\n"
            
        process.stdout.close()
        process.wait()
        
        # Finally, read the optimized code and send it as an event
        opt_file = test_file.replace(".c", "_optimized.c")
        if os.path.exists(opt_file):
            with open(opt_file, "r", encoding="utf-8") as f:
                opt_code = f.read()
            # Encode optimized code so it doesn't break SSE framing
            import json
            yield f"event: optimized_code\ndata: {json.dumps({'code': opt_code})}\n\n"
            
        yield f"event: done\ndata: done\n\n"

    return Response(generate(), mimetype='text/event-stream')

if __name__ == '__main__':
    # Ensure test_workloads directory exists
    test_dir = os.path.join(BASE_DIR, "data", "test_workloads")
    os.makedirs(test_dir, exist_ok=True)
    app.run(debug=True, port=5000)
