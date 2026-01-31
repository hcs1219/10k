from flask import Flask, render_template, jsonify, request
from flask_socketio import SocketIO, emit
import eventlet
import json
from datetime import datetime
import uuid

app = Flask(__name__, static_folder='.', static_url_path='')
app.config['SECRET_KEY'] = 'your-secret-key-change-in-production'
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='eventlet')

# In-memory storage (replace with Redis in production)
users = {}
staff = {}
emergencies = {}

# Running routes coordinates (example data)
ROUTES = {
    "route_1": {
        "name": "Coastal Route",
        "path": [[1.3521, 103.8198], [1.3525, 103.8205], [1.3530, 103.8212], [1.3525, 103.8220]],
        "color": "#3B82F6"
    },
    "route_2": {
        "name": "Park Trail",
        "path": [[1.3510, 103.8190], [1.3505, 103.8198], [1.3500, 103.8205], [1.3495, 103.8212]],
        "color": "#10B981"
    },
    "route_3": {
        "name": "City Loop",
        "path": [[1.3530, 103.8180], [1.3535, 103.8190], [1.3540, 103.8200], [1.3535, 103.8210]],
        "color": "#8B5CF6"
    }
}

@app.route('/')
def index():
    return app.send_static_file('index.html')

@app.route('/staff')
def staff_page():
    return app.send_static_file('staff.html')

@app.route('/api/routes')
def get_routes():
    return jsonify(ROUTES)

@socketio.on('connect')
def handle_connect():
    print(f'Client connected: {request.sid}')

@socketio.on('disconnect')
def handle_disconnect():
    sid = request.sid
    if sid in users:
        del users[sid]
        socketio.emit('user_left', {'sid': sid})
    if sid in staff:
        del staff[sid]
        socketio.emit('staff_left', {'sid': sid})

@socketio.on('user_location')
def handle_user_location(data):
    users[request.sid] = {
        'type': 'user',
        'location': [data['lat'], data['lng']],
        'emergency': data.get('emergency', False),
        'name': f"User-{request.sid[:4]}",
        'timestamp': datetime.now().isoformat()
    }
    socketio.emit('user_update', users[request.sid])

@socketio.on('staff_location')
def handle_staff_location(data):
    staff[request.sid] = {
        'type': 'staff',
        'location': [data['lat'], data['lng']],
        'transport': data.get('transport', 'walk'),
        'share_location': data.get('share_location', True),
        'first_aid': data.get('first_aid', False),
        'name': f"Staff-{request.sid[:4]}",
        'timestamp': datetime.now().isoformat()
    }
    socketio.emit('staff_update', staff[request.sid])

@socketio.on('emergency_request')
def handle_emergency(data):
    user_id = request.sid
    emergency_id = str(uuid.uuid4())[:8]
    
    emergencies[emergency_id] = {
        'user_id': user_id,
        'location': users[user_id]['location'] if user_id in users else data['location'],
        'timestamp': datetime.now().isoformat(),
        'resolved': False
    }
    
    if user_id in users:
        users[user_id]['emergency'] = True
    
    socketio.emit('emergency_alert', {
        'emergency_id': emergency_id,
        'user_id': user_id,
        'location': emergencies[emergency_id]['location'],
        'timestamp': emergencies[emergency_id]['timestamp']
    })
    
    return {'emergency_id': emergency_id}

@socketio.on('resolve_emergency')
def handle_resolve_emergency(data):
    emergency_id = data['emergency_id']
    
    if emergency_id in emergencies:
        emergencies[emergency_id]['resolved'] = True
        user_id = emergencies[emergency_id]['user_id']
        
        if user_id in users:
            users[user_id]['emergency'] = False
        
        socketio.emit('emergency_resolved', {
            'emergency_id': emergency_id,
            'user_id': user_id
        })
        
        return {'status': 'success'}
    
    return {'status': 'error', 'message': 'Emergency not found'}

@socketio.on('get_all_data')
def handle_get_all_data():
    active_emergencies = {k: v for k, v in emergencies.items() if not v['resolved']}
    emit('all_data', {
        'users': users,
        'staff': staff,
        'emergencies': active_emergencies,
        'routes': ROUTES
    })

if __name__ == '__main__':
    socketio.run(app, debug=True, port=5000)