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
