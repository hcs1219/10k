from flask import Flask, render_template, jsonify, request, send_from_directory
from flask_socketio import SocketIO, emit
import eventlet
import json
from datetime import datetime
import uuid
import os
import threading
import time

# Monkey patch for eventlet
eventlet.monkey_patch()

app = Flask(__name__, static_folder='.', static_url_path='')
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-secret-key-123')

# Configure SocketIO with CORS for mobile access
socketio = SocketIO(app, 
                   cors_allowed_origins="*",
                   async_mode='eventlet',
                   logger=True,
                   engineio_logger=False,
                   ping_timeout=60,
                   ping_interval=25,
                   max_http_buffer_size=1e8)

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
            [1.3530, 103.8212], [1.3525, 103.8220],
            [1.3520, 103.8225], [1.3515, 103.8230]
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
            [1.3500, 103.8205], [1.3495, 103.8212],
            [1.3490, 103.8220], [1.3485, 103.8225]
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
            [1.3540, 103.8200], [1.3535, 103.8210],
            [1.3530, 103.8220], [1.3525, 103.8210]
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
            'uptime': get_uptime()
        })

@app.route('/api/data')
def get_all_data():
    with data_lock:
        active_emergencies = {k: v for k, v in emergencies.items() if not v.get('resolved', False)}
        return jsonify({
            'users': users,
            'staff': staff,
            'emergencies': active_emergencies,
            'routes': ROUTES,
            'timestamp': datetime.now().isoformat()
        })

# ========== SOCKET.IO HANDLERS ==========
@socketio.on('connect')
def handle_connect():
    sid = request.sid
    print(f'📱 Client connected: {sid}')
    emit('connected', {'sid': sid, 'message': 'Connected to race tracker'})

@socketio.on('disconnect')
def handle_disconnect():
    sid = request.sid
    print(f'📴 Client disconnected: {sid}')
    
    with data_lock:
        # Remove user
        if sid in users:
            user_data = users.pop(sid)
            emit('user_left', {'sid': sid, 'name': user_data.get('name', 'Unknown')}, 
                 broadcast=True, include_self=False)
            print(f'👤 Removed user: {sid}')
        
        # Remove staff
        if sid in staff:
            staff_data = staff.pop(sid)
            emit('staff_left', {'sid': sid, 'name': staff_data.get('name', 'Unknown')}, 
                 broadcast=True, include_self=False)
            print(f'👨‍⚕️ Removed staff: {sid}')
        
        # Resolve user's emergencies
        for eid, emergency in list(emergencies.items()):
            if emergency.get('user_id') == sid and not emergency.get('resolved', False):
                emergencies[eid]['resolved'] = True
                emit('emergency_resolved', {
                    'emergency_id': eid,
                    'user_id': sid,
                    'auto_resolved': True
                }, broadcast=True)

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
    print(f'👤 New user registered: {users[sid]["name"]}')

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
    print(f'👨‍⚕️ New staff registered: {staff[sid]["name"]}')

@socketio.on('user_location_update')
def handle_user_location(data):
    sid = request.sid
    with data_lock:
        if sid in users:
            users[sid].update({
                'location': [float(data['lat']), float(data['lng'])],
                'last_update': datetime.now().isoformat(),
                'accuracy': data.get('accuracy', 10),
                'speed': data.get('speed', 0),
                'heading': data.get('heading', 0),
                'battery': data.get('battery', users[sid].get('battery', 100))
            })
            
            emit('user_location_updated', {
                'sid': sid,
                'location': users[sid]['location'],
                'name': users[sid]['name'],
                'emergency': users[sid]['emergency']
            }, broadcast=True, include_self=False)

@socketio.on('staff_location_update')
def handle_staff_location(data):
    sid = request.sid
    with data_lock:
        if sid in staff and staff[sid].get('share_location', True):
            staff[sid].update({
                'location': [float(data['lat']), float(data['lng'])],
                'transport': data.get('transport', staff[sid].get('transport', 'walk')),
                'first_aid': data.get('first_aid', staff[sid].get('first_aid', False)),
                'share_location': data.get('share_location', True),
                'status': data.get('status', 'available'),
                'last_update': datetime.now().isoformat(),
                'accuracy': data.get('accuracy', 10),
                'battery': data.get('battery', staff[sid].get('battery', 100))
            })
            
            emit('staff_location_updated', {
                'sid': sid,
                'location': staff[sid]['location'],
                'name': staff[sid]['name'],
                'transport': staff[sid]['transport'],
                'first_aid': staff[sid]['first_aid'],
                'status': staff[sid]['status']
            }, broadcast=True, include_self=False)

