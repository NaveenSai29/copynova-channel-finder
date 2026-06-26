"""
CopyNova AI - Telegram Microservice
Handles OTP sending and channel fetching
"""
import os
import asyncio
from flask import Flask, request, jsonify

app = Flask(__name__)

API_ID = int(os.environ.get('TELEGRAM_API_ID', '23111641'))
API_HASH = os.environ.get('TELEGRAM_API_HASH', '6288120282735bf0fecc4753ee60b1b8')

sessions = {}

@app.route('/')
def home():
    return jsonify({'service': 'CopyNova AI - Telegram Service', 'status': 'running'})

@app.route('/send-code', methods=['POST'])
def send_code():
    try:
        data = request.json
        phone = data.get('phone')
        
        if not phone:
            return jsonify({'success': False, 'error': 'Phone number required'}), 400

        from telethon import TelegramClient
        from telethon.sessions import StringSession
        
        async def _send():
            client = TelegramClient(StringSession(), API_ID, API_HASH)
            await client.connect()
            result = await client.send_code_request(phone)
            session_string = client.session.save()
            sessions[phone] = {
                'session_string': session_string,
                'phone_code_hash': result.phone_code_hash
            }
            return True
        
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(_send())
        
        return jsonify({
            'success': True,
            'message': f'OTP sent to {phone}. Check your Telegram app!',
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
        
        if not phone or not code:
            return jsonify({'success': False, 'error': 'Phone and code required'}), 400
        
        session_data = sessions.get(phone)
        if not session_data:
            return jsonify({'success': False, 'error': 'No active session. Please send OTP again.'}), 400

        from telethon import TelegramClient
        from telethon.sessions import StringSession
        from telethon.tl.functions.messages import GetDialogsRequest
        from telethon.tl.types import InputPeerEmpty
        
        async def _verify():
            client = TelegramClient(
                StringSession(session_data['session_string']), 
                API_ID, 
                API_HASH
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
                    
                    # Get the ID and ensure proper format for Telegram Bot API
                    raw_id = str(entity.id)
                    
                    # Channels and supergroups need -100 prefix for Bot API
                    if hasattr(entity, 'broadcast') and entity.broadcast:
                        # It's a channel
                        if raw_id.startswith('-100'):
                            channel_id = raw_id
                        else:
                            channel_id = f'-100{raw_id}'
                        channels.append({
                            'id': channel_id,
                            'title': entity.title,
                            'type': 'channel'
                        })
                    elif hasattr(entity, 'megagroup') and entity.megagroup:
                        # It's a supergroup
                        if raw_id.startswith('-100'):
                            channel_id = raw_id
                        else:
                            channel_id = f'-100{raw_id}'
                        channels.append({
                            'id': channel_id,
                            'title': entity.title,
                            'type': 'group'
                        })
                except Exception as e:
                    print(f"Error processing dialog: {e}")
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
