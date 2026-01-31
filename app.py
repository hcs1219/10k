from flask import Flask, render_template
from flask_socketio import SocketIO, emit, request

app = Flask(__name__,
            template_folder='.')           # ← important: look for templates in same folder as app.py

app.config['SECRET_KEY'] = 'dev-key-change-me-in-production'

socketio = SocketIO(app, cors_allowed_origins="*", async_mode='eventlet')

# In-memory state (sid → data)
participants = {}
staff_members = {}


@app.route('/')
def participant():
    return render_template('index.html')


@app.route('/staff')
def staff():
    return render_template('staff.html')


# ────────────────────────────────────────────────
# SocketIO events
# ────────────────────────────────────────────────

@socketio.on('connect')
def on_connect():
    print(f"Client connected: {request.sid}")


@socketio.on('disconnect')
def on_disconnect():
    participants.pop(request.sid, None)
    staff_members.pop(request.sid, None)
    broadcast_state()


@socketio.on('update_location')
def on_location(data):
    sid = request.sid
    role = data.get('role')

    if role == 'participant':
        participants[sid] = {
            'lat': data.get('lat'),
            'lng': data.get('lng'),
            'name': data.get('name', f"Runner-{sid[:6]}"),
            'emergency': participants.get(sid, {}).get('emergency', False)
        }
    elif role == 'staff':
        share = data.get('share_location', False)
        staff_members[sid] = {
            'lat': data.get('lat') if share else None,
            'lng': data.get('lng') if share else None,
            'name': data.get('name', 'Staff'),
            'transport': data.get('transport', 'walk'),
            'first_aid': data.get('first_aid', False),
            'share_location': share
        }

    broadcast_state()


@socketio.on('emergency')
def on_emergency(_):
    sid = request.sid
    if sid in participants:
        participants[sid]['emergency'] = True
        emit('emergency_alert', {'name': participants[sid]['name']}, broadcast=True)
        broadcast_state()


@socketio.on('cancel_emergency')
def on_cancel():
    sid = request.sid
    if sid in participants:
        participants[sid]['emergency'] = False
        broadcast_state()


def broadcast_state():
    emit('update_all', {
        'participants': participants,
        'staff': staff_members
    }, broadcast=True)


if __name__ == '__main__':
    socketio.run(app, host='0.0.0.0', port=8000, debug=True, allow_unsafe_werkzeug=True)