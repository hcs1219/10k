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

# 數據存儲
users = {}
crew = {}
emergencies = {}

data_lock = threading.Lock()

# 路線數據
ROUTES = {
    "route_2k": {
        "id": "route_2k",
        "name": "2km 路線",
        "path": [
            [25.0338, 121.5645],
            [25.0335, 121.5640],
            [25.0330, 121.5635],
            [25.0325, 121.5630]
        ],
        "color": "#3B82F6"
    },
    "route_5k": {
        "id": "route_5k", 
        "name": "5km 路線",
        "path": [
            [25.0338, 121.5645],
            [25.0345, 121.5655],
            [25.0355, 121.5665],
            [25.0365, 121.5675]
        ],
        "color": "#10B981"
    },
    "route_10k": {
        "id": "route_10k",
        "name": "10km 路線", 
        "path": [
            [25.0338, 121.5645],
            [25.0330, 121.5635],
            [25.0320, 121.5625],
            [25.0310, 121.5615]
        ],
        "color": "#8B5CF6"
    }
}

# 路由
@app.route('/')
def index():
    return send_from_directory('.', 'index.html')

@app.route('/crew')
def crew_page():
    return send_from_directory('.', 'crew.html')

@app.route('/api/routes')
def get_routes():
    return jsonify(ROUTES)

# WebSocket 處理
@socketio.on('connect')
def handle_connect():
    sid = request.sid
    print(f'連接: {sid}')
    emit('connected', {'sid': sid})

@socketio.on('disconnect')
def handle_disconnect():
    sid = request.sid
    print(f'斷線: {sid}')
    
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
            'name': f'跑者-{sid[-4:]}',
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
            'name': f'工作人員-{sid[-4:]}',
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
        user_name = f'跑者-{sid[-4:]}'
        
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
                    'name': user.get('name'),
                    'location': user.get('location'),
                    'emergency': False  # 跑者看不到其他人的緊急狀態
                }
        
        crew_data = {}
        for cid, c in crew.items():
            if cid != sid:
                crew_data[cid] = {
                    'name': c.get('name'),
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

# 清理線程
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
    port = int(os.environ.get('PORT', 5000))
    socketio.run(app, host='0.0.0.0', port=port, debug=False)