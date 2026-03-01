from flask import Flask, request, Response
from flask_cors import CORS
import subprocess
import os

app = Flask(__name__)
CORS(app)

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
    test_file = "../data/matrix_mult.c"
    with open(test_file, "w") as f:
        f.write(source_code)
        
    def generate():
        cmd = ["python", "-u", "main.py", test_file, f"--optimize={optimize}"]
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
            with open(opt_file, "r") as f:
                opt_code = f.read()
            # Encode optimized code so it doesn't break SSE framing
            import json
            yield f"event: optimized_code\ndata: {json.dumps({'code': opt_code})}\n\n"
            
        yield f"event: done\ndata: done\n\n"

    return Response(generate(), mimetype='text/event-stream')

if __name__ == '__main__':
    # Ensure test_workloads directory exists
    os.makedirs("test_workloads", exist_ok=True)
    app.run(debug=True, port=5000)
