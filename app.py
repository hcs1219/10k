from flask import Flask, send_from_directory, jsonify, request
from flask_socketio import SocketIO, emit
import eventlet
from datetime import datetime
import uuid
import os
import threading
import time

eventlet.monkey_patch()

app = Flask(__name__, static_folder='.', static_url_path='')
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'race-tracker-2026')

socketio = SocketIO(app, 
                   cors_allowed_origins="*",
                   async_mode='eventlet',
                   logger=False,
                   engineio_logger=False)

# Data storage
users = {}
crew = {}
emergencies = {}

data_lock = threading.Lock()

# Route data - Full coordinates
ROUTES = {
    "route_2k": {
        "id": "route_2k",
        "name": "2km Route",
        "path": [
            [25.0338, 121.5645],
            [25.0335, 121.5640],
            [25.0330, 121.5635],
            [25.0325, 121.5630],
            [25.0320, 121.5625],
            [25.0315, 121.5620],
            [25.0310, 121.5615],
            [25.0305, 121.5610],
            [25.0300, 121.5605],
            [25.0305, 121.5610],
            [25.0310, 121.5615],
            [25.0315, 121.5620],
            [25.0320, 121.5625],
            [25.0325, 121.5630],
            [25.0330, 121.5635],
            [25.0335, 121.5640],
            [25.0338, 121.5645]
        ],
        "color": "#3B82F6"
    },
    "route_5k": {
        "id": "route_5k", 
        "name": "5km Route",
        "path": [
            [25.0338, 121.5645],
            [25.0340, 121.5650],
            [25.0345, 121.5655],
            [25.0350, 121.5660],
            [25.0355, 121.5665],
            [25.0360, 121.5670],
            [25.0365, 121.5675],
            [25.0370, 121.5680],
            [25.0375, 121.5685],
            [25.0380, 121.5690],
            [25.0385, 121.5695],
            [25.0390, 121.5700],
            [25.0395, 121.5705],
            [25.0400, 121.5710],
            [25.0395, 121.5705],
            [25.0390, 121.5700],
            [25.0385, 121.5695],
            [25.0380, 121.5690],
            [25.0375, 121.5685],
            [25.0370, 121.5680],
            [25.0365, 121.5675],
            [25.0360, 121.5670],
            [25.0355, 121.5665],
            [25.0350, 121.5660],
            [25.0345, 121.5655],
            [25.0340, 121.5650],
            [25.0338, 121.5645]
        ],
        "color": "#10B981"
    },
    "route_10k": {
        "id": "route_10k",
        "name": "10km Route", 
        "path": [
            [25.0338, 121.5645],
            [25.0335, 121.5640],
            [25.0330, 121.5635],
            [25.0325, 121.5630],
            [25.0320, 121.5625],
            [25.0315, 121.5620],
            [25.0310, 121.5615],
            [25.0305, 121.5610],
            [25.0300, 121.5605],
            [25.0295, 121.5600],
            [25.0290, 121.5595],
            [25.0285, 121.5590],
            [25.0280, 121.5585],
            [25.0275, 121.5580],
            [25.0270, 121.5575],
            [25.0265, 121.5570],
            [25.0260, 121.5565],
            [25.0255, 121.5560],
            [25.0260, 121.5565],
            [25.0265, 121.5570],
            [25.0270, 121.5575],
            [25.0275, 121.5580],
            [25.0280, 121.5585],
            [25.0285, 121.5590],
            [25.0290, 121.5595],
            [25.0295, 121.5600],
            [25.0300, 121.5605],
            [25.0305, 121.5610],
            [25.0310, 121.5615],
            [25.0315, 121.5620],
            [25.0320, 121.5625],
            [25.0325, 121.5630],
            [25.0330, 121.5635],
            [25.0335, 121.5640],
            [25.0338, 121.5645]
        ],
        "color": "#8B5CF6"
    }
}

# Routes
@app.route('/')
def index():
    return send_from_directory('.', 'index.html')

@app.route('/crew')
def crew_page():
    return send_from_directory('.', 'crew.html')

@app.route('/api/routes')
def get_routes():
    return jsonify(ROUTES)

# WebSocket handlers
@socketio.on('connect')
def handle_connect():
    sid = request.sid
    emit('connected', {'sid': sid})

@socketio.on('disconnect')
def handle_disconnect():
    sid = request.sid
    
    with data_lock:
        if sid in users:
            del users[sid]
            emit('user_left', {'sid': sid}, broadcast=True)
        
        if sid in crew:
            del crew[sid]
            emit('crew_left', {'sid': sid}, broadcast=True)

