from flask import Flask, send_from_directory, jsonify, request
from flask_socketio import SocketIO, emit
import eventlet
import json
from datetime import datetime
import uuid
import os
import threading
import time

# Use setuptools instead of distutils
import setuptools

# Monkey patch for eventlet
eventlet.monkey_patch()

app = Flask(__name__, static_folder='.', static_url_path='')
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'race-tracker-secret-2024')

# Configure SocketIO
socketio = SocketIO(app, 
                   cors_allowed_origins="*",
                   async_mode='eventlet',
                   logger=False,
                   engineio_logger=False,
                   ping_timeout=60,
                   ping_interval=25)

# ========== DATA STORAGE ==========
users = {}
staff = {}
emergencies = {}
routes_data = {}

# Lock for thread-safe operations
data_lock = threading.Lock()

# ========== ROUTES DATA ==========
ROUTES = {
    "route_1": {
        "id": "route_1",
        "name": "Coastal Route",
        "path": [
            [1.3521, 103.8198], [1.3525, 103.8205], 
            [1.3530, 103.8212], [1.3525, 103.8220]
        ],
        "color": "#3B82F6",
        "distance": "5.2km",
        "difficulty": "Easy"
    },
    "route_2": {
        "id": "route_2", 
        "name": "Park Trail",
        "path": [
            [1.3510, 103.8190], [1.3505, 103.8198],
            [1.3500, 103.8205], [1.3495, 103.8212]
        ],
        "color": "#10B981",
        "distance": "7.8km", 
        "difficulty": "Medium"
    },
    "route_3": {
        "id": "route_3",
        "name": "City Loop", 
        "path": [
            [1.3530, 103.8180], [1.3535, 103.8190],
            [1.3540, 103.8200], [1.3535, 103.8210]
        ],
        "color": "#8B5CF6",
        "distance": "10.5km",
        "difficulty": "Hard"
    }
}

# ========== FLASK ROUTES ==========
@app.route('/')
def index():
    return send_from_directory('.', 'index.html')

@app.route('/staff')
def staff_page():
    return send_from_directory('.', 'staff.html')

@app.route('/api/routes')
def get_routes():
    return jsonify(ROUTES)

@app.route('/api/status')
def status():
    with data_lock:
        active_emergencies = [e for e in emergencies.values() if not e.get('resolved', False)]
        return jsonify({
            'status': 'online',
            'users': len(users),
            'staff': len(staff),
            'active_emergencies': len(active_emergencies),
            'timestamp': datetime.now().isoformat()
        })

# ========== SOCKET.IO HANDLERS ==========
@socketio.on('connect')
def handle_connect():
    sid = request.sid
    print(f'Client connected: {sid}')
    emit('connected', {'sid': sid, 'message': 'Connected to race tracker'})

@socketio.on('disconnect')
def handle_disconnect():
    sid = request.sid
    print(f'Client disconnected: {sid}')
    
    with data_lock:
        if sid in users:
            user_data = users.pop(sid)
            emit('user_left', {'sid': sid}, broadcast=True, include_self=False)
        
        if sid in staff:
            staff_data = staff.pop(sid)
            emit('staff_left', {'sid': sid}, broadcast=True, include_self=False)

@socketio.on('register_user')
def handle_register_user(data):
    sid = request.sid
    with data_lock:
        users[sid] = {
            'sid': sid,
            'type': 'user',
            'name': data.get('name', f'Runner-{sid[-4:]}'),
            'location': data.get('location', [1.3521, 103.8198]),
            'emergency': False,
            'last_update': datetime.now().isoformat(),
            'battery': data.get('battery', 100)
        }
    
    emit('registration_success', {'user_id': sid})
    emit('user_joined', users[sid], broadcast=True, include_self=False)

