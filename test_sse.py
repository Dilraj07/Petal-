import requests
import sys

url = "http://127.0.0.1:5000/compile"
data = {"source_code": "int main() { return 0; }", "runs": 1}

print("Sending request to server...")
try:
    with requests.post(url, json=data, stream=True) as r:
        for line in r.iter_lines():
            if line:
                print(line.decode('utf-8'))
    print("Done!")
except Exception as e:
    print(f"Error: {e}")
    sys.exit(1)
