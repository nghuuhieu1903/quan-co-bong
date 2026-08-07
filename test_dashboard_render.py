import requests

session = requests.Session()
# Login first
login_data = {'username': 'admin', 'password': 'admin123'}
response = session.post('http://localhost:5000/admin/login', data=login_data)
print(f"Login Status: {response.status_code}")

# Get dashboard
response = session.get('http://localhost:5000/admin/dashboard')
print(f"Dashboard Status: {response.status_code}")

if response.status_code == 200 and "Initial Last Order ID:" in response.text:
    print("SUCCESS: Dashboard rendered and script found.")
else:
    print(f"FAILURE: {response.status_code} - {response.text[:100]}")
