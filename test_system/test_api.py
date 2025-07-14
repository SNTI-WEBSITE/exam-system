import requests

# Step 4A: Start Pre-Test Window
print("\n--- Starting Pre-Test Window ---")
res = requests.post("http://localhost:5000/start_pre_test", headers={"Content-Type": "application/json"}, json={})
try:
    print(res.json())
except Exception:
    print("Response was not JSON:", res.text)

# Step 4B: Student Login
print("\n--- Logging In Student ---")
res = requests.post("http://localhost:5000/student_login", json={"personal_number": "123456"})
try:
    print(res.json())
except Exception:
    print("Response was not JSON:", res.text)

# Step 5A: Start Test
print("\n--- Starting Test for Student ---")
res = requests.post("http://localhost:5000/start_test", json={"personal_number": "123456", "num_questions": 4})
try:
    print(res.json())
except Exception:
    print("Response was not JSON:", res.text)
