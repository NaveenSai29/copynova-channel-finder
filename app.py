import streamlit as st
import requests
import sys

st.set_page_config(page_title="CopyNova AI - Channel Finder", page_icon="🔍")

st.title("🔍 CopyNova AI - Channel Finder")
st.caption("Find your Telegram channels and sync them to your dashboard")

SERVER_URL = "https://consoling-botch-sulphuric.ngrok-free.dev"

# Initialize session state
if "step" not in st.session_state:
    st.session_state.step = "credentials"
if "phone_code_hash" not in st.session_state:
    st.session_state.phone_code_hash = None
if "found_channels" not in st.session_state:
    st.session_state.found_channels = []
if "api_id" not in st.session_state:
    st.session_state.api_id = ""
if "api_hash" not in st.session_state:
    st.session_state.api_hash = ""
if "phone" not in st.session_state:
    st.session_state.phone = ""
if "api_key" not in st.session_state:
    st.session_state.api_key = ""

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
            from telethon import TelegramClient
            
            # Create new event loop for this operation
            import asyncio
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            
            async def send():
                client = TelegramClient('session', int(api_id), api_hash)
                await client.connect()
                result = await client.send_code_request(phone)
                return result.phone_code_hash
            
            with st.spinner("Sending verification code..."):
                phone_code_hash = loop.run_until_complete(send())
            
            st.session_state.phone_code_hash = phone_code_hash
            st.session_state.api_id = api_id
            st.session_state.api_hash = api_hash
            st.session_state.phone = phone
            st.session_state.api_key = api_key
            st.session_state.step = "verify"
            st.rerun()
        except Exception as e:
            st.error(f"Failed: {str(e)}")

# ============ STEP 2: VERIFY OTP ============
elif st.session_state.step == "verify":
    st.subheader("📱 Verify Your Phone Number")
    st.caption(f"Code sent to {st.session_state.phone}. Check Telegram app.")
    
    code = st.text_input("Enter Verification Code", placeholder="12345")
    
    col1, col2 = st.columns(2)
    with col1:
        if st.button("✅ Verify & Find Channels", type="primary", disabled=not code):
            try:
                from telethon import TelegramClient
                from telethon.tl.functions.messages import GetDialogsRequest
                from telethon.tl.types import InputPeerEmpty
                import asyncio
                
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                
                async def verify():
                    client = TelegramClient('session', int(st.session_state.api_id), st.session_state.api_hash)
                    await client.connect()
                    await client.sign_in(
                        phone=st.session_state.phone,
                        code=code,
                        phone_code_hash=st.session_state.phone_code_hash
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
                    return channels
                
                with st.spinner("Verifying and fetching channels..."):
                    channels = loop.run_until_complete(verify())
                
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