@socketio.on('register_staff')
def handle_register_staff(data):
    sid = request.sid
    with data_lock:
        staff[sid] = {
            'sid': sid,
            'type': 'staff',
            'name': data.get('name', f'Staff-{sid[-4:]}'),
            'location': data.get('location', [1.3521, 103.8198]),
            'transport': data.get('transport', 'walk'),
            'share_location': data.get('share_location', True),
            'first_aid': data.get('first_aid', False),
            'status': 'available',
            'last_update': datetime.now().isoformat(),
            'battery': data.get('battery', 100)
        }
    
    emit('registration_success', {'staff_id': sid})
    emit('staff_joined', staff[sid], broadcast=True, include_self=False)

@socketio.on('user_location_update')
def handle_user_location(data):
    sid = request.sid
    with data_lock:
        if sid in users:
            users[sid].update({
                'location': [float(data.get('lat', 1.3521)), float(data.get('lng', 103.8198))],
                'last_update': datetime.now().isoformat(),
                'emergency': data.get('emergency', False),
                'battery': data.get('battery', users[sid].get('battery', 100))
            })
            
            emit('user_location_updated', {
                'sid': sid,
                'name': users[sid]['name'],
                'location': users[sid]['location'],
                'emergency': users[sid]['emergency']
            }, broadcast=True, include_self=False)

@socketio.on('staff_location_update')
def handle_staff_location(data):
    sid = request.sid
    with data_lock:
        if sid in staff:
            staff[sid].update({
                'location': [float(data.get('lat', 1.3521)), float(data.get('lng', 103.8198))],
                'transport': data.get('transport', 'walk'),
                'first_aid': data.get('first_aid', False),
                'share_location': data.get('share_location', True),
                'status': data.get('status', 'available'),
                'last_update': datetime.now().isoformat()
            })
            
            if staff[sid]['share_location']:
                emit('staff_location_updated', {
                    'sid': sid,
                    'name': staff[sid]['name'],
                    'location': staff[sid]['location'],
                    'transport': staff[sid]['transport'],
                    'first_aid': staff[sid]['first_aid'],
                    'status': staff[sid]['status']
                }, broadcast=True, include_self=False)

@socketio.on('emergency_request')
def handle_emergency(data):
    sid = request.sid
    emergency_id = str(uuid.uuid4())[:8]
    
    with data_lock:
        user_location = [1.3521, 103.8198]
        user_name = f'Runner-{sid[-4:]}'
        
        if sid in users:
            user_location = users[sid]['location']
            user_name = users[sid]['name']
            users[sid]['emergency'] = True
        
        emergencies[emergency_id] = {
            'emergency_id': emergency_id,
            'user_id': sid,
            'user_name': user_name,
            'location': user_location,
            'timestamp': datetime.now().isoformat(),
            'resolved': False,
            'description': data.get('description', 'Medical emergency')
        }
    
    emit('emergency_alert', {
        'emergency_id': emergency_id,
        'user_id': sid,
        'user_name': user_name,
        'location': user_location,
        'timestamp': datetime.now().isoformat(),
        'description': emergencies[emergency_id]['description']
    }, broadcast=True)
    
    emit('emergency_confirmed', {
        'emergency_id': emergency_id,
        'message': 'Emergency reported! Staff have been notified.'
    })
    
    return {'emergency_id': emergency_id}

@socketio.on('staff_respond_emergency')
def handle_staff_respond(data):
    sid = request.sid
    emergency_id = data.get('emergency_id')
    
    with data_lock:
        if emergency_id in emergencies and not emergencies[emergency_id]['resolved']:
            if sid in staff:
                emergencies[emergency_id]['assigned_to'] = sid
                staff[sid]['status'] = 'responding'
                
                emit('emergency_response', {
                    'emergency_id': emergency_id,
                    'staff_id': sid,
                    'staff_name': staff[sid]['name']
                }, broadcast=True)
                
                return {'status': 'responding', 'emergency_id': emergency_id}
    
    return {'status': 'error', 'message': 'Emergency not found'}