@socketio.on('emergency_request')
def handle_emergency(data):
    sid = request.sid
    emergency_id = str(uuid.uuid4())[:8]
    
    with data_lock:
        # Get user location
        user_location = [1.3521, 103.8198]
        user_name = f'Runner-{sid[-4:]}'
        
        if sid in users:
            user_location = users[sid]['location']
            user_name = users[sid]['name']
            users[sid]['emergency'] = True
        
        # Create emergency record
        emergencies[emergency_id] = {
            'emergency_id': emergency_id,
            'user_id': sid,
            'user_name': user_name,
            'location': user_location,
            'timestamp': datetime.now().isoformat(),
            'resolved': False,
            'assigned_to': None,
            'priority': 'high',
            'description': data.get('description', 'Medical emergency'),
            'phone': data.get('phone', ''),
            'notes': data.get('notes', '')
        }
    
    # Broadcast emergency to ALL connected clients
    emit('emergency_alert', {
        'emergency_id': emergency_id,
        'user_id': sid,
        'user_name': user_name,
        'location': user_location,
        'timestamp': emergencies[emergency_id]['timestamp'],
        'description': emergencies[emergency_id]['description'],
        'priority': 'high'
    }, broadcast=True)
    
    # Send confirmation to requester
    emit('emergency_confirmed', {
        'emergency_id': emergency_id,
        'message': 'Emergency reported! Staff have been notified.',
        'estimated_response': '2-5 minutes'
    })
    
    print(f'🚨 EMERGENCY ALERT: {user_name} at {user_location}')
    return {'emergency_id': emergency_id, 'status': 'reported'}

@socketio.on('staff_respond_emergency')
def handle_staff_respond(data):
    sid = request.sid
    emergency_id = data['emergency_id']
    
    with data_lock:
        if emergency_id in emergencies and not emergencies[emergency_id]['resolved']:
            if sid in staff:
                emergencies[emergency_id]['assigned_to'] = sid
                emergencies[emergency_id]['status'] = 'responding'
                staff[sid]['status'] = 'responding'
                
                emit('emergency_response', {
                    'emergency_id': emergency_id,
                    'staff_id': sid,
                    'staff_name': staff[sid]['name'],
                    'response_time': datetime.now().isoformat(),
                    'transport': staff[sid]['transport'],
                    'has_first_aid': staff[sid]['first_aid']
                }, broadcast=True)
                
                print(f'👨‍⚕️ Staff {staff[sid]["name"]} responding to emergency {emergency_id}')
                return {'status': 'responding', 'emergency_id': emergency_id}
    
    return {'status': 'error', 'message': 'Emergency not found or already resolved'}

@socketio.on('resolve_emergency')
def handle_resolve_emergency(data):
    emergency_id = data['emergency_id']
    resolved_by = request.sid
    
    with data_lock:
        if emergency_id in emergencies:
            emergencies[emergency_id].update({
                'resolved': True,
                'resolved_by': resolved_by,
                'resolved_at': datetime.now().isoformat(),
                'resolution_notes': data.get('notes', 'Resolved by staff')
            })
            
            # Update user status
            user_id = emergencies[emergency_id]['user_id']
            if user_id in users:
                users[user_id]['emergency'] = False
            
            # Update staff status
            staff_id = emergencies[emergency_id].get('assigned_to')
            if staff_id and staff_id in staff:
                staff[staff_id]['status'] = 'available'
    
    emit('emergency_resolved', {
        'emergency_id': emergency_id,
        'user_id': emergencies[emergency_id]['user_id'],
        'resolved_by': resolved_by,
        'resolved_at': emergencies[emergency_id]['resolved_at']
    }, broadcast=True)
    
    print(f'✅ Emergency {emergency_id} resolved by {resolved_by}')
    return {'status': 'resolved', 'emergency_id': emergency_id}

@socketio.on('cancel_emergency')
def handle_cancel_emergency(data):
    emergency_id = data['emergency_id']
    user_id = request.sid
    
    with data_lock:
        if emergency_id in emergencies and emergencies[emergency_id]['user_id'] == user_id:
            emergencies[emergency_id]['resolved'] = True
            emergencies[emergency_id]['cancelled'] = True
            emergencies[emergency_id]['cancelled_at'] = datetime.now().isoformat()
            
            if user_id in users:
                users[user_id]['emergency'] = False
    
    emit('emergency_cancelled', {
        'emergency_id': emergency_id,
        'user_id': user_id,
        'cancelled_at': datetime.now().isoformat()
    }, broadcast=True)
    
    return {'status': 'cancelled', 'emergency_id': emergency_id}

