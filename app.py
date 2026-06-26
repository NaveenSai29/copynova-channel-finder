"""
CopyNova AI - Telegram Service
Runs 24/7 on Streamlit Cloud - Handles OTP and channel fetching
"""
import streamlit as st
import requests
import asyncio
import sys
import json

st.set_page_config(page_title="CopyNova AI - Telegram Service", page_icon="🔐")

# Install telethon if needed
try:
    from telethon import TelegramClient
    from telethon.tl.functions.messages import GetDialogsRequest
    from telethon.tl.types import InputPeerEmpty
except ImportError:
    import subprocess
    subprocess.check_call([sys.executable, "-m", "pip", "install", "telethon", "cryptg"])
    from telethon import TelegramClient
    from telethon.tl.functions.messages import GetDialogsRequest
    from telethon.tl.types import InputPeerEmpty

# CopyNova's Telegram API credentials
API_ID = 23111641
API_HASH = "6288120282735bf0fecc4753ee60b1b8"

# Initialize session state
if "sessions" not in st.session_state:
    st.session_state.sessions = {}

st.title("🔐 CopyNova AI - Telegram Service")
st.caption("Handles OTP verification and channel fetching")

# API endpoint handler
st.subheader("API Endpoints")

tab1, tab2 = st.tabs(["Send OTP", "Verify & Fetch"])

with tab1:
    st.write("**POST /send-code**")
    phone = st.text_input("Phone Number", key="send_phone", placeholder="+919876543210")
    
    if st.button("Send OTP"):
        try:
            async def send():
                client = TelegramClient(f'session_{phone}', API_ID, API_HASH)
                await client.connect()
                result = await client.send_code_request(phone)
                st.session_state.sessions[phone] = {
                    'client': client,
                    'phone_code_hash': result.phone_code_hash
                }
                return True
            
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(send())
            st.success(f"✅ OTP sent to {phone}! Check Telegram app.")
        except Exception as e:
            st.error(f"Failed: {str(e)}")

with tab2:
    st.write("**POST /verify-code**")
    phone2 = st.text_input("Phone Number", key="verify_phone", placeholder="+919876543210")
    code = st.text_input("OTP Code", key="verify_code", placeholder="12345")
    
    if st.button("Verify & Fetch Channels"):
        session_data = st.session_state.sessions.get(phone2)
        if not session_data:
            st.error("No active session. Send OTP first!")
        else:
            try:
                async def verify():
                    client = session_data['client']
                    await client.sign_in(
                        phone=phone2,
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
                            if hasattr(entity, 'broadcast') and entity.broadcast:
                                channels.append({'id': str(entity.id), 'title': entity.title, 'type': 'channel'})
                            elif hasattr(entity, 'megagroup') and entity.megagroup:
                                channels.append({'id': str(entity.id), 'title': entity.title, 'type': 'group'})
                        except:
                            pass
                    
                    await client.disconnect()
                    del st.session_state.sessions[phone2]
                    return channels
                
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                channels = loop.run_until_complete(verify())
                
                st.success(f"✅ Found {len(channels)} channels!")
                st.json(channels)
            except Exception as e:
                st.error(f"Failed: {str(e)}")
