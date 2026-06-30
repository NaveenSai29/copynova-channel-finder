"""
CopyNova AI - Telegram Service (Multi-User)
Monitors channels for signals via Telethon (User Account - No Bot Needed)
Processes ALL messages - AI decides what's a signal
"""
import os
import asyncio
import threading
from flask import Flask, request, jsonify

app = Flask(__name__)

# Default credentials (users can use their own)
DEFAULT_API_ID = int(os.environ.get('TELEGRAM_API_ID', '23111641'))
DEFAULT_API_HASH = os.environ.get('TELEGRAM_API_HASH', '6288120282735bf0fecc4753ee60b1b8')
SERVER_URL = os.environ.get('SERVER_URL', 'https://your-server.com')

active_sessions = {}
session_lock = threading.Lock()

def get_credentials(user_api_id=None, user_api_hash=None):
    """Get API credentials - user's own or fallback to default"""
    api_id = int(user_api_id) if user_api_id else DEFAULT_API_ID
    api_hash = user_api_hash if user_api_hash else DEFAULT_API_HASH
    return api_id, api_hash

def send_signal_to_server(phone, chat_title, chat_id, message_text, api_key, user_id, chat_type, is_public):
    """Forward a message to the CopyNova server - AI decides if it's a signal"""
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
                "chatType": chat_type,
                "isPublic": is_public,
            },
            headers={"Content-Type": "application/json"},
            timeout=10
        )
        print(f"📤 Sent: {message_text[:50]}... Status: {res.status_code}")
    except Exception as e:
        print(f"❌ Failed to send: {e}")

async def monitor_channel(phone, chat_id, api_key, user_id, user_api_id, user_api_hash):
    """Monitor a channel - send ALL messages to server using user's API credentials"""
    from telethon import TelegramClient, events
    from telethon.sessions import StringSession
    
    session_data = active_sessions.get(phone)
    if not session_data:
        return
    
    api_id, api_hash = get_credentials(user_api_id, user_api_hash)
    
    try:
        client = TelegramClient(
            StringSession(session_data['session_string']),
            api_id, api_hash
        )
        await client.connect()
        
        entity = await client.get_entity(int(chat_id))
        chat_title = entity.title if hasattr(entity, 'title') else 'Unknown'
        is_broadcast = hasattr(entity, 'broadcast') and entity.broadcast
        is_megagroup = hasattr(entity, 'megagroup') and entity.megagroup
        is_public = hasattr(entity, 'username') and entity.username is not None
        chat_type = 'channel' if is_broadcast else 'group' if is_megagroup else 'private'
        
        print(f"👂 Monitoring: {chat_title} (Type: {chat_type})")
        
        @client.on(events.NewMessage(chats=[int(chat_id)]))
        async def handler(event):
            try:
                message_text = event.message.text or event.message.caption or ''
                if message_text:
                    print(f"📨 Message from {chat_title}: {message_text[:80]}...")
                    send_signal_to_server(
                        phone, chat_title, chat_id, message_text,
                        api_key, user_id, chat_type, is_public
                    )
            except Exception as e:
                print(f"Handler error: {e}")
        
        while phone in active_sessions:
            await asyncio.sleep(1)
            
    except Exception as e:
        print(f"Monitor error for {phone}: {e}")
    finally:
        await client.disconnect()

@app.route('/')
def home():
    return jsonify({
        'service': 'CopyNova AI - Telegram Service',
        'status': 'running',
        'activeUsers': len(active_sessions)
    })

