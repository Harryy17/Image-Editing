import os
import base64
import time
import numpy as np
from io import BytesIO
from flask import Flask, render_template, redirect, url_for, request, flash, jsonify, send_file
from flask_login import LoginManager, login_user, login_required, logout_user, UserMixin, current_user
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from PIL import Image, ImageEnhance, ImageFilter, ImageOps, ImageDraw, ImageFont
import tempfile

# Create Flask app first
app = Flask(__name__)
app.secret_key = 'your_secret_key_change_this_in_production'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///users.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Upload configurations
app.config['UPLOAD_FOLDER'] = 'static/uploads'
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max file size
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'bmp', 'webp', 'tiff'}

# Create necessary directories
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
os.makedirs('static/images', exist_ok=True)
os.makedirs('static/css', exist_ok=True)

# Initialize extensions
db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'
login_manager.login_message = 'Please log in to access this page.'
login_manager.login_message_category = 'info'

# Simplified Models (compatible with existing database)
class User(UserMixin, db.Model):
    __tablename__ = 'users'
    
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(150), unique=True, nullable=False)
    email = db.Column(db.String(150), unique=True, nullable=True)
    password = db.Column(db.String(150), nullable=False)
    created_at = db.Column(db.DateTime, default=db.func.current_timestamp())
    
    def __repr__(self):
        return f'<User {self.username}>'

class Template(db.Model):
    __tablename__ = 'templates'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    filename = db.Column(db.String(200), nullable=False)
    category = db.Column(db.String(50), nullable=False)
    description = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=db.func.current_timestamp())
    
    def __repr__(self):
        return f'<Template {self.name}>'

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def apply_sepia_filter(img):
    """Apply sepia filter to image"""
    if img.mode != 'RGB':
        img = img.convert('RGB')
    
    pixels = img.load()
    width, height = img.size
    
    for py in range(height):
        for px in range(width):
            r, g, b = img.getpixel((px, py))
            
            # Sepia transformation formula
            tr = int(0.393 * r + 0.769 * g + 0.189 * b)
            tg = int(0.349 * r + 0.686 * g + 0.168 * b)
            tb = int(0.272 * r + 0.534 * g + 0.131 * b)
            
            # Clamp values to 0-255
            tr = min(255, tr)
            tg = min(255, tg)
            tb = min(255, tb)
                
            pixels[px, py] = (tr, tg, tb)
    
    return img

def create_vintage_filter(img):
    """Create vintage effect"""
    if img.mode != 'RGB':
        img = img.convert('RGB')
    
    # Apply sepia first
    img = apply_sepia_filter(img)
    
    # Reduce saturation slightly
    enhancer = ImageEnhance.Color(img)
    img = enhancer.enhance(0.8)
    
    return img