@socketio.on('get_initial_data')
def handle_get_initial_data():
    sid = request.sid
    with data_lock:
        active_emergencies = {k: v for k, v in emergencies.items() if not v.get('resolved', False)}
        
        # Filter sensitive data
        users_data = {}
        for uid, user in users.items():
            if uid != sid:  # Don't send user their own data
                users_data[uid] = {
                    'name': user.get('name'),
                    'location': user.get('location'),
                    'emergency': user.get('emergency', False),
                    'type': 'user'
                }
        
        staff_data = {}
        for stid, stf in staff.items():
            if stid != sid and stf.get('share_location', True):
                staff_data[stid] = {
                    'name': stf.get('name'),
                    'location': stf.get('location'),
                    'transport': stf.get('transport', 'walk'),
                    'first_aid': stf.get('first_aid', False),
                    'status': stf.get('status', 'available'),
                    'type': 'staff'
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
                'transport': data.get('transport', staff[sid].get('transport', 'walk')),
                'first_aid': data.get('first_aid', staff[sid].get('first_aid', False)),
                'share_location': data.get('share_location', staff[sid].get('share_location', True)),
                'status': data.get('status', 'available')
            })
            
            emit('staff_status_updated', {
                'sid': sid,
                'name': staff[sid]['name'],
                'transport': staff[sid]['transport'],
                'first_aid': staff[sid]['first_aid'],
                'status': staff[sid]['status']
            }, broadcast=True, include_self=False)

# ========== BACKGROUND TASKS ==========
def cleanup_old_data():
    """Remove inactive users/staff every minute"""
    while True:
        time.sleep(60)  # Run every minute
        now = datetime.now()
        cutoff = 300  # 5 minutes in seconds
        
        with data_lock:
            # Clean old users
            for uid in list(users.keys()):
                if 'last_update' in users[uid]:
                    last_update = datetime.fromisoformat(users[uid]['last_update'])
                    if (now - last_update).total_seconds() > cutoff:
                        print(f'🧹 Cleaning up inactive user: {users[uid]["name"]}')
                        del users[uid]
                        emit('user_left', {'sid': uid}, broadcast=True)
            
            # Clean old staff
            for sid in list(staff.keys()):
                if 'last_update' in staff[sid]:
                    last_update = datetime.fromisoformat(staff[sid]['last_update'])
                    if (now - last_update).total_seconds() > cutoff:
                        print(f'🧹 Cleaning up inactive staff: {staff[sid]["name"]}')
                        del staff[sid]
                        emit('staff_left', {'sid': sid}, broadcast=True)
            
            # Auto-resolve old emergencies
            for eid in list(emergencies.keys()):
                if not emergencies[eid].get('resolved', False):
                    emergency_time = datetime.fromisoformat(emergencies[eid]['timestamp'])
                    if (now - emergency_time).total_seconds() > 3600:  # 1 hour
                        emergencies[eid]['resolved'] = True
                        emergencies[eid]['auto_resolved'] = True
                        print(f'🧹 Auto-resolving old emergency: {eid}')

def periodic_broadcast():
    """Broadcast system status periodically"""
    while True:
        time.sleep(30)  # Every 30 seconds
        with data_lock:
            active_users = len(users)
            active_staff = len(staff)
            active_emergencies = len([e for e in emergencies.values() if not e.get('resolved', False)])
        
        socketio.emit('system_status', {
            'timestamp': datetime.now().isoformat(),
            'active_users': active_users,
            'active_staff': active_staff,
            'active_emergencies': active_emergencies,
            'uptime': get_uptime()
        })

def get_uptime():
    """Calculate server uptime"""
    if not hasattr(get_uptime, 'start_time'):
        get_uptime.start_time = datetime.now()
    
    uptime = datetime.now() - get_uptime.start_time
    hours = uptime.seconds // 3600
    minutes = (uptime.seconds % 3600) // 60
    return f"{hours}h {minutes}m"

# ========== START BACKGROUND THREADS ==========
def start_background_tasks():
    """Start background cleanup and status threads"""
    cleanup_thread = threading.Thread(target=cleanup_old_data, daemon=True)
    broadcast_thread = threading.Thread(target=periodic_broadcast, daemon=True)
    
    cleanup_thread.start()
    broadcast_thread.start()
    
    print("✅ Background tasks started")

# ========== MAIN ENTRY POINT ==========
if __name__ == '__main__':
    # Start background tasks
    start_background_tasks()
    
    # Get port from environment (Railway provides this)
    port = int(os.environ.get('PORT', 5000))
    
    print("=" * 50)
    print("🚀 Race Tracker Server Starting...")
    print(f"📡 WebSocket Server: Ready on port {port}")
    print(f"🗺️ Routes loaded: {len(ROUTES)}")
    print(f"🔐 Secret Key: {'Set' if os.environ.get('SECRET_KEY') else 'Using default'}")
    print("=" * 50)
    
    # Run the server
    socketio.run(app, 
                 host='0.0.0.0', 
                 port=port, 
                 debug=False,
                 log_output=True,
                 allow_unsafe_werkzeug=True)