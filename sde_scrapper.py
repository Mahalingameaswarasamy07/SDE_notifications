import requests
from bs4 import BeautifulSoup
import schedule
import time
import json
import os
from datetime import datetime
import logging
from telegram import Bot
import pandas as pd
from dotenv import load_dotenv
import threading
import streamlit as st

# Load environment variables from .env file
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.FileHandler("scraper.log"), logging.StreamHandler()]
)
logger = logging.getLogger(__name__)

# Constants
URL = "https://b-u.ac.in/notifications/"
DATA_FILE = "previous_data.json"
ENV_FILE = ".env"

def create_default_env():
    """Create default .env file if it doesn't exist."""
    if not os.path.exists(ENV_FILE):
        current_time = datetime.now().strftime("%H:%M")
        with open(ENV_FILE, 'w') as f:
            f.write(f"TELEGRAM_TOKEN=7933065437:AAEXHryKASz_2zBkqLXmbjzvCZDdOwTT7UI\n")
            f.write(f"TELEGRAM_CHAT_ID=1357121467\n")
            f.write(f"NOTIFICATION_TIME={current_time}\n")
        logger.info(f"Created default .env file. Please update {ENV_FILE} with your credentials.")

def get_env_config():
    """Get configuration from environment variables."""
    # Reload environment variables to ensure we have the latest values
    load_dotenv(override=True)
    
    config = {
        "telegram_token": os.getenv("TELEGRAM_TOKEN", ""),
        "telegram_chat_id": os.getenv("TELEGRAM_CHAT_ID", ""),
        "notification_time": os.getenv("NOTIFICATION_TIME", datetime.now().strftime("%H:%M"))
    }
    
    return config

def load_previous_data():
    """Load previously scraped data from file with enhanced cloud compatibility."""
    try:
        # For Streamlit Cloud, use a known accessible directory
        if os.environ.get('STREAMLIT_SHARING_MODE') == 'streamlit':
            # Use Streamlit's cache directory for persistence
            file_path = os.path.join('/tmp', DATA_FILE)
        else:
            file_path = DATA_FILE
            
        if os.path.exists(file_path):
            with open(file_path, 'r') as f:
                return json.load(f)
        
        return {"news": []}
    except Exception as e:
        logger.error(f"Error loading previous data: {str(e)}")
        return {"news": []}

def save_data(data):
    """Save scraped data to file with cloud environment handling."""
    try:
        # Use the same path resolution logic as in load_previous_data
        if os.environ.get('STREAMLIT_SHARING_MODE') == 'streamlit':
            file_path = os.path.join('/tmp', DATA_FILE)
        else:
            file_path = DATA_FILE
            
        with open(file_path, 'w') as f:
            json.dump(data, f, indent=4)
        logger.info(f"Data saved successfully to {file_path}")
    except Exception as e:
        logger.error(f"Error saving data: {str(e)}")

def scrape_website():
    """Scrape news titles from the SDE BU website."""
    logger.info("Starting scraping process...")
   
    try:
        response = requests.get(URL, timeout=30)
        response.raise_for_status()
       
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Extract news items
        news_items = []
        news_section = soup.find('div', class_='admissions_contents')
        
        if news_section:
            # Find all title containers
            title_elements = news_section.find_all('div', class_='views-field views-field-title')
            
            for title_element in title_elements:
                # Extract the text from the span that contains the link
                span_content = title_element.find('span', class_='field-content')
                if span_content and span_content.find('a'):
                    title = span_content.find('a').text.strip()
                    news_items.append({"title": title})
       
        return {"news": news_items}
   
    except Exception as e:
        logger.error(f"Error scraping website: {str(e)}")
        return {"news": []}

def find_new_items(current_data, previous_data):
    """Find new items by comparing current and previous data."""
    new_news = [item for item in current_data["news"] 
                if item not in previous_data["news"]]
    
    return {"news": new_news}

import asyncio
from telegram.ext import ApplicationBuilder

async def send_telegram_message_async(message, config):
    """Send message via Telegram bot asynchronously."""
    if not config["telegram_token"] or not config["telegram_chat_id"]:
        logger.warning("Telegram credentials not configured. Update .env with your credentials.")
        return False
    
    try:
        application = ApplicationBuilder().token(config["telegram_token"]).build()
        await application.bot.send_message(
            chat_id=config["telegram_chat_id"],
            text=message,
            parse_mode='Markdown'
        )
        logger.info("Telegram message sent successfully")
        return True
    except Exception as e:
        logger.error(f"Error sending Telegram message: {str(e)}")
        return False

def send_telegram_message(message, config):
    """Wrapper function to call the async function from synchronous code."""
    return asyncio.run(send_telegram_message_async(message, config))

def format_message(new_items, previous_data):
    """Format the notification message with both new and existing news."""
    current_date = datetime.now().strftime('%d-%m-%Y')
    
    # Start with header
    message = f"*📢 SDE BU Notifications Update - {current_date}*\n\n"
    
    # Add new news section if there are new items
    if new_items["news"]:
        message += "🔔 *NEW NOTIFICATIONS:*\n"
        message += "━━━━━━━━━━━━━━━━━━━━━━\n"
        for i, item in enumerate(new_items["news"], 1):
            message += f"*{i}.* {item['title']}"
            if item.get('url'):
                message += f" - [Link]({item['url']})"
            message += "\n"
        message += "\n"
    
    # Add existing news section
    message += "📋 *EXISTING NOTIFICATIONS:*\n"
    message += "━━━━━━━━━━━━━━━━━━━━━━\n"
    
    if previous_data["news"]:
        for i, item in enumerate(previous_data["news"], 1):
            message += f"{i}. {item['title']}"
            if item.get('url'):
                message += f" - [Link]({item['url']})"
            message += "\n"
    else:
        message += "No existing notifications.\n"
    
    # Add footer
    message += "\n"
    message += "━━━━━━━━━━━━━━━━━━━━━━\n"
    message += "_Note: This is an automated notification from the SDE BU Scraper Service_"
    
    return message

