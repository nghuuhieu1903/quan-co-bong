from flask import Flask, render_template
from datetime import datetime

app = Flask(__name__)
app.secret_key = 'test'

# Mock objects
class MockOrder:
    def __init__(self, id, total, status):
        self.id = id
        self.total_amount = total
        self.status = status
        self.created_at = datetime.now()
        self.customer_name = "Test"
        self.customer_phone = "123"

class MockProduct:
    def __init__(self):
        self.id = 1
        self.name = "Test"

class MockAutomation:
    enabled = True

class MockSpeaker:
    enabled = True

@app.route('/')
def index(): return ""

@app.route('/test')
def test_render():
    try:
        products = [MockProduct()]
        orders = [MockOrder(1, 100000, 'pending')]
        
        # Add session mock
        from flask import session
        session['admin_username'] = 'admin'
        
        return render_template('admin_dashboard.html', 
                             products=products, 
                             orders=orders, 
                             automation=MockAutomation(), 
                             laptop_speaker=MockSpeaker())
    except Exception as e:
        import traceback
        traceback.print_exc()
        return str(e), 500

# Dummy routes for template
@app.route('/manage_products')
def manage_products(): return ""
@app.route('/products')
def products(): return ""
@app.route('/add_product')
def add_product(): return ""
@app.route('/automation_settings')
def automation_settings(): return ""
@app.route('/generate_qr')
def generate_qr(): return ""
@app.route('/export_orders')
def export_orders(): return ""
@app.route('/admin/order/<int:order_id>/update', methods=['POST'])
def update_order_status(order_id): return ""


if __name__ == '__main__':
    app.run(port=5001)
