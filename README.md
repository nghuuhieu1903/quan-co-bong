# E-Commerce Website

A modern e-commerce website built with Flask, featuring separate admin and customer interfaces with **Light/Dark Mode** and **Modern UI Design**.

## 🎨 New Features - Modern UI

### 🌓 Light/Dark Mode Toggle
- **Smart Theme Switching**: Toggle between light and dark modes with a single click
- **Persistent Theme**: Theme preference saved in localStorage
- **Smooth Transitions**: Beautiful animations when switching themes
- **Adaptive Colors**: All UI elements adapt to the selected theme

### 🎯 Modern Design System
- **Gradient Backgrounds**: Beautiful gradient effects throughout the interface
- **Card-Based Layout**: Clean, organized card components
- **Responsive Grid**: Mobile-first responsive design
- **Micro-interactions**: Hover effects, transitions, and animations
- **Modern Typography**: Clean, readable fonts with proper hierarchy

### 🎭 Enhanced Components
- **Interactive Buttons**: Animated buttons with hover states and loading indicators
- **Smart Forms**: Real-time validation and feedback
- **Data Tables**: Sortable, responsive tables with modern styling
- **Status Badges**: Color-coded badges for different states
- **Alert System**: Beautiful notification system with auto-dismiss

## 🚀 Features

### Admin Panel
- **Modern Dashboard**: Real-time statistics and quick actions
- **Secure Login**: Session-based authentication
- **Product Management**: Add, edit, enable/disable products
- **Order Management**: View and update order status
- **Advanced Automation**: 
  - **gTTS Integration**: High-quality Vietnamese text-to-speech
  - **pyttsx3 Fallback**: Offline Windows TTS support
  - **Voice Settings**: Customizable voice rate, volume, and model
  - **Smart Notifications**: Order announcements with Vietnamese support
- **QR Code Generation**: Create QR codes for products
- **System Monitoring**: Real-time system status indicators

### Customer Interface
- **Modern Homepage**: Hero section with featured products
- **Product Catalog**: Advanced filtering and search
- **Shopping Cart**: Real-time cart management with animations
- **Secure Checkout**: Simple, streamlined checkout process
- **Order Confirmation**: Clear order summary and status

### 🎵 Text-to-Speech System
- **Dual Engine Support**: gTTS (online) + pyttsx3 (offline)
- **Vietnamese Optimization**: Perfect pronunciation for Vietnamese text
- **Admin Controls**: Easy switching between engines
- **Error Handling**: Automatic fallback and graceful degradation
- **Unicode Safe**: Proper handling of Vietnamese characters

## 🛠️ Technology Stack

### Backend
- **Flask**: Web framework
- **SQLAlchemy**: Database ORM
- **Flask-Session**: Session management
- **gTTS**: Google Text-to-Speech
- **pyttsx3**: Offline TTS engine
- **pygame**: Audio playback for gTTS

### Frontend
- **Modern CSS3**: Custom properties, Grid, Flexbox
- **Responsive Design**: Mobile-first approach
- **Font Awesome**: Icon library
- **Google Fonts**: Modern typography (Inter)
- **Vanilla JavaScript**: No heavy frameworks needed

### Database
- **MySQL**: Set via the `DATABASE_URL` environment variable (e.g. `mysql+pymysql://user:password@host:3306/dbname`)

## 📁 Project Layout

`app.py` is an application factory; the code it wires together lives in these
modules:

| File | Contains |
|---|---|
| `app.py` | `create_app()` - config, extensions, blueprint registration |
| `extensions.py` | The `db` / `sess` objects, created unbound to avoid circular imports |
| `models.py` | The 13 SQLAlchemy models and `create_notification()` |
| `translations.py` | The VI/EN strings for the customer-facing pages |
| `helpers.py` | Console printing, SMTP email, image uploads |
| `decorators.py` | `admin_required`, `super_admin_required`, `manager_required`, … |
| `automation.py` | `LaptopSpeaker` and `AutomationController` (all optional deps) |
| `db_init.py` | `ensure_column()` migrations and first-run seed data |
| `blueprints/public.py` | Home, catalogue, rooms, cart, checkout |
| `blueprints/auth.py` | Admin + customer sign-in, sign-out, password recovery |
| `blueprints/admin.py` | Everything under `/admin` |
| `blueprints/menu.py` | The daily food menu |