@socketio.on('resolve_emergency')
def handle_resolve_emergency(data):
    emergency_id = data.get('emergency_id')
    
    with data_lock:
        if emergency_id in emergencies:
            emergencies[emergency_id]['resolved'] = True
            
            user_id = emergencies[emergency_id]['user_id']
            if user_id in users:
                users[user_id]['emergency'] = False
    
    emit('emergency_resolved', {
        'emergency_id': emergency_id,
        'user_id': emergencies[emergency_id]['user_id']
    }, broadcast=True)
    
    return {'status': 'resolved', 'emergency_id': emergency_id}

@socketio.on('cancel_emergency')
def handle_cancel_emergency(data):
    emergency_id = data.get('emergency_id')
    user_id = request.sid
    
    with data_lock:
        if emergency_id in emergencies and emergencies[emergency_id]['user_id'] == user_id:
            emergencies[emergency_id]['resolved'] = True
            
            if user_id in users:
                users[user_id]['emergency'] = False
    
    emit('emergency_cancelled', {
        'emergency_id': emergency_id,
        'user_id': user_id
    }, broadcast=True)
    
    return {'status': 'cancelled', 'emergency_id': emergency_id}

@socketio.on('get_initial_data')
def handle_get_initial_data():
    sid = request.sid
    with data_lock:
        active_emergencies = {k: v for k, v in emergencies.items() if not v.get('resolved', False)}
        
        users_data = {}
        for uid, user in users.items():
            if uid != sid:
                users_data[uid] = {
                    'name': user.get('name'),
                    'location': user.get('location'),
                    'emergency': user.get('emergency', False)
                }
        
        staff_data = {}
        for stid, stf in staff.items():
            if stid != sid and stf.get('share_location', True):
                staff_data[stid] = {
                    'name': stf.get('name'),
                    'location': stf.get('location'),
                    'transport': stf.get('transport', 'walk'),
                    'first_aid': stf.get('first_aid', False),
                    'status': stf.get('status', 'available')
                }
    
    emit('initial_data', {
        'users': users_data,
        'staff': staff_data,
        'emergencies': active_emergencies,
        'routes': ROUTES,
        'your_id': sid
    })

@socketio.on('update_staff_status')
def handle_update_staff_status(data):
    sid = request.sid
    with data_lock:
        if sid in staff:
            staff[sid].update({
                'transport': data.get('transport', 'walk'),
                'first_aid': data.get('first_aid', False),
                'share_location': data.get('share_location', True),
                'status': data.get('status', 'available')
            })
            
            emit('staff_status_updated', {
                'sid': sid,
                'name': staff[sid]['name'],
                'transport': staff[sid]['transport'],
                'first_aid': staff[sid]['first_aid'],
                'status': staff[sid]['status']
            }, broadcast=True, include_self=False)

# ========== CLEANUP THREAD ==========
def cleanup_old_data():
    """Remove inactive users/staff every minute"""
    while True:
        time.sleep(60)
        now = datetime.now()
        cutoff = 300  # 5 minutes
        
        with data_lock:
            # Clean old users
            for uid in list(users.keys()):
                if 'last_update' in users[uid]:
                    last_update = datetime.fromisoformat(users[uid]['last_update'])
                    if (now - last_update).total_seconds() > cutoff:
                        del users[uid]
                        emit('user_left', {'sid': uid}, broadcast=True)
            
            # Clean old staff
            for sid in list(staff.keys()):
                if 'last_update' in staff[sid]:
                    last_update = datetime.fromisoformat(staff[sid]['last_update'])
                    if (now - last_update).total_seconds() > cutoff:
                        del staff[sid]
                        emit('staff_left', {'sid': sid}, broadcast=True)

# ========== START CLEANUP THREAD ==========
cleanup_thread = threading.Thread(target=cleanup_old_data, daemon=True)
cleanup_thread.start()

# ========== MAIN ENTRY POINT ==========
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    print(f"Starting server on port {port}")
    socketio.run(app, host='0.0.0.0', port=port, debug=False)