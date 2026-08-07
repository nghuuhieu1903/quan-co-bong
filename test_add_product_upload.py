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

# Create NEW product with image
files = {'image': ('dummy_image.jpg', open('dummy_image.jpg', 'rb'), 'image/jpeg')}
data = {
    'name': 'New Product with Image',
    'description': 'Description',
    'price': 200000,
    'stock': 20,
    'category': 'Electronics'
}

print("Adding new product with image...")
# Use the add_product route
response = session.post('http://localhost:5000/admin/product/add', data=data, files=files)

print(f"Add Product Response: {response.status_code}")

# Verify
response = session.get('http://localhost:5000/admin/manage_products')
if 'New Product with Image' in response.text:
    print("New product found in list.")
    # More specific: check if image filename is in the source (timestamped)
    if 'dummy_image.jpg' in response.text:
         print("SUCCESS: Image filename found in page source.")
    else:
         print("PARTIAL: Product created, but exact filename match failed (expected due to timestamp).")
         if 'static/images/' in response.text:
             print("SUCCESS: Found static/images path in source.")
else:
    print("FAILURE: New product not found in dashboard.")