Because the routes are blueprints now, `url_for` needs the blueprint name:
`url_for('admin.admin_dashboard')`, not `url_for('admin_dashboard')`. The URLs
themselves are unchanged.

### Adding a database column

There is no Alembic. Add the column to the model, then add a matching
`ensure_column(...)` line in `db_init.py` - it runs an idempotent `ALTER TABLE`
on every startup so existing databases pick the column up.

## 🔒 CSRF Protection

Every state-changing request needs a CSRF token; without one the app answers
`400`. Forms get theirs from a hidden field:

```html
<form method="POST" action="...">
    <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
```

**Any new POST form needs that line** - leaving it out means the form silently
stops working. `test_csrf.py` renders the pages and fails if a form is missing
one, so run it after adding a form.

JavaScript that POSTs reads the token from the meta tag in the base templates
and sends it as a header:

```js
fetch(url, {
    method: 'POST',
    headers: {'X-CSRFToken': document.querySelector('meta[name="csrf-token"]').content}
})
```

## 🔎 Editing the SEO text

`/admin/seo` (super admin only) edits the shop details and the title and
description search engines show, without touching code: name, description,
phone, address, opening hours, price range, map link and coordinates, plus a
title/description override per public page.

Every setting has a built-in default in `seo.DEFAULTS`. Clearing a field
deletes the override and the site falls back to that default, so an empty
`site_setting` table renders exactly what the hard-coded version did - there
is no state where the site ends up with a blank name.

The page shows a live preview of the Google result and counts characters
against the lengths Google truncates at (60 for a title, 160 for a
description).

The share image can be uploaded from the same page. Uploads are cropped to
cover 1200x630 - the shape Facebook and Zalo render a link preview at - so a
square or portrait photo is centre-cropped here rather than being cut
unpredictably by each platform. A file that is not an image, or is smaller
than 600x315, is refused and the current image is left alone. "Dùng lại ảnh
mặc định" deletes the upload and falls back to the generated card, which
still comes from `tools/make_icons.py`.

The favicon and app icons can be replaced the same way: upload one logo and
all six sizes plus the `.ico` are generated from it, centre-cropped square.

Uploaded files (`static/icons/og-custom.jpg`, `static/icons/custom-*`) are
deliberately not tracked in git: they belong to the running site, not the
source, and this also keeps a `git pull` from overwriting them.

**The app has to be able to write to `static/icons`.** If it cannot, the page
says so and nothing is overwritten. On a server where the code was pulled as
root but the app runs as another user, grant it:

```bash
cd /www/wwwroot/quan-co-bong
APPUSER=$(ps -eo user,args | grep "[g]unicorn" | grep quan-co-bong | head -1 | awk '{print $1}')
chown -R "$APPUSER" static/icons static/images
```

## 🔑 Sessions and SECRET_KEY

`SECRET_KEY` signs the session cookie, and the cookie is what says
`admin_role=super_admin`. The example value is committed to this repository,
so anyone could forge a valid admin cookie against a deployment still using
it. The app therefore refuses the known example values: if `SECRET_KEY` is
unset or unchanged it generates a random key for the process and logs a
warning. That costs you sessions on restart rather than the admin account -
**set a real one in `.env` before deploying**:

