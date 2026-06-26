import streamlit as st
import requests
import subprocess
import json
import os
import sys

st.set_page_config(page_title="CopyNova AI - Channel Finder", page_icon="🔍")

st.title("🔍 CopyNova AI - Channel Finder")
st.caption("Find your Telegram channels and sync them to your dashboard")

SERVER_URL = "https://consoling-botch-sulphuric.ngrok-free.dev"

# Initialize session state
if "step" not in st.session_state:
    st.session_state.step = "credentials"
if "found_channels" not in st.session_state:
    st.session_state.found_channels = []
if "api_key" not in st.session_state:
    st.session_state.api_key = ""

# Install telethon if needed
try:
    import telethon
except ImportError:
    subprocess.check_call([sys.executable, "-m", "pip", "install", "telethon", "cryptg"])

# ============ STEP 1: CREDENTIALS ============
if st.session_state.step == "credentials":
    st.subheader("Step 1: CopyNova API Key")
    api_key = st.text_input("Enter your CopyNova API Key", type="password",
        help="Get this from your CopyNova dashboard → API Keys")
    
    st.subheader("Step 2: Telegram API Credentials")
    st.caption("Get these from [my.telegram.org](https://my.telegram.org)")
    api_id = st.text_input("API ID")
    api_hash = st.text_input("API Hash", type="password")
    phone = st.text_input("Phone Number (+91...)", placeholder="+919876543210")
    
    if st.button("🔍 Find My Channels", type="primary", disabled=not (api_key and api_id and api_hash and phone)):
        # Create a Python script that runs telethon independently
        script = f'''
import asyncio
import json
import sys
sys.path.insert(0, '{os.path.dirname(os.path.abspath(__file__))}')

async def main():
    from telethon import TelegramClient
    from telethon.tl.functions.messages import GetDialogsRequest
    from telethon.tl.types import InputPeerEmpty
    
    client = TelegramClient('session_{phone}', {api_id}, '{api_hash}')
    await client.start(phone='{phone}')
    
    dialogs = await client(GetDialogsRequest(
        offset_date=None, offset_id=0, offset_peer=InputPeerEmpty(),
        limit=200, hash=0
    ))
    
    channels = []
    for dialog in dialogs.dialogs:
        try:
            entity = await client.get_entity(dialog.peer)
            if hasattr(entity, 'broadcast') and entity.broadcast:
                channels.append({{'id': str(entity.id), 'title': entity.title, 'type': 'channel'}})
            elif hasattr(entity, 'megagroup') and entity.megagroup:
                channels.append({{'id': str(entity.id), 'title': entity.title, 'type': 'group'}})
        except:
            pass
    
    await client.disconnect()
    print(json.dumps(channels))

asyncio.run(main())
'''
        
        script_path = '/tmp/find_channels.py'
        with open(script_path, 'w') as f:
            f.write(script)
        
        with st.spinner("Connecting to Telegram... This may take a moment."):
            try:
                result = subprocess.run(
                    [sys.executable, script_path],
                    capture_output=True, text=True, timeout=60
                )
                
                if result.returncode == 0:
                    output = result.stdout.strip()
                    # Find the JSON part (last line)
                    lines = output.split('\n')
                    json_line = None
                    for line in reversed(lines):
                        line = line.strip()
                        if line.startswith('['):
                            json_line = line
                            break
                    
                    if json_line:
                        channels = json.loads(json_line)
                        st.session_state.found_channels = channels
                        st.session_state.api_key = api_key
                        st.session_state.step = "channels"
                        st.rerun()
                    else:
                        st.error("Could not parse channels. Raw output:")
                        st.code(output)
                else:
                    st.error(f"Error: {result.stderr}")
                    st.code(result.stdout + "\n" + result.stderr)
            except subprocess.TimeoutExpired:
                st.error("Timed out. Please try again.")
            except Exception as e:
                st.error(f"Error: {str(e)}")

# ============ STEP 2: SHOW CHANNELS & SYNC ============
elif st.session_state.step == "channels":
    channels = st.session_state.found_channels
    
    if channels:
        st.success(f"✅ Found {len(channels)} channels/groups!")
        
        st.subheader("📋 Your Channels")
        for ch in channels:
            st.write(f"• **{ch['title']}** ({ch['type']}) - ID: `{ch['id']}`")
        
        st.divider()
        
        if st.button("🚀 Sync to Dashboard", type="primary"):
            with st.spinner(f"Syncing {len(channels)} channels..."):
                try:
                    res = requests.post(
                        f"{SERVER_URL}/api/user/sync-channels?key={st.session_state.api_key}",
                        json={"channels": channels},
                        headers={
                            "Content-Type": "application/json",
                            "ngrok-skip-browser-warning": "true"
                        },
                        timeout=15
                    )
                    if res.status_code == 200:
                        st.success(f"✅ {len(channels)} channels synced!")
                        st.info("🎉 Go to Dashboard → Telegram → Add Channel → Load My Channels")
                        st.balloons()
                    else:
                        st.error(f"Sync failed: {res.json().get('error', 'Unknown')}")
                except Exception as e:
                    st.error(f"Connection error: {str(e)}")
        
        if st.button("🔄 Start Over"):
            st.session_state.step = "credentials"
            st.session_state.found_channels = []
            st.rerun()
    else:
        st.warning("No channels found.")
        if st.button("🔄 Try Again"):
            st.session_state.step = "credentials"
            st.rerun()