def check_and_notify():
    """Main function to check for updates and send notifications."""
    logger.info("Running scheduled check for updates")
    
    config = get_env_config()
    previous_data = load_previous_data()
    current_data = scrape_website()
    
    if not current_data["news"]:
        logger.warning("No data scraped. Check website structure or network connection.")
        return
    
    new_items = find_new_items(current_data, previous_data)
    
    # Only send notification if there are new items or it's time for daily update
    # if new_items["news"]:
    message = format_message(new_items, previous_data)
    success = send_telegram_message(message, config)
    
    if success:
        save_data(current_data)  # Only save if notification was successful
        logger.info(f"Found and notified about {len(new_items['news'])} new news items")
    else:
        logger.warning("Failed to send notification, will try again next time")

def update_env_variable(key, value):
    """Update a single environment variable in the .env file."""
    if not os.path.exists(ENV_FILE):
        create_default_env()
    
    # Read current .env content
    with open(ENV_FILE, 'r') as f:
        lines = f.readlines()
    
    # Check if key exists and update it
    key_exists = False
    for i, line in enumerate(lines):
        if line.strip().startswith(f"{key}="):
            lines[i] = f"{key}={value}\n"
            key_exists = True
            break
    
    # Add key if it doesn't exist
    if not key_exists:
        lines.append(f"{key}={value}\n")
    
    # Write updated content back to .env
    with open(ENV_FILE, 'w') as f:
        f.writelines(lines)
    
    # Reload environment variables
    load_dotenv(override=True)

# Global variable to track if scheduler is running
scheduler_running = False
scheduler_thread = None

def run_scheduler():
    """Function to run in the scheduler thread."""
    global scheduler_running
    
    config = get_env_config()
    notification_time = config["notification_time"]
    
    logger.info(f"Scheduler thread started, checking for tasks at {notification_time}")
    
    schedule.clear()  # Clear any existing scheduled tasks
    schedule.every().day.at(notification_time).do(check_and_notify)
    
    # Immediately run a check
    # check_and_notify()
    
    while scheduler_running:
        schedule.run_pending()
        time.sleep(10)  # Check every 10 seconds
    
    logger.info("Scheduler thread stopped")

def start_scheduler():
    """Start the scheduler in a separate thread."""
    global scheduler_running, scheduler_thread
    
    if not scheduler_running:
        scheduler_running = True
        scheduler_thread = threading.Thread(target=run_scheduler)
        scheduler_thread.daemon = True  # Important for Streamlit
        scheduler_thread.start()
        logger.info("Scheduler started in background thread")
        return True
    
    return False

def stop_scheduler():
    """Stop the scheduler thread."""
    global scheduler_running
    
    if scheduler_running:
        scheduler_running = False
        logger.info("Scheduler stop requested")
        return True
    
    return False

# Initialize session state variables
def init_session_state():
    if 'scheduler_status' not in st.session_state:
        st.session_state.scheduler_status = False

# Main Streamlit app function
def main():
    st.title("SDE BU News Scraper")
    
    # Initialize session state
    init_session_state()
    
    # Load configuration
    config = get_env_config()
    
    # Configuration section
    st.header("Configuration")
    
    col1, col2 = st.columns(2)
    
    with col1:
        telegram_token = st.text_input("Telegram Bot Token", value=config["telegram_token"], type="password")
    
    with col2:
        telegram_chat_id = st.text_input("Telegram Chat ID", value=config["telegram_chat_id"])
    
    notification_time = st.time_input("Daily Notification Time", value=datetime.strptime(config["notification_time"], "%H:%M").time())
    
    # Save configuration
    if st.button("Save Configuration"):
        update_env_variable("TELEGRAM_TOKEN", telegram_token)
        update_env_variable("TELEGRAM_CHAT_ID", telegram_chat_id)
        update_env_variable("NOTIFICATION_TIME", notification_time.strftime("%H:%M"))
        
        st.success("Configuration saved successfully!")
    
    # Manual run button
    if st.button("Run Scraper Now"):
        with st.spinner("Scraping website..."):
            check_and_notify()
        st.success("Scraping completed!")
    
    # Scheduler controls
    st.header("Scheduler Control")
    
    col3, col4 = st.columns(2)
    
    with col3:
        if st.button("Start Scheduler"):
            if start_scheduler():
                st.session_state.scheduler_status = True
                st.success("Scheduler started successfully!")
            else:
                st.warning("Scheduler is already running")
    
    with col4:
        if st.button("Stop Scheduler"):
            if stop_scheduler():
                st.session_state.scheduler_status = False
                st.success("Scheduler stopped successfully!")
            else:
                st.warning("Scheduler is not running")
    
    # Display scheduler status
    status_color = "green" if st.session_state.scheduler_status else "red"
    status_text = "Running" if st.session_state.scheduler_status else "Stopped"
    st.markdown(f"<h4>Scheduler Status: <span style='color:{status_color};'>{status_text}</span></h4>", unsafe_allow_html=True)
    
    # Display previous data
    st.header("Previous Data")
    previous_data = load_previous_data()
    
    st.subheader("News")
    if previous_data["news"]:
        news_df = pd.DataFrame(previous_data["news"])
        st.dataframe(news_df)
    else:
        st.info("No news data available")

# Start the scheduler automatically when the app loads
if __name__ == "__main__":
    main()
    # Auto-start the scheduler when the app loads
    if not st.session_state.get('scheduler_status', False):
        start_scheduler()
        st.session_state.scheduler_status = True