```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

The session cookie is `HttpOnly` and `SameSite=Lax`. Set
`SESSION_COOKIE_SECURE=1` once the site is behind HTTPS.

## 💳 Bank transfer (QR)

Set the shop's account in `.env` and a "Chuyển khoản QR" option appears at
checkout; leave it blank and cash stays the only method, because showing a
customer a QR that pays nobody is worse than not offering it at all:

```bash
SHOP_BANK_ID=970436          # Vietcombank; codes at https://vietqr.io
SHOP_BANK_ACCOUNT_NO=1234567890
SHOP_BANK_ACCOUNT_NAME=QUAN CO BONG
```

The QR comes from VietQR with the amount and description already filled in.
The description is what the shop matches a payment against:

| Who ordered | Transfer content |
|---|---|
| Gave a name | `NGUYEN VAN AN DH25` |
| Ordered anonymously | `DH25` |

`DH<id>` is the order number, and it is always present - it is the part that
identifies the payment. Names are folded to unaccented capitals because
Vietnamese banking apps commonly drop or garble diacritics in a transfer
description, and the whole string is trimmed to 50 characters, keeping the
code. Account details live in the environment, not the database, so an admin
session cannot redirect payments to another account.

## 🧾 Who can see an order

`/order_confirmation/<id>` shows a customer's name and phone, and order ids
are sequential, so it checks who is asking: the browser that placed the order
(the id is kept in its session) or a signed-in admin. Anyone else gets a 404.
`test_security.py` performs the enumeration attack and fails if it works.

## 📋 Logging

Error handlers call `logger.exception(...)`, which records the message *and*
the traceback, so a failure says where it happened. Output goes to stderr;
set `LOG_LEVEL=DEBUG` for more detail.

## ✅ Tests

`test_smoke_routes.py` requests every GET route twice - once as a signed-in
admin, once anonymously - and compares the status codes against a recorded
baseline. Run it before and after any refactor:

```bash
python test_smoke_routes.py --save   # record current behaviour
python test_smoke_routes.py          # report anything that changed
python test_csrf.py                  # CSRF is on and forms still work
python test_flows.py                 # 38 real write paths, end to end
python test_security.py              # each fix, verified by running the attack
python test_payments.py              # QR + transfer-content rules
python test_seo.py                   # metadata, sitemap, icons
python test_seo_admin.py             # settings page drives the public pages
```

The other `test_*.py` scripts are older one-off checks that need a server
already running on port 5000.

> On macOS, port 5000 is taken by the AirPlay Receiver. Either turn it off in
> System Settings → General → AirDrop & Handoff, or run on another port.

## 📦 Installation

1. **Clone the repository**
   ```bash
   git clone <repository-url>
   cd 2048
   ```

2. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

3. **Run the application**
   ```bash
   python app.py
   ```

   The server listens on every interface, so a second laptop or a phone on
   the same Wi-Fi can reach it. Find this machine's address with
   `ipconfig getifaddr en0` and open `http://<that-address>:5000` on the
   other device. `FLASK_RUN_HOST=127.0.0.1` restricts it to this machine.

   Debug mode is opt-in, because its interactive console executes arbitrary
   code for anyone who can reach a traceback - which matters precisely when
   other devices can reach the server:
   ```bash
   FLASK_DEBUG=1 python app.py     # auto-reload + debugger
   ```

   **Testing from two machines:** both devices must be on the same network,
   and macOS gives port 5000 to the AirPlay Receiver, so pick another port:
   ```bash
   FLASK_RUN_PORT=8000 python app.py
   ```
   Remember that templates are cached unless `FLASK_DEBUG=1`, so restart the
   server after editing one.

4. **Access the application**
   - Customer Interface: http://localhost:5000
   - Admin Panel: http://localhost:5000/admin

## 🔧 Configuration

### Admin Login
- **Default Username**: admin
- **Default Password**: admin123

### TTS Configuration
- **Default Engine**: gTTS (Google Text-to-Speech)
- **Fallback**: pyttsx3 (Windows TTS)
- **Language**: Vietnamese (vi)
- **Audio Format**: MP3 (gTTS) / Direct (pyttsx3)

## 🎨 UI/UX Features

### Theme System
```css
/* Light Mode (Default) */
:root {
    --bg-primary: #ffffff;
    --text-primary: #212529;
    --accent-color: #4361ee;
}

/* Dark Mode */
[data-theme="dark"] {
    --bg-primary: #0a0e27;
    --text-primary: #ffffff;
    --accent-color: #4361ee;
}
```

### Responsive Breakpoints
- **Mobile**: < 768px
- **Tablet**: 768px - 1024px
- **Desktop**: > 1024px

### Animation System
- **Fade-in**: Smooth entrance animations
- **Hover Effects**: Interactive button states
- **Loading States**: Spinner animations
- **Transitions**: Smooth color and layout changes

## 📱 Mobile Responsiveness

The interface is fully responsive with:
- **Touch-Friendly**: Large tap targets and gestures
- **Adaptive Layout**: Content reorganizes for mobile screens
- **Performance**: Optimized for mobile devices
- **Accessibility**: WCAG compliant design

## 🔊 Voice Settings

### gTTS (Google TTS)
- **Quality**: High-quality Vietnamese speech
- **Requirements**: Internet connection
- **Speed**: Fast processing
- **Natural**: Human-like pronunciation

### pyttsx3 (Windows TTS)
- **Offline**: No internet required
- **Speed**: Instant playback
- **Customizable**: Rate, volume, voice selection
- **Compatible**: Works with Windows voices

## 🎯 Usage Examples