# Routes
@app.route('/')
def home():
    return render_template('home.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        
        if not username or not password:
            flash('Please fill in all fields', 'error')
            return render_template('login.html')
        
        user = User.query.filter_by(username=username).first()
        
        if user and check_password_hash(user.password, password):
            login_user(user)
            flash(f'Welcome back, {user.username}!', 'success')
            next_page = request.args.get('next')
            return redirect(next_page) if next_page else redirect(url_for('home'))
        else:
            flash('Invalid username or password', 'error')
    
    return render_template('login.html')

@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        email = request.form.get('email', '').strip()
        password = request.form.get('password', '')
        
        # Basic validation
        if not all([username, email, password]):
            flash('Please fill in all fields', 'error')
            return render_template('signup.html')
        
        if len(password) < 6:
            flash('Password must be at least 6 characters long', 'error')
            return render_template('signup.html')
        
        # Check if user already exists
        if User.query.filter_by(username=username).first():
            flash('Username already exists', 'error')
            return render_template('signup.html')
        
        if User.query.filter_by(email=email).first():
            flash('Email already registered', 'error')
            return render_template('signup.html')
        
        # Create new user
        try:
            hashed_password = generate_password_hash(password)
            new_user = User(
                username=username,
                email=email,
                password=hashed_password
            )
            db.session.add(new_user)
            db.session.commit()
            
            flash('Account created successfully! You can now log in.', 'success')
            return redirect(url_for('login'))
            
        except Exception as e:
            db.session.rollback()
            flash('An error occurred while creating your account. Please try again.', 'error')
    
    return render_template('signup.html')

@app.route('/logout')
@login_required
def logout():
    username = current_user.username
    logout_user()
    flash(f'Goodbye, {username}!', 'info')
    return redirect(url_for('home'))

@app.route('/templates')
def templates_gallery():
    category = request.args.get('category', 'all')
    search = request.args.get('search', '').strip()
    
    # Static template data (since database might not have all columns)
    all_templates = [
        {
            'id': 'business',
            'name': 'Professional Business Template',
            'category': 'business',
            'description': 'Clean and professional layout perfect for corporate presentations, business cards, and marketing materials.',
            'features': ['High Resolution', 'Print Ready', 'Modern Design', 'Corporate Style'],
            'colors': ['Blue', 'White', 'Gray', 'Professional'],
            'rating': 4.8,
            'downloads': 1250,
            'is_premium': False
        },
        {
            'id': 'portfolio',
            'name': 'Creative Portfolio Template',
            'category': 'portfolio',
            'description': 'Modern creative design ideal for showcasing artistic work, photography, and creative projects.',
            'features': ['Artistic Layout', 'Gallery Ready', 'Creative Focus', 'Visual Impact'],
            'colors': ['Pastel', 'Multi-color', 'Vibrant', 'Creative'],
            'rating': 4.9,
            'downloads': 980,
            'is_premium': False
        },
        {
            'id': 'minimalist',
            'name': 'Minimalist Design Template',
            'category': 'minimalist',
            'description': 'Clean, simple design focusing on content with plenty of white space and elegant typography.',
            'features': ['Clean Layout', 'Typography Focus', 'Minimal Style', 'White Space'],
            'colors': ['Black', 'White', 'Gray', 'Monochrome'],
            'rating': 4.7,
            'downloads': 750,
            'is_premium': False
        },
        {
            'id': 'ecommerce',
            'name': 'E-commerce Product Template',
            'category': 'ecommerce',
            'description': 'Perfect for product showcases, online stores, and commercial presentations with focus on products.',
            'features': ['Product Focus', 'Commercial Use', 'Sales Ready', 'Conversion Optimized'],
            'colors': ['White', 'Green', 'Orange', 'Commercial'],
            'rating': 4.6,
            'downloads': 650,
            'is_premium': True
        },
        {
            'id': 'social',
            'name': 'Social Media Template',
            'category': 'social',
            'description': 'Optimized for social media posts, stories, and digital marketing campaigns across all platforms.',
            'features': ['Social Ready', 'Multiple Formats', 'Engaging Design', 'Platform Optimized'],
            'colors': ['Gradient', 'Colorful', 'Modern', 'Trendy'],
            'rating': 4.8,
            'downloads': 1100,
            'is_premium': False
        },
        {
            'id': 'photography',
            'name': 'Photography Showcase Template',
            'category': 'photography',
            'description': 'Designed specifically for photographers to showcase their work with elegant frames and layouts.',
            'features': ['Photo Focused', 'Professional Look', 'Gallery Style', 'Elegant Frames'],
            'colors': ['Natural', 'Earth Tones', 'Classic', 'Elegant'],
            'rating': 4.9,
            'downloads': 820,
            'is_premium': True
        }
    ]
    
    # Filter templates
    templates = all_templates
    
    if category != 'all':
        templates = [t for t in templates if t['category'] == category]
    
    if search:
        search_lower = search.lower()
        templates = [t for t in templates if 
                    search_lower in t['name'].lower() or 
                    search_lower in t['description'].lower() or
                    any(search_lower in feature.lower() for feature in t['features'])]
    
    # Get categories for filter menu
    categories = list(set([t['category'] for t in all_templates]))
    categories.sort()
    
    return render_template('templates.html', 
                         templates=templates, 
                         categories=categories,
                         current_category=category,
                         search_query=search)

@app.route('/editor')
@login_required
def editor():
    template = request.args.get('template')
    return render_template('editor.html', template=template)

@app.route('/upload_image', methods=['POST'])
@login_required
def upload_image():
    if 'file' not in request.files:
        return jsonify({'error': 'No file selected'}), 400
    
    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'No file selected'}), 400
    
    if file and allowed_file(file.filename):
        try:
            # Secure the filename and add timestamp
            filename = secure_filename(file.filename)
            timestamp = str(int(time.time()))
            name, ext = os.path.splitext(filename)
            filename = f"{timestamp}_{name}{ext}"
            
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(filepath)
            
            # Validate that it's actually an image
            try:
                with Image.open(filepath) as img:
                    img.verify()
            except Exception:
                os.remove(filepath)
                return jsonify({'error': 'Invalid image file'}), 400
            
            return jsonify({'success': True, 'filename': filename})
            
        except Exception as e:
            return jsonify({'error': 'Upload failed'}), 500
    
    return jsonify({'error': 'Invalid file type. Supported formats: PNG, JPG, JPEG, GIF, BMP, WEBP, TIFF'}), 400

