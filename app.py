from flask import Flask, render_template
from flask_socketio import SocketIO, emit, join_room
import eventlet

eventlet.monkey_patch()

# 模板和靜態檔案都在當前資料夾
app = Flask(__name__, template_folder='.', static_folder='.')
app.config['SECRET_KEY'] = 'race2026'
socketio = SocketIO(app, cors_allowed_origins="*")

# 香港三條跑步路線（有交會點）
ROUTES = {
    'red': [[22.3964,114.1095],[22.4000,114.1150],[22.4050,114.1200]],
    'green': [[22.3980,114.1120],[22.4020,114.1180],[22.4070,114.1250]], 
    'blue': [[22.3950,114.1100],[22.4030,114.1170],[22.4060,114.1220]]
}

staff_locations = {}
active_emergencies = {}

@app.route('/')
def user_page():
    return render_template('user.html', routes=ROUTES)

@app.route('/staff')
def staff_page():
    return render_template('staff.html', routes=ROUTES)

@socketio.on('join_staff_room')
def join_staff(data):
    join_room('staff')

@socketio.on('gps_share')
def gps_update(data):
    staff_locations[data['staffId']] = {
        'lat': data['lat'], 'lng': data['lng'], 
        'mode': data['mode'], 'firstaid': data['firstaid']
    }
    emit('staff_update', data, broadcast=True)

@socketio.on('emergency_call')
def emergency_alert(data):
    user_id = data['userId']
    active_emergencies[user_id] = {
        'userId': user_id, 'lat': data['lat'], 'lng': data['lng'], 'time': data['time']
    }
    emit('emergency_alert', active_emergencies[user_id], room='staff')

@socketio.on('cancel_emergency')
def cancel_emergency(data):
    user_id = data['userId']
    if user_id in active_emergencies:
        del active_emergencies[user_id]
    emit('emergency_cleared', {'userId': user_id}, room='staff')

if __name__ == '__main__':
    socketio.run(app, debug=True, host='0.0.0.0', port=5000)
