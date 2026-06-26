"""
CopyNova AI - Telegram Microservice
Handles OTP sending and channel fetching
Deployed on Render.com
"""
import os
import asyncio
import json
from flask import Flask, request, jsonify

app = Flask(__name__)

# CopyNova's Telegram API credentials (set in Render environment variables)
API_ID = int(os.environ.get('TELEGRAM_API_ID', '23111641'))
API_HASH = os.environ.get('TELEGRAM_API_HASH', '6288120282735bf0fecc4753ee60b1b8')

# Store active sessions (in production, use Redis)
sessions = {}

@app.route('/')
def home():
    return jsonify({'service': 'CopyNova AI - Telegram Service', 'status': 'running'})

@app.route('/send-code', methods=['POST'])
def send_code():
    """Send OTP to user's Telegram"""
    try:
        data = request.json
        phone = data.get('phone')
        
        if not phone:
            return jsonify({'success': False, 'error': 'Phone number required'}), 400
        
        # Import here to avoid cold start issues
        from telethon import TelegramClient
        
        async def _send():
            client = TelegramClient(f'session_{phone.replace("+", "")}', API_ID, API_HASH)
            await client.connect()
            result = await client.send_code_request(phone)
            sessions[phone] = {
                'client': client,
                'phone_code_hash': result.phone_code_hash
            }
            return True
        
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(_send())
        
        return jsonify({
            'success': True,
            'message': f'OTP sent to {phone}. Check your Telegram app!',
            'phoneHash': phone[-4:]  # Last 4 digits for verification
        })
    except Exception as e:
        print(f"Send code error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/verify-code', methods=['POST'])
def verify_code():
    """Verify OTP and fetch channels"""
    try:
        data = request.json
        phone = data.get('phone')
        code = data.get('code')
        
        if not phone or not code:
            return jsonify({'success': False, 'error': 'Phone and code required'}), 400
        
        session_data = sessions.get(phone)
        if not session_data:
            return jsonify({'success': False, 'error': 'No active session. Send OTP first.'}), 400
        
        from telethon import TelegramClient
        from telethon.tl.functions.messages import GetDialogsRequest
        from telethon.tl.types import InputPeerEmpty
        
        async def _verify():
            client = session_data['client']
            await client.sign_in(
                phone=phone,
                code=code,
                phone_code_hash=session_data['phone_code_hash']
            )
            
            print(f"✅ Signed in as {phone}")
            
            dialogs = await client(GetDialogsRequest(
                offset_date=None, offset_id=0, offset_peer=InputPeerEmpty(),
                limit=200, hash=0
            ))
            
            channels = []
            for dialog in dialogs.dialogs:
                try:
                    entity = await client.get_entity(dialog.peer)
                    if hasattr(entity, 'broadcast') and entity.broadcast:
                        channels.append({
                            'id': str(entity.id),
                            'title': entity.title,
                            'type': 'channel'
                        })
                    elif hasattr(entity, 'megagroup') and entity.megagroup:
                        channels.append({
                            'id': str(entity.id),
                            'title': entity.title,
                            'type': 'group'
                        })
                except:
                    pass
            
            await client.disconnect()
            del sessions[phone]
            return channels
        
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        channels = loop.run_until_complete(_verify())
        
        return jsonify({
            'success': True,
            'channels': channels,
            'count': len(channels)
        })
    except Exception as e:
        print(f"Verify error: {e}")
        if phone in sessions:
            del sessions[phone]
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/health')
def health():
    return jsonify({'status': 'healthy'})

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