@app.route('/edit_image', methods=['POST'])
@login_required
def edit_image():
    try:
        data = request.get_json()
        filename = data.get('filename')
        operation = data.get('operation')
        value = data.get('value', 0)
        
        if not filename:
            return jsonify({'error': 'No filename provided'}), 400
        
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        
        if not os.path.exists(filepath):
            return jsonify({'error': 'File not found'}), 404
        
        with Image.open(filepath) as img:
            # Convert to RGB if necessary
            if img.mode in ('RGBA', 'LA', 'P'):
                background = Image.new('RGB', img.size, (255, 255, 255))
                if img.mode == 'P':
                    img = img.convert('RGBA')
                background.paste(img, mask=img.split()[-1] if img.mode in ('RGBA', 'LA') else None)
                img = background
            elif img.mode != 'RGB':
                img = img.convert('RGB')
            
            # Apply operations
            if operation == 'rotate':
                img = img.rotate(int(value), expand=True)
            elif operation == 'brightness':
                enhancer = ImageEnhance.Brightness(img)
                img = enhancer.enhance(float(value))
            elif operation == 'contrast':
                enhancer = ImageEnhance.Contrast(img)
                img = enhancer.enhance(float(value))
            elif operation == 'saturation':
                enhancer = ImageEnhance.Color(img)
                img = enhancer.enhance(float(value))
            elif operation == 'sharpness':
                enhancer = ImageEnhance.Sharpness(img)
                img = enhancer.enhance(float(value))
            elif operation == 'blur':
                img = img.filter(ImageFilter.GaussianBlur(radius=float(value)))
            elif operation == 'resize':
                try:
                    width, height = map(int, value.split('x'))
                    img = img.resize((width, height), Image.Resampling.LANCZOS)
                except ValueError:
                    return jsonify({'error': 'Invalid resize format. Use WIDTHxHEIGHT'}), 400
            
            # Color operations
            elif operation == 'grayscale':
                img = img.convert('L').convert('RGB')
            elif operation == 'sepia':
                img = apply_sepia_filter(img)
            elif operation == 'vintage':
                img = create_vintage_filter(img)
            elif operation == 'invert':
                img = ImageOps.invert(img)
            elif operation == 'posterize':
                img = ImageOps.posterize(img, max(2, min(8, int(value))))
            elif operation == 'solarize':
                img = ImageOps.solarize(img, max(0, min(255, int(value))))
            
            # Advanced filters
            elif operation == 'emboss':
                img = img.filter(ImageFilter.EMBOSS)
            elif operation == 'edge_enhance':
                img = img.filter(ImageFilter.EDGE_ENHANCE)
            elif operation == 'edge_enhance_more':
                img = img.filter(ImageFilter.EDGE_ENHANCE_MORE)
            elif operation == 'find_edges':
                img = img.filter(ImageFilter.FIND_EDGES)
            elif operation == 'contour':
                img = img.filter(ImageFilter.CONTOUR)
            elif operation == 'detail':
                img = img.filter(ImageFilter.DETAIL)
            elif operation == 'sharpen':
                img = img.filter(ImageFilter.SHARPEN)
            elif operation == 'smooth':
                img = img.filter(ImageFilter.SMOOTH)
            elif operation == 'smooth_more':
                img = img.filter(ImageFilter.SMOOTH_MORE)
            elif operation == 'unsharp_mask':
                img = img.filter(ImageFilter.UnsharpMask(radius=2, percent=150, threshold=3))
            
            # Flip operations
            elif operation == 'flip_horizontal':
                img = img.transpose(Image.Transpose.FLIP_LEFT_RIGHT)
            elif operation == 'flip_vertical':
                img = img.transpose(Image.Transpose.FLIP_TOP_BOTTOM)
            
            # Auto enhance
            elif operation == 'auto_contrast':
                img = ImageOps.autocontrast(img)
            elif operation == 'equalize':
                img = ImageOps.equalize(img)
            
            else:
                return jsonify({'error': f'Unknown operation: {operation}'}), 400
            
            # Save edited image
            edited_filename = f"edited_{int(time.time())}_{os.path.basename(filename)}"
            edited_filepath = os.path.join(app.config['UPLOAD_FOLDER'], edited_filename)
            
            # Save with high quality
            save_kwargs = {'quality': 95, 'optimize': True}
            if edited_filename.lower().endswith('.png'):
                save_kwargs = {'optimize': True}
            
            img.save(edited_filepath, **save_kwargs)
            
            # Convert to base64 for preview
            buffer = BytesIO()
            img.save(buffer, format='PNG')
            img_str = base64.b64encode(buffer.getvalue()).decode()
            
            return jsonify({
                'success': True,
                'edited_filename': edited_filename,
                'preview': f"data:image/png;base64,{img_str}",
                'operation_applied': operation
            })
    
    except Exception as e:
        return jsonify({'error': f'Edit operation failed: {str(e)}'}), 500

# Error handlers
@app.errorhandler(404)
def not_found_error(error):
    return render_template('errors/404.html'), 404

@app.errorhandler(500)
def internal_error(error):
    db.session.rollback()
    return render_template('errors/500.html'), 500

@app.errorhandler(413)
def too_large(error):
    return jsonify({'error': 'File too large. Maximum size is 16MB.'}), 413

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True, port=5000)
