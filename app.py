"""
CopyNova AI - Telegram Service with Persistent Sessions
- Saves sessions to database
- Auto-reconnects on disconnect
- Uses user's own API ID & Hash
"""
import os
import asyncio
import json
import threading
import time
from datetime import datetime
from flask import Flask, request, jsonify

app = Flask(__name__)

# CopyNova's fallback API (used only if user doesn't provide their own)
FALLBACK_API_ID = int(os.environ.get('TELEGRAM_API_ID', '23111641'))
FALLBACK_API_HASH = os.environ.get('TELEGRAM_API_HASH', '6288120282735bf0fecc4753ee60b1b8')
SERVER_URL = os.environ.get('SERVER_URL', 'https://consoling-botch-sulphuric.ngrok-free.dev')

active_sessions = {}
session_lock = threading.Lock()

def save_session_to_server(phone, session_string, user_id, api_key):
    """Save session string to CopyNova database"""
    import requests
    try:
        requests.post(
            f"{SERVER_URL}/api/telegram/save-session",
            json={
                "phone": phone,
                "sessionString": session_string,
                "userId": user_id,
                "apiKey": api_key,
            },
            headers={"Content-Type": "application/json"},
            timeout=10
        )
    except Exception as e:
        print(f"Failed to save session: {e}")

def load_session_from_server(phone, user_id):
    """Load session string from CopyNova database"""
    import requests
    try:
        res = requests.get(
            f"{SERVER_URL}/api/telegram/get-session?phone={phone}&userId={user_id}",
            timeout=10
        )
        if res.status_code == 200:
            data = res.json()
            return data.get('sessionString')
    except:
        pass
    return None

def send_signal_to_server(phone, chat_title, chat_id, message_text, api_key, user_id, chat_type, is_public):
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
                "chatType": chat_type,
                "isPublic": is_public,
            },
            headers={"Content-Type": "application/json"},
            timeout=10
        )
    except Exception as e:
        print(f"Failed to forward signal: {e}")

async def monitor_channel(phone, chat_id, api_key, user_id, api_id, api_hash):
    """Monitor a specific channel with auto-reconnect"""
    from telethon import TelegramClient, events
    from telethon.sessions import StringSession
    
    while True:
        try:
            # Try to load existing session
            session_string = load_session_from_server(phone, user_id)
            
            if session_string:
                client = TelegramClient(StringSession(session_string), int(api_id), api_hash)
            else:
                client = TelegramClient(StringSession(), int(api_id), api_hash)
            
            await client.connect()
            
            # If not authorized, need new OTP
            if not await client.is_user_authorized():
                print(f"⚠️ Session expired for {phone}, needs re-verification")
                return
            
            entity = await client.get_entity(int(chat_id))
            chat_title = entity.title if hasattr(entity, 'title') else 'Unknown'
            is_public = hasattr(entity, 'username') and entity.username is not None
            
            # Save session
            session_string = client.session.save()
            save_session_to_server(phone, session_string, user_id, api_key)
            
            print(f"👂 Monitoring: {chat_title} for {phone}")
            
            @client.on(events.NewMessage(chats=[int(chat_id)]))
            async def handler(event):
                try:
                    message_text = event.message.text or event.message.caption or ''
                    if not message_text:
                        return
                    
                    upper = message_text.upper()
                    signal_keywords = ['BUY', 'SELL', 'LONG', 'SHORT', 'TP', 'SL', 'ENTRY',
                                      'XAUUSD', 'EURUSD', 'GBPUSD', 'USDJPY', 'BTCUSD',
                                      'GOLD', 'FOREX', 'NASDAQ', 'DOW']
                    
                    if any(kw in upper for kw in signal_keywords):
                        print(f"📨 Signal from {chat_title}: {message_text[:80]}...")
                        send_signal_to_server(phone, chat_title, chat_id, message_text, api_key, user_id,
                                            'channel' if hasattr(entity, 'broadcast') and entity.broadcast else 'group',
                                            is_public)
                except Exception as e:
                    print(f"Handler error: {e}")
            
            # Keep alive with heartbeat
            last_save = time.time()
            while True:
                await asyncio.sleep(5)
                
                # Check if still connected
                if not await client.is_user_authorized():
                    print(f"🔄 Session lost for {phone}, reconnecting...")
                    break
                
                # Save session every 5 minutes
                if time.time() - last_save > 300:
                    session_string = client.session.save()
                    save_session_to_server(phone, session_string, user_id, api_key)
                    last_save = time.time()
                    print(f"💾 Session saved for {phone}")
                
                # Check if channel still exists
                try:
                    await client.get_entity(int(chat_id))
                except:
                    print(f"⚠️ Channel {chat_id} not accessible")
                    break
                    
        except Exception as e:
            print(f"❌ Monitor error for {phone}: {e}")
            print(f"🔄 Reconnecting in 30 seconds...")
        
        # Wait before reconnect
        await asyncio.sleep(30)

