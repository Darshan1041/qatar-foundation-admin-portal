from flask import Flask, request, jsonify, session, send_from_directory
from flask_sqlalchemy import SQLAlchemy
from flask_bcrypt import Bcrypt
from flask_cors import CORS
from datetime import datetime, timedelta
import secrets
import re
import os

app = Flask(__name__)
app.config['SECRET_KEY'] = secrets.token_hex(16)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///qatar_foundation.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(days=30)

db = SQLAlchemy(app)
bcrypt = Bcrypt(app)
CORS(app, supports_credentials=True)

class Admin(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    full_name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(128), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    opportunities = db.relationship('Opportunity', backref='admin', lazy=True, cascade='all, delete-orphan')

    def set_password(self, password):
        self.password_hash = bcrypt.generate_password_hash(password).decode('utf-8')

    def check_password(self, password):
        return bcrypt.check_password_hash(self.password_hash, password)

class PasswordReset(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    admin_id = db.Column(db.Integer, db.ForeignKey('admin.id'), nullable=False)
    token = db.Column(db.String(128), unique=True, nullable=False)
    expires_at = db.Column(db.DateTime, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class Opportunity(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    admin_id = db.Column(db.Integer, db.ForeignKey('admin.id'), nullable=False)
    name = db.Column(db.String(200), nullable=False)
    duration = db.Column(db.String(100), nullable=False)
    start_date = db.Column(db.Date, nullable=False)
    description = db.Column(db.Text, nullable=False)
    skills_to_gain = db.Column(db.String(500), nullable=False)
    category = db.Column(db.String(50), nullable=False)
    future_opportunities = db.Column(db.Text, nullable=False)
    maximum_applicants = db.Column(db.Integer)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

def validate_email(email):
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return re.match(pattern, email) is not None

@app.route('/')
def index():
    return send_from_directory('.', 'admin.html')

@app.route('/<path:filename>')
def serve_static(filename):
    return send_from_directory('.', filename)

@app.route('/api/')
def api_index():
    return jsonify({'message': 'Qatar Foundation Admin Portal API', 'version': '1.0.0'})

@app.route('/api/auth/signup', methods=['POST'])
def signup():
    try:
        data = request.get_json()
        full_name = data.get('full_name', '').strip()
        email = data.get('email', '').strip()
        password = data.get('password', '')
        confirm_password = data.get('confirm_password', '')
        
        if not full_name or not email or not password or not confirm_password:
            return jsonify({'error': 'All fields are required'}), 400
        
        if not validate_email(email):
            return jsonify({'error': 'Invalid email format'}), 400
        
        if len(password) < 8:
            return jsonify({'error': 'Password must be at least 8 characters long'}), 400
        
        if password != confirm_password:
            return jsonify({'error': 'Password and confirm password must match'}), 400
        
        if Admin.query.filter_by(email=email).first():
            return jsonify({'error': 'Account with this email already exists'}), 400
        
        admin = Admin(full_name=full_name, email=email)
        admin.set_password(password)
        db.session.add(admin)
        db.session.commit()
        
        return jsonify({'message': 'Account created successfully'}), 201
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': 'Internal server error'}), 500

@app.route('/api/auth/login', methods=['POST'])
def login():
    try:
        data = request.get_json()
        email = data.get('email', '').strip()
        password = data.get('password', '')
        remember_me = data.get('remember_me', False)
        
        if not email or not password:
            return jsonify({'error': 'Email and password are required'}), 400
        
        admin = Admin.query.filter_by(email=email).first()
        
        if not admin or not admin.check_password(password):
            return jsonify({'error': 'Invalid email or password'}), 401
        
        session['admin_id'] = admin.id
        session['admin_email'] = admin.email
        session.permanent = remember_me
        
        return jsonify({
            'message': 'Login successful',
            'admin': {
                'id': admin.id,
                'full_name': admin.full_name,
                'email': admin.email
            }
        }), 200
    except Exception as e:
        return jsonify({'error': 'Internal server error'}), 500

@app.route('/api/auth/logout', methods=['POST'])
def logout():
    session.clear()
    return jsonify({'message': 'Logged out successfully'}), 200

@app.route('/api/auth/forgot-password', methods=['POST'])
def forgot_password():
    try:
        data = request.get_json()
        email = data.get('email', '').strip()
        
        if not email:
            return jsonify({'error': 'Email is required'}), 400
        
        admin = Admin.query.filter_by(email=email).first()
        
        if admin:
            token = secrets.token_urlsafe(32)
            expires_at = datetime.utcnow() + timedelta(hours=1)
            reset_record = PasswordReset(admin_id=admin.id, token=token, expires_at=expires_at)
            db.session.add(reset_record)
            db.session.commit()
            print(f"Password reset link: http://localhost:5000/reset-password?token={token}")
        
        return jsonify({'message': 'If an account with this email exists, a reset link has been sent'}), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': 'Internal server error'}), 500

@app.route('/api/auth/reset-password', methods=['POST'])
def reset_password():
    try:
        data = request.get_json()
        token = data.get('token', '')
        new_password = data.get('new_password', '')
        confirm_password = data.get('confirm_password', '')
        
        if not token or not new_password or not confirm_password:
            return jsonify({'error': 'All fields are required'}), 400
        
        if len(new_password) < 8:
            return jsonify({'error': 'Password must be at least 8 characters long'}), 400
        
        if new_password != confirm_password:
            return jsonify({'error': 'Password and confirm password must match'}), 400
        
        reset_record = PasswordReset.query.filter_by(token=token).first()
        
        if not reset_record or reset_record.expires_at < datetime.utcnow():
            return jsonify({'error': 'Invalid or expired reset link'}), 400
        
        admin = Admin.query.get(reset_record.admin_id)
        admin.set_password(new_password)
        db.session.delete(reset_record)
        db.session.commit()
        
        return jsonify({'message': 'Password reset successful'}), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': 'Internal server error'}), 500

@app.route('/api/opportunities', methods=['GET'])
def get_opportunities():
    try:
        if 'admin_id' not in session:
            return jsonify({'error': 'Unauthorized'}), 401
        
        opportunities = Opportunity.query.filter_by(admin_id=session['admin_id']).all()
        
        data = []
        for opp in opportunities:
            data.append({
                'id': opp.id,
                'name': opp.name,
                'category': opp.category,
                'duration': opp.duration,
                'start_date': opp.start_date.strftime('%Y-%m-%d'),
                'description': opp.description[:100] + '...' if len(opp.description) > 100 else opp.description,
                'skills_to_gain': opp.skills_to_gain,
                'future_opportunities': opp.future_opportunities,
                'maximum_applicants': opp.maximum_applicants
            })
        
        return jsonify({'opportunities': data}), 200
    except Exception as e:
        return jsonify({'error': 'Internal server error'}), 500

@app.route('/api/opportunities', methods=['POST'])
def create_opportunity():
    try:
        if 'admin_id' not in session:
            return jsonify({'error': 'Unauthorized'}), 401
        
        data = request.get_json()
        
        required_fields = ['name', 'duration', 'start_date', 'description', 'skills_to_gain', 'category', 'future_opportunities']
        for field in required_fields:
            if not data.get(field, '').strip():
                return jsonify({'error': f'{field.replace("_", " ").title()} is required'}), 400
        
        valid_categories = ['Technology', 'Business', 'Design', 'Marketing', 'Data Science', 'Other']
        if data['category'] not in valid_categories:
            return jsonify({'error': 'Invalid category'}), 400
        
        try:
            start_date = datetime.strptime(data['start_date'], '%Y-%m-%d').date()
        except ValueError:
            return jsonify({'error': 'Invalid start date format'}), 400
        
        opportunity = Opportunity(
            admin_id=session['admin_id'],
            name=data['name'],
            duration=data['duration'],
            start_date=start_date,
            description=data['description'],
            skills_to_gain=data['skills_to_gain'],
            category=data['category'],
            future_opportunities=data['future_opportunities'],
            maximum_applicants=data.get('maximum_applicants')
        )
        
        db.session.add(opportunity)
        db.session.commit()
        
        return jsonify({
            'message': 'Opportunity created successfully',
            'opportunity': {
                'id': opportunity.id,
                'name': opportunity.name,
                'category': opportunity.category,
                'duration': opportunity.duration,
                'start_date': opportunity.start_date.strftime('%Y-%m-%d'),
                'description': opportunity.description[:100] + '...' if len(opportunity.description) > 100 else opportunity.description
            }
        }), 201
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': 'Internal server error'}), 500

@app.route('/api/opportunities/<int:opportunity_id>', methods=['GET'])
def get_opportunity(opportunity_id):
    try:
        if 'admin_id' not in session:
            return jsonify({'error': 'Unauthorized'}), 401
        
        opportunity = Opportunity.query.filter_by(id=opportunity_id, admin_id=session['admin_id']).first()
        
        if not opportunity:
            return jsonify({'error': 'Opportunity not found'}), 404
        
        return jsonify({
            'opportunity': {
                'id': opportunity.id,
                'name': opportunity.name,
                'duration': opportunity.duration,
                'start_date': opportunity.start_date.strftime('%Y-%m-%d'),
                'description': opportunity.description,
                'skills_to_gain': opportunity.skills_to_gain,
                'category': opportunity.category,
                'future_opportunities': opportunity.future_opportunities,
                'maximum_applicants': opportunity.maximum_applicants
            }
        }), 200
    except Exception as e:
        return jsonify({'error': 'Internal server error'}), 500

@app.route('/api/opportunities/<int:opportunity_id>', methods=['PUT'])
def update_opportunity(opportunity_id):
    try:
        if 'admin_id' not in session:
            return jsonify({'error': 'Unauthorized'}), 401
        
        opportunity = Opportunity.query.filter_by(id=opportunity_id, admin_id=session['admin_id']).first()
        
        if not opportunity:
            return jsonify({'error': 'Opportunity not found'}), 404
        
        data = request.get_json()
        
        required_fields = ['name', 'duration', 'start_date', 'description', 'skills_to_gain', 'category', 'future_opportunities']
        for field in required_fields:
            if not data.get(field, '').strip():
                return jsonify({'error': f'{field.replace("_", " ").title()} is required'}), 400
        
        valid_categories = ['Technology', 'Business', 'Design', 'Marketing', 'Data Science', 'Other']
        if data['category'] not in valid_categories:
            return jsonify({'error': 'Invalid category'}), 400
        
        try:
            start_date = datetime.strptime(data['start_date'], '%Y-%m-%d').date()
        except ValueError:
            return jsonify({'error': 'Invalid start date format'}), 400
        
        opportunity.name = data['name']
        opportunity.duration = data['duration']
        opportunity.start_date = start_date
        opportunity.description = data['description']
        opportunity.skills_to_gain = data['skills_to_gain']
        opportunity.category = data['category']
        opportunity.future_opportunities = data['future_opportunities']
        opportunity.maximum_applicants = data.get('maximum_applicants')
        opportunity.updated_at = datetime.utcnow()
        
        db.session.commit()
        
        return jsonify({
            'message': 'Opportunity updated successfully',
            'opportunity': {
                'id': opportunity.id,
                'name': opportunity.name,
                'category': opportunity.category,
                'duration': opportunity.duration,
                'start_date': opportunity.start_date.strftime('%Y-%m-%d'),
                'description': opportunity.description[:100] + '...' if len(opportunity.description) > 100 else opportunity.description
            }
        }), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': 'Internal server error'}), 500

@app.route('/api/opportunities/<int:opportunity_id>', methods=['DELETE'])
def delete_opportunity(opportunity_id):
    try:
        if 'admin_id' not in session:
            return jsonify({'error': 'Unauthorized'}), 401
        
        opportunity = Opportunity.query.filter_by(id=opportunity_id, admin_id=session['admin_id']).first()
        
        if not opportunity:
            return jsonify({'error': 'Opportunity not found'}), 404
        
        db.session.delete(opportunity)
        db.session.commit()
        
        return jsonify({'message': 'Opportunity deleted successfully'}), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': 'Internal server error'}), 500

@app.route('/api/auth/check', methods=['GET'])
def check_auth():
    if 'admin_id' in session:
        admin = Admin.query.get(session['admin_id'])
        if admin:
            return jsonify({
                'authenticated': True,
                'admin': {
                    'id': admin.id,
                    'full_name': admin.full_name,
                    'email': admin.email
                }
            }), 200
    return jsonify({'authenticated': False}), 401

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True, port=5000)
