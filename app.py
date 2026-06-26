import streamlit as st
import requests
import asyncio
import sys

st.set_page_config(page_title="CopyNova AI - Channel Finder", page_icon="🔍")

st.title("🔍 CopyNova AI - Channel Finder")
st.caption("Find your Telegram channels and sync them to your dashboard")

# Hardcoded server URL - users don't need to enter this
SERVER_URL = "https://consoling-botch-sulphuric.ngrok-free.dev"

# Step 1: CopyNova API Key
st.subheader("Step 1: CopyNova API Key")
api_key = st.text_input("Enter your CopyNova API Key", type="password", 
    help="Get this from your CopyNova dashboard → API Keys")
st.caption("Get your API key from Dashboard → API Keys")

# Step 2: Telegram Credentials
st.subheader("Step 2: Telegram API Credentials")
st.caption("Get these from [my.telegram.org](https://my.telegram.org)")
api_id = st.text_input("API ID")
api_hash = st.text_input("API Hash", type="password")
phone = st.text_input("Phone Number (+91...)")

if st.button("🔍 Find My Channels & Sync", type="primary", disabled=not (api_key and api_id and api_hash and phone)):
    try:
        from telethon import TelegramClient
        from telethon.tl.functions.messages import GetDialogsRequest
        from telethon.tl.types import InputPeerEmpty
    except ImportError:
        import subprocess
        subprocess.check_call([sys.executable, "-m", "pip", "install", "telethon"])
        from telethon import TelegramClient
        from telethon.tl.functions.messages import GetDialogsRequest
        from telethon.tl.types import InputPeerEmpty

    async def find_channels():
        client = TelegramClient('session', int(api_id), api_hash)
        await client.start(phone)
        
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

    with st.spinner("Connecting to Telegram..."):
        channels = asyncio.run(find_channels())
    
    if channels:
        st.success(f"Found {len(channels)} channels!")
        
        # Auto-sync to server
        with st.spinner(f"Syncing {len(channels)} channels to your dashboard..."):
            try:
                res = requests.post(
                    f"{SERVER_URL}/api/user/sync-channels?key={api_key}",
                    json={"channels": channels},
                    headers={"Content-Type": "application/json", "ngrok-skip-browser-warning": "true"}
                )
                if res.status_code == 200:
                    st.success(f"✅ {len(channels)} channels synced successfully!")
                    st.info("🎉 Go to your dashboard → Telegram → Add Channel and click 'Load My Channels'")
                    st.balloons()
                    
                    # Show channels
                    st.subheader("📋 Synced Channels")
                    for ch in channels:
                        st.write(f"• **{ch['title']}** ({ch['type']})")
                else:
                    error = res.json().get('error', 'Unknown error')
                    st.error(f"Sync failed: {error}")
            except Exception as e:
                st.error(f"Connection error: {e}")
    else:
        st.warning("No channels found. Make sure you're a member of some channels/groups.")