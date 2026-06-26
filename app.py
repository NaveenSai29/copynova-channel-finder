"""
CopyNova AI - Telegram Service (Multi-User)
Monitors ALL channels for ALL users via Telethon
"""
import os
import asyncio
import json
import threading
import time
from datetime import datetime
from flask import Flask, request, jsonify

app = Flask(__name__)

API_ID = int(os.environ.get('TELEGRAM_API_ID', '23111641'))
API_HASH = os.environ.get('TELEGRAM_API_HASH', '6288120282735bf0fecc4753ee60b1b8')
SERVER_URL = os.environ.get('SERVER_URL', 'https://consoling-botch-sulphuric.ngrok-free.dev')

# Store active user sessions
active_sessions = {}  # phone -> {client, channels, api_key, user_id}
session_lock = threading.Lock()

def send_signal_to_server(phone, chat_title, chat_id, message_text, api_key, user_id):
    """Forward a signal to the CopyNova server"""
    import requests
    try:
        res = requests.post(
            f"{SERVER_URL}/api/telegram/signal-from-member",
            json={
                "phone": phone,
                "chatTitle": chat_title,
                "chatId": str(chat_id),
                "message": message_text,
                "apiKey": api_key,
                "userId": user_id,
            },
            headers={"Content-Type": "application/json"},
            timeout=10
        )
        print(f"📤 Forwarded signal from {chat_title}: {message_text[:50]}... Status: {res.status_code}")
    except Exception as e:
        print(f"❌ Failed to forward: {e}")

async def monitor_user_channels(phone, api_key, user_id):
    """Monitor all channels for a specific user"""
    from telethon import TelegramClient, events
    from telethon.sessions import StringSession
    
    session_data = active_sessions.get(phone)
    if not session_data:
        return
    
    try:
        client = TelegramClient(
            StringSession(session_data['session_string']),
            API_ID, API_HASH
        )
        await client.connect()
        
        print(f"👂 Started monitoring for {phone} (User: {user_id})")
        
        @client.on(events.NewMessage)
        async def handler(event):
            try:
                chat = await event.get_chat()
                message_text = event.message.text or event.message.caption or ''
                
                if not message_text:
                    return
                
                # Check if message looks like a trading signal
                upper = message_text.upper()
                signal_keywords = ['BUY', 'SELL', 'LONG', 'SHORT', 'TP', 'SL', 'ENTRY', 
                                  'XAUUSD', 'EURUSD', 'GBPUSD', 'USDJPY', 'BTCUSD',
                                  'GOLD', 'FOREX', 'NASDAQ', 'DOW']
                
                if any(kw in upper for kw in signal_keywords):
                    print(f"📨 Signal detected from {chat.title}: {message_text[:80]}...")
                    send_signal_to_server(
                        phone, chat.title, chat.id, message_text, api_key, user_id
                    )
            except Exception as e:
                print(f"Handler error: {e}")
        
        # Keep the connection alive
        while phone in active_sessions:
            await asyncio.sleep(1)
            
    except Exception as e:
        print(f"Monitor error for {phone}: {e}")
    finally:
        await client.disconnect()
        print(f"🔌 Disconnected monitor for {phone}")

@app.route('/')
def home():
    return jsonify({
        'service': 'CopyNova AI - Telegram Service',
        'status': 'running',
        'activeUsers': len(active_sessions)
    })