@app.route('/')
def home():
    return jsonify({
        'service': 'CopyNova AI - Telegram Service',
        'status': 'running',
        'activeUsers': len(active_sessions)
    })

@app.route('/send-code', methods=['POST'])
def send_code():
    """Send OTP using user's own API credentials"""
    try:
        data = request.json
        phone = data.get('phone')
        api_id = data.get('apiId', FALLBACK_API_ID)
        api_hash = data.get('apiHash', FALLBACK_API_HASH)
        api_key = data.get('apiKey', '')
        user_id = data.get('userId', '')
        
        if not phone:
            return jsonify({'success': False, 'error': 'Phone number required'}), 400

        from telethon import TelegramClient
        from telethon.sessions import StringSession
        
        async def _send():
            client = TelegramClient(StringSession(), int(api_id), str(api_hash))
            await client.connect()
            result = await client.send_code_request(phone)
            session_string = client.session.save()
            
            with session_lock:
                active_sessions[phone] = {
                    'session_string': session_string,
                    'phone_code_hash': result.phone_code_hash,
                    'api_key': api_key,
                    'user_id': user_id,
                    'api_id': api_id,
                    'api_hash': api_hash,
                    'monitored_chat_id': None,
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
    """Verify OTP, get channels, and start monitoring"""
    try:
        data = request.json
        phone = data.get('phone')
        code = data.get('code')
        selected_chat_id = data.get('selectedChatId')
        
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
                int(session_data['api_id']), 
                str(session_data['api_hash'])
            )
            await client.connect()
            await client.sign_in(
                phone=phone,
                code=code,
                phone_code_hash=session_data['phone_code_hash']
            )
            
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
            
            # Save session to database
            session_string = client.session.save()
            save_session_to_server(phone, session_string, session_data['user_id'], session_data['api_key'])
            
            # Update active session
            session_data['session_string'] = session_string
            session_data['channels'] = channels
            
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
        
        # Start monitoring selected channel
        if selected_chat_id:
            session_data['monitored_chat_id'] = selected_chat_id
            monitor_thread = threading.Thread(
                target=run_monitor,
                args=(phone, selected_chat_id, session_data['api_key'], session_data['user_id'], 
                      session_data['api_id'], session_data['api_hash']),
                daemon=True
            )
            monitor_thread.start()
        
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

def run_monitor(phone, chat_id, api_key, user_id, api_id, api_hash):
    """Run the async monitor in a thread"""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(monitor_channel(phone, chat_id, api_key, user_id, api_id, api_hash))

@app.route('/reconnect-sessions', methods=['POST'])
def reconnect_sessions():
    """Reconnect all saved sessions from database"""
    data = request.json
    api_key = data.get('apiKey', '')
    
    # Get all users with saved sessions and reconnect
    import requests
    try:
        res = requests.get(
            f"{SERVER_URL}/api/telegram/get-all-sessions",
            timeout=10
        )
        if res.status_code == 200:
            sessions = res.json().get('sessions', [])
            for sess in sessions:
                if sess.get('phone') not in active_sessions:
                    # Start monitoring for this session
                    monitor_thread = threading.Thread(
                        target=run_monitor,
                        args=(sess['phone'], sess['chatId'], sess['apiKey'], sess['userId'],
                              sess.get('apiId', FALLBACK_API_ID), sess.get('apiHash', FALLBACK_API_HASH)),
                        daemon=True
                    )
                    monitor_thread.start()
                    print(f"🔄 Reconnected session for {sess['phone']}")
            return jsonify({'success': True, 'reconnected': len(sessions)})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})
    return jsonify({'success': True, 'reconnected': 0})

@app.route('/health')
def health():
    return jsonify({'status': 'healthy', 'users': len(active_sessions)})

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
