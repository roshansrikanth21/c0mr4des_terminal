import os
from dotenv import load_dotenv
from backend.broker.angel_one_broker import AngelOneBroker

def test_connection():
    load_dotenv()
    print("Initializing Angel One Broker...")
    broker = AngelOneBroker()
    
    print(f"Client ID: {broker.client_id}")
    print(f"API Key: {broker.api_key}")
    print(f"TOTP Key: {broker.totp_key}")
    print(f"Password set: {'Yes' if broker.password and 'REPLACE' not in broker.password else 'No'}")
    
    print("\nAttempting to connect...")
    success = broker.connect()
    
    if success:
        print("Success! Connected to Angel One.")
        print("Fetching a quote for NIFTY-EQ...")
        price = broker.get_quote("NIFTY 50")
        print(f"LTP: {price}")
    else:
        print("Connection Failed. Check credentials and session status.")

if __name__ == "__main__":
    test_connection()