@app.route('/send-code', methods=['POST'])
def send_code():
    """Send OTP to user's phone"""
    try:
        data = request.json
        phone = data.get('phone')
        api_key = data.get('apiKey', '')
        user_id = data.get('userId', '')
        
        if not phone:
            return jsonify({'success': False, 'error': 'Phone number required'}), 400

        from telethon import TelegramClient
        from telethon.sessions import StringSession
        
        async def _send():
            client = TelegramClient(StringSession(), API_ID, API_HASH)
            await client.connect()
            result = await client.send_code_request(phone)
            session_string = client.session.save()
            
            with session_lock:
                active_sessions[phone] = {
                    'session_string': session_string,
                    'phone_code_hash': result.phone_code_hash,
                    'api_key': api_key,
                    'user_id': user_id,
                    'client': None,
                    'monitor_thread': None,
                }
            return True
        
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(_send())
        
        return jsonify({
            'success': True,
            'message': f'OTP sent to {phone}. Check Telegram!',
            'phoneHash': phone[-4:]
        })
    except Exception as e:
        print(f"Send code error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/verify-code', methods=['POST'])
def verify_code():
    """Verify OTP and start monitoring channels"""
    try:
        data = request.json
        phone = data.get('phone')
        code = data.get('code')
        
        if not phone or not code:
            return jsonify({'success': False, 'error': 'Phone and code required'}), 400
        
        session_data = active_sessions.get(phone)
        if not session_data:
            return jsonify({'success': False, 'error': 'No active session. Send OTP first.'}), 400

        from telethon import TelegramClient
        from telethon.sessions import StringSession
        from telethon.tl.functions.messages import GetDialogsRequest
        from telethon.tl.types import InputPeerEmpty
        
        async def _verify():
            client = TelegramClient(
                StringSession(session_data['session_string']), 
                API_ID, API_HASH
            )
            await client.connect()
            await client.sign_in(
                phone=phone,
                code=code,
                phone_code_hash=session_data['phone_code_hash']
            )
            
            # Get all channels
            dialogs = await client(GetDialogsRequest(
                offset_date=None, offset_id=0, offset_peer=InputPeerEmpty(),
                limit=200, hash=0
            ))
            
            channels = []
            for dialog in dialogs.dialogs:
                try:
                    entity = await client.get_entity(dialog.peer)
                    raw_id = str(entity.id)
                    
                    if hasattr(entity, 'broadcast') and entity.broadcast:
                        channel_id = f'-100{raw_id}' if not raw_id.startswith('-100') else raw_id
                        channels.append({'id': channel_id, 'title': entity.title, 'type': 'channel'})
                    elif hasattr(entity, 'megagroup') and entity.megagroup:
                        channel_id = f'-100{raw_id}' if not raw_id.startswith('-100') else raw_id
                        channels.append({'id': channel_id, 'title': entity.title, 'type': 'group'})
                except:
                    pass
            
            # Save updated session
            session_data['session_string'] = client.session.save()
            session_data['channels'] = channels
            
            # Start monitoring in a background thread
            monitor_thread = threading.Thread(
                target=run_monitor,
                args=(phone, session_data['api_key'], session_data['user_id']),
                daemon=True
            )
            monitor_thread.start()
            session_data['monitor_thread'] = monitor_thread
            
            return channels
        
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        channels = loop.run_until_complete(_verify())
        
        # Sync channels to server
        import requests
        try:
            requests.post(
                f"{SERVER_URL}/api/user/sync-channels?key={session_data.get('api_key', '')}",
                json={"channels": channels},
                headers={"Content-Type": "application/json"},
                timeout=10
            )
        except:
            pass
        
        return jsonify({
            'success': True,
            'channels': channels,
            'count': len(channels),
            'message': f'Monitoring {len(channels)} channels for signals!'
        })
    except Exception as e:
        print(f"Verify error: {e}")
        if phone in active_sessions:
            del active_sessions[phone]
        return jsonify({'success': False, 'error': str(e)}), 500

def run_monitor(phone, api_key, user_id):
    """Run the async monitor in a thread"""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(monitor_user_channels(phone, api_key, user_id))

@app.route('/stop-monitoring', methods=['POST'])
def stop_monitoring():
    """Stop monitoring for a user"""
    data = request.json
    phone = data.get('phone')
    
    if phone in active_sessions:
        del active_sessions[phone]
        return jsonify({'success': True, 'message': 'Monitoring stopped'})
    return jsonify({'success': False, 'error': 'No active session'}), 404

@app.route('/status')
def status():
    return jsonify({
        'activeUsers': len(active_sessions),
        'users': list(active_sessions.keys())
    })

@app.route('/health')
def health():
    return jsonify({'status': 'healthy', 'users': len(active_sessions)})

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
