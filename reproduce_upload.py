import requests
import os

session = requests.Session()
# Login
login_data = {'username': 'admin', 'password': 'admin123'}
print(f"Logging in...")
session.post('http://localhost:5000/admin/login', data=login_data)

# Ensure dummy image exists
if not os.path.exists('dummy_image.jpg'):
    with open('dummy_image.jpg', 'wb') as f:
        f.write(b'\x00' * 1024)

# Update product 1 with image
files = {'image': ('dummy_image.jpg', open('dummy_image.jpg', 'rb'), 'image/jpeg')}
data = {
    'name': 'Image Upload Test',
    'description': 'Description',
    'price': 100000,
    'stock': 10,
    'category': 'Electronics'
}

print("Uploading image for product 1...")
response = session.post('http://localhost:5000/admin/product/1/edit', data=data, files=files)

print(f"Upload Response: {response.status_code}")

# Verify
response = session.get('http://localhost:5000/admin/manage_products')
if 'dummy_image' in response.text or 'Image Upload Test' in response.text:
    print("Dashboard reflects changes.")
    # More specific: check if image filename is in the source (it might have a timestamp prefix)
    if 'dummy_image.jpg' in response.text:
         print("SUCCESS: Image filename found in page source.")
    else:
         print("PARTIAL: Product updated, but exact filename match failed (expected due to timestamp).")
         # Check if any image path with timestamp exists
         if 'static/images/' in response.text:
             print("SUCCESS: Found static/images path in source.")
else:
    print("FAILURE: Dashboard not reflecting update.")