@socketio.on('register_user')
def handle_register_user(data):
    sid = request.sid
    with data_lock:
        users[sid] = {
            'sid': sid,
            'name': 'Runner',
            'location': data.get('location', [25.0338, 121.5645]),
            'emergency': False,
            'last_update': datetime.now().isoformat()
        }
    
    emit('registration_success', {'user_id': sid})
    emit('user_joined', users[sid], broadcast=True)

@socketio.on('register_crew')
def handle_register_crew(data):
    sid = request.sid
    with data_lock:
        crew[sid] = {
            'sid': sid,
            'name': 'Crew',
            'location': data.get('location', [25.0338, 121.5645]),
            'transport': data.get('transport', 'walk'),
            'first_aid': data.get('first_aid', False),
            'last_update': datetime.now().isoformat()
        }
    
    emit('registration_success', {'crew_id': sid})
    emit('crew_joined', crew[sid], broadcast=True)

@socketio.on('user_location_update')
def handle_user_location(data):
    sid = request.sid
    with data_lock:
        if sid in users:
            users[sid].update({
                'location': [float(data.get('lat', 25.0338)), float(data.get('lng', 121.5645))],
                'emergency': data.get('emergency', False),
                'last_update': datetime.now().isoformat()
            })
            
            emit('user_location_updated', {
                'sid': sid,
                'name': users[sid]['name'],
                'location': users[sid]['location'],
                'emergency': users[sid]['emergency']
            }, broadcast=True)

@socketio.on('crew_location_update')
def handle_crew_location(data):
    sid = request.sid
    with data_lock:
        if sid in crew:
            crew[sid].update({
                'location': [float(data.get('lat', 25.0338)), float(data.get('lng', 121.5645))],
                'transport': data.get('transport', 'walk'),
                'first_aid': data.get('first_aid', False),
                'last_update': datetime.now().isoformat()
            })
            
            emit('crew_location_updated', {
                'sid': sid,
                'name': crew[sid]['name'],
                'location': crew[sid]['location'],
                'transport': crew[sid]['transport'],
                'first_aid': crew[sid]['first_aid']
            }, broadcast=True)

@socketio.on('emergency_request')
def handle_emergency(data):
    sid = request.sid
    emergency_id = str(uuid.uuid4())[:8]
    
    with data_lock:
        user_location = [25.0338, 121.5645]
        user_name = 'Runner'
        
        if sid in users:
            user_location = users[sid]['location']
            users[sid]['emergency'] = True
        
        emergencies[emergency_id] = {
            'emergency_id': emergency_id,
            'user_id': sid,
            'user_name': user_name,
            'location': user_location,
            'timestamp': datetime.now().isoformat(),
            'resolved': False
        }
    
    emit('emergency_alert', {
        'emergency_id': emergency_id,
        'user_id': sid,
        'user_name': user_name,
        'location': user_location
    }, broadcast=True)
    
    emit('emergency_confirmed', {
        'emergency_id': emergency_id
    })
    
    return {'emergency_id': emergency_id}

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
    
    return {'status': 'resolved'}

@socketio.on('get_initial_data')
def handle_get_initial_data():
    sid = request.sid
    with data_lock:
        active_emergencies = {k: v for k, v in emergencies.items() if not v.get('resolved', False)}
        
        users_data = {}
        for uid, user in users.items():
            if uid != sid:
                users_data[uid] = {
                    'name': 'Runner',
                    'location': user.get('location'),
                    'emergency': False
                }
        
        crew_data = {}
        for cid, c in crew.items():
            if cid != sid:
                crew_data[cid] = {
                    'name': 'Crew',
                    'location': c.get('location'),
                    'transport': c.get('transport', 'walk'),
                    'first_aid': c.get('first_aid', False)
                }
    
    emit('initial_data', {
        'users': users_data,
        'crew': crew_data,
        'emergencies': active_emergencies,
        'routes': ROUTES,
        'your_id': sid
    })

# Cleanup thread
def cleanup_old_data():
    while True:
        time.sleep(60)
        now = datetime.now()
        cutoff = 300
        
        with data_lock:
            for uid in list(users.keys()):
                if 'last_update' in users[uid]:
                    last_update = datetime.fromisoformat(users[uid]['last_update'])
                    if (now - last_update).total_seconds() > cutoff:
                        del users[uid]
            
            for cid in list(crew.keys()):
                if 'last_update' in crew[cid]:
                    last_update = datetime.fromisoformat(crew[cid]['last_update'])
                    if (now - last_update).total_seconds() > cutoff:
                        del crew[cid]

cleanup_thread = threading.Thread(target=cleanup_old_data, daemon=True)
cleanup_thread.start()

if __name__ == '__main__':
    socketio.run(app, host='0.0.0.0', port=8080, debug=False)