### Switching Themes
```javascript
// Automatic theme toggle
function toggleTheme() {
    const html = document.documentElement;
    const currentTheme = html.getAttribute('data-theme');
    const newTheme = currentTheme === 'light' ? 'dark' : 'light';
    html.setAttribute('data-theme', newTheme);
    localStorage.setItem('theme', newTheme);
}
```

### TTS Engine Toggle
```python
# Switch to gTTS
laptop_speaker.use_gtts = True
laptop_speaker.initialize_engine()

# Switch to pyttsx3
laptop_speaker.use_gtts = False
laptop_speaker.initialize_engine()
```

## 🐛 Troubleshooting

### Common Issues

1. **Theme not persisting**
   - Check browser localStorage support
   - Ensure JavaScript is enabled

2. **TTS not working**
   - Verify internet connection for gTTS
   - Check audio permissions
   - Ensure pygame is installed

3. **Responsive issues**
   - Clear browser cache
   - Check viewport meta tag
   - Test on different screen sizes

### Debug Mode
```bash
# Run with debug mode
python app.py --debug
```

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Test thoroughly
5. Submit a pull request

## 📄 License

This project is licensed under the MIT License.

## 🎉 Acknowledgments

- **Flask**: Web framework
- **Google**: gTTS service
- **Font Awesome**: Icon library
- **Google Fonts**: Typography

---

## 🚀 Quick Start

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Run the app
python app.py

# 3. Open browser
# Customer: http://localhost:5000
# Admin: http://localhost:5000/admin
```

Enjoy your **Modern E-Commerce Platform** with **Light/Dark Mode** and **Advanced TTS Features**! 🎊
- Real-time inventory tracking
- QR code generation for customer access

### Customer Interface
- Product browsing with category filtering
- Shopping cart functionality
- Secure checkout process
- Order confirmation
- Mobile-responsive design

### Technical Features
- Modern dark theme UI
- Responsive design for all devices
- Session-based shopping cart
- MySQL database for data persistence
- QR code integration for easy customer access

## Installation

1. **Clone the repository** (or extract the files to your desired location)

2. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

3. **Run the application:**
   ```bash
   python app.py
   ```

4. **Access the application:**
   - Admin Panel: http://127.0.0.1:5000/admin
   - Customer Store: http://127.0.0.1:5000/customer

## Default Credentials

**Admin Login:**
- Username: `admin`
- Password: `admin123`

## Usage Guide

### For Admins

1. **Login:** Access `/admin` and use the default credentials
2. **Add Products:** Click "Add Product" to add new items to your inventory
3. **Manage Stock:** Toggle products to enable/disable them when out of stock
4. **View Orders:** Monitor customer orders and update their status
5. **Generate QR Code:** Create a QR code for customers to easily access your store

### For Customers

1. **Access Store:** Scan the QR code or visit `/customer`
2. **Browse Products:** View available items with real-time stock information
3. **Add to Cart:** Select items and add them to your shopping cart
4. **Checkout:** Provide your information and confirm your order
5. **Order Confirmation:** Receive confirmation with order details

## Project Structure

```
ecommerce/
├── app.py                 # Main Flask application
├── requirements.txt        # Python dependencies
├── README.md              # This file
├── templates/             # HTML templates
│   ├── admin_login.html
│   ├── admin_dashboard.html
│   ├── add_product.html
│   ├── customer.html
│   ├── cart.html
│   ├── checkout.html
│   ├── order_confirmation.html
│   └── qr_code.html
└── static/
    ├── css/
    │   └── style.css      # Dark theme styling
    ├── js/                # JavaScript files (if needed)
    └── images/            # Product images
```

## Database Schema

The application uses MySQL with the following tables:
- `products` - Product information and inventory
- `orders` - Customer orders
- `order_items` - Individual items within orders
- `admin` - Administrator accounts

## Customization

### Adding Products
Products can be added through the admin panel with:
- Name and description
- Price and stock quantity
- Category classification
- Image URL (optional)

### Styling
The dark theme CSS is located in `static/css/style.css` and can be customized to match your brand colors.

### Security
For production use:
- Change the default admin password
- Update the Flask secret key
- Consider implementing proper password hashing
- Add HTTPS/SSL certificates

## Support

This is a demonstration e-commerce platform. For production deployment, consider:
- Adding payment gateway integration
- Implementing user accounts for customers
- Adding email notifications
- Setting up proper error logging
- Implementing backup systems

## License

This project is provided as-is for educational and demonstration purposes.
