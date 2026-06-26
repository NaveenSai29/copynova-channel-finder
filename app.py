import streamlit as st
import requests
import asyncio
import sys

st.set_page_config(page_title="CopyNova AI - Channel Finder", page_icon="🔍")

st.title("🔍 CopyNova AI - Channel Finder")
st.caption("Find your Telegram channels and sync them to your dashboard")

# Hardcoded server URL
SERVER_URL = "https://consoling-botch-sulphuric.ngrok-free.dev"

# Initialize session state
if "step" not in st.session_state:
    st.session_state.step = "credentials"  # credentials, verify, channels
if "phone_code_hash" not in st.session_state:
    st.session_state.phone_code_hash = None
if "client" not in st.session_state:
    st.session_state.client = None
if "found_channels" not in st.session_state:
    st.session_state.found_channels = []
if "api_key" not in st.session_state:
    st.session_state.api_key = ""
if "phone" not in st.session_state:
    st.session_state.phone = ""

# Import telethon once
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

async def send_code(api_id, api_hash, phone):
    """Send verification code to phone"""
    client = TelegramClient('streamlit_session', int(api_id), api_hash)
    await client.connect()
    result = await client.send_code_request(phone)
    return client, result.phone_code_hash

async def verify_and_fetch(client, phone, code, phone_code_hash):
    """Verify code and fetch channels"""
    await client.sign_in(phone=phone, code=code, phone_code_hash=phone_code_hash)
    
    dialogs = await client(GetDialogsRequest(
        offset_date=None, offset_id=0, offset_peer=InputPeerEmpty(),
        limit=200, hash=0
    ))
    
    all_channels = []
    for dialog in dialogs.dialogs:
        try:
            entity = await client.get_entity(dialog.peer)
            if hasattr(entity, 'broadcast') and entity.broadcast:
                all_channels.append({'id': str(entity.id), 'title': entity.title, 'type': 'channel'})
            elif hasattr(entity, 'megagroup') and entity.megagroup:
                all_channels.append({'id': str(entity.id), 'title': entity.title, 'type': 'group'})
        except:
            pass
    
    await client.disconnect()
    return all_channels

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
    
    if st.button("📱 Send Verification Code", type="primary", disabled=not (api_key and api_id and api_hash and phone)):
        try:
            with st.spinner("Sending verification code to Telegram..."):
                client, phone_code_hash = asyncio.run(send_code(api_id, api_hash, phone))
                st.session_state.client = client
                st.session_state.phone_code_hash = phone_code_hash
                st.session_state.api_key = api_key
                st.session_state.phone = phone
                st.session_state.step = "verify"
                st.rerun()
        except Exception as e:
            st.error(f"Failed to send code: {str(e)}")

# ============ STEP 2: VERIFY OTP ============
elif st.session_state.step == "verify":
    st.subheader("📱 Verify Your Phone Number")
    st.caption(f"A verification code was sent to {st.session_state.phone}")
    st.caption("Check your Telegram app for the code")
    
    code = st.text_input("Enter Verification Code", placeholder="12345", key="otp_input")
    
    col1, col2 = st.columns(2)
    with col1:
        if st.button("✅ Verify & Find Channels", type="primary", disabled=not code):
            try:
                with st.spinner("Verifying and fetching channels..."):
                    channels = asyncio.run(verify_and_fetch(
                        st.session_state.client,
                        st.session_state.phone,
                        code,
                        st.session_state.phone_code_hash
                    ))
                    st.session_state.found_channels = channels
                    st.session_state.step = "channels"
                    st.rerun()
            except Exception as e:
                st.error(f"Verification failed: {str(e)}")
    
    with col2:
        if st.button("↩️ Back"):
            st.session_state.step = "credentials"
            st.rerun()

# ============ STEP 3: SHOW CHANNELS & SYNC ============
elif st.session_state.step == "channels":
    channels = st.session_state.found_channels
    
    if channels:
        st.success(f"✅ Found {len(channels)} channels/groups!")
        
        st.subheader("📋 Your Channels")
        for ch in channels:
            st.write(f"• **{ch['title']}** ({ch['type']}) - ID: `{ch['id']}`")
        
        st.divider()
        
        if st.button("🚀 Sync to Dashboard", type="primary"):
            with st.spinner(f"Syncing {len(channels)} channels to your dashboard..."):
                try:
                    res = requests.post(
                        f"{SERVER_URL}/api/user/sync-channels?key={st.session_state.api_key}",
                        json={"channels": channels},
                        headers={
                            "Content-Type": "application/json",
                            "ngrok-skip-browser-warning": "true"
                        },
                        timeout=10
                    )
                    if res.status_code == 200:
                        st.success(f"✅ {len(channels)} channels synced successfully!")
                        st.info("🎉 Go back to your dashboard → Telegram → Add Channel and click **Load My Channels**")
                        st.balloons()
                    else:
                        error = res.json().get('error', 'Unknown error')
                        st.error(f"Sync failed: {error}")
                except Exception as e:
                    st.error(f"Connection error: {str(e)}")
        
        if st.button("🔄 Start Over"):
            st.session_state.step = "credentials"
            st.session_state.found_channels = []
            st.rerun()
    else:
        st.warning("No channels found. Make sure you're a member of some channels/groups.")
        if st.button("🔄 Try Again"):
            st.session_state.step = "credentials"
            st.rerun()