@app.route('/send-code', methods=['POST'])
def send_code():
    try:
        data = request.json
        phone = data.get('phone')
        api_key = data.get('apiKey', '')
        user_id = data.get('userId', '')
        user_api_id = data.get('apiId')
        user_api_hash = data.get('apiHash')
        
        if not phone:
            return jsonify({'success': False, 'error': 'Phone number required'}), 400

        api_id, api_hash = get_credentials(user_api_id, user_api_hash)

        from telethon import TelegramClient
        from telethon.sessions import StringSession
        
        async def _send():
            client = TelegramClient(StringSession(), api_id, api_hash)
            await client.connect()
            result = await client.send_code_request(phone)
            session_string = client.session.save()
            
            with session_lock:
                active_sessions[phone] = {
                    'session_string': session_string,
                    'phone_code_hash': result.phone_code_hash,
                    'api_key': api_key,
                    'user_id': user_id,
                    'user_api_id': user_api_id,
                    'user_api_hash': user_api_hash,
                    'monitored_chat_id': None,
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
    try:
        data = request.json
        phone = data.get('phone')
        code = data.get('code')
        selected_chat_id = data.get('selectedChatId')
        
        if not phone or not code:
            return jsonify({'success': False, 'error': 'Phone and code required'}), 400
        
        session_data = active_sessions.get(phone)
        if not session_data:
            return jsonify({'success': False, 'error': 'Send OTP first'}), 400

        user_api_id = session_data.get('user_api_id')
        user_api_hash = session_data.get('user_api_hash')
        api_id, api_hash = get_credentials(user_api_id, user_api_hash)

        from telethon import TelegramClient
        from telethon.sessions import StringSession
        from telethon.tl.functions.messages import GetDialogsRequest
        from telethon.tl.types import InputPeerEmpty
        
        async def _verify():
            client = TelegramClient(
                StringSession(session_data['session_string']), 
                api_id, api_hash
            )
            await client.connect()
            await client.sign_in(phone=phone, code=code,
                phone_code_hash=session_data['phone_code_hash'])
            
            dialogs = await client(GetDialogsRequest(
                offset_date=None, offset_id=0, offset_peer=InputPeerEmpty(),
                limit=200, hash=0
            ))
            
            channels = []
            for dialog in dialogs.dialogs:
                try:
                    entity = await client.get_entity(dialog.peer)
                    raw_id = str(entity.id)
                    
                    is_broadcast = hasattr(entity, 'broadcast') and entity.broadcast
                    is_megagroup = hasattr(entity, 'megagroup') and entity.megagroup
                    has_username = hasattr(entity, 'username') and entity.username is not None
                    
                    if is_broadcast or is_megagroup:
                        channel_id = f'-100{raw_id}' if not raw_id.startswith('-100') else raw_id
                        channels.append({
                            'id': channel_id,
                            'title': entity.title,
                            'type': 'channel' if is_broadcast else 'group',
                            'visibility': 'public' if has_username else 'private',
                            'username': entity.username if has_username else None,
                        })
                except:
                    pass
            
            session_data['session_string'] = client.session.save()
            session_data['channels'] = channels
            return channels
        
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        channels = loop.run_until_complete(_verify())
        
        # Sync channels to server
        import requests
        try:
            requests.post(
                f"{SERVER_URL}/api/user/sync-channels",
                json={"channels": channels, "apiKey": session_data.get('api_key', '')},
                headers={"Content-Type": "application/json"},
                timeout=10
            )
        except:
            pass
        
        if selected_chat_id:
            session_data['monitored_chat_id'] = selected_chat_id
            monitor_thread = threading.Thread(
                target=run_monitor,
                args=(phone, selected_chat_id, session_data['api_key'], 
                      session_data['user_id'], user_api_id, user_api_hash),
                daemon=True
            )
            monitor_thread.start()
            session_data['monitor_thread'] = monitor_thread
        
        return jsonify({
            'success': True,
            'channels': channels,
            'count': len(channels),
            'monitoring': selected_chat_id is not None
        })
    except Exception as e:
        print(f"Verify error: {e}")
        if phone in active_sessions:
            del active_sessions[phone]
        return jsonify({'success': False, 'error': str(e)}), 500

def run_monitor(phone, chat_id, api_key, user_id, user_api_id, user_api_hash):
    """Run the monitor in a new event loop"""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(monitor_channel(phone, chat_id, api_key, user_id, user_api_id, user_api_hash))

@app.route('/start-monitoring', methods=['POST'])
def start_monitoring():
    data = request.json
    phone = data.get('phone')
    chat_id = data.get('chatId')
    session_data = active_sessions.get(phone)
    if not session_data:
        return jsonify({'success': False, 'error': 'No active session'}), 404
    
    session_data['monitored_chat_id'] = chat_id
    monitor_thread = threading.Thread(
        target=run_monitor,
        args=(phone, chat_id, session_data['api_key'], session_data['user_id'],
              session_data.get('user_api_id'), session_data.get('user_api_hash')),
        daemon=True
    )
    monitor_thread.start()
    session_data['monitor_thread'] = monitor_thread
    return jsonify({'success': True, 'message': 'Monitoring started'})

@app.route('/stop-monitoring', methods=['POST'])
def stop_monitoring():
    data = request.json
    phone = data.get('phone')
    if phone in active_sessions:
        del active_sessions[phone]
        return jsonify({'success': True})
    return jsonify({'success': False, 'error': 'No active session'}), 404

@app.route('/status')
def status():
    return jsonify({
        'activeUsers': len(active_sessions), 
        'users': list(active_sessions.keys())
    })

@app.route('/health')
def health():
    return jsonify({
        'status': 'healthy', 
        'users': len(active_sessions)
    })

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)