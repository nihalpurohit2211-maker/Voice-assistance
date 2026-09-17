import subprocess
import time
import requests
import os

env = os.environ.copy()
env["FRONTEND_URL"] = "https://my-vercel-app.vercel.app"

p = subprocess.Popen([".venv/Scripts/uvicorn.exe", "backend.main:app", "--port", "8005"], env=env)
time.sleep(3)

try:
    headers = {
        "Origin": "https://my-vercel-app.vercel.app",
        "Access-Control-Request-Method": "POST"
    }
    resp = requests.options("http://localhost:8005/auth/login", headers=headers)
    print("STATUS:", resp.status_code)
    print("HEADERS:")
    for k, v in resp.headers.items():
        print(f"{k}: {v}")
finally:
    p.terminate()
