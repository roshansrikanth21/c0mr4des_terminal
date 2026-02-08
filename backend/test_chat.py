import requests

def test_chat():
    url = "http://localhost:8000/api/chat_analysis"
    
    # Test 1: Text Only
    print("\n--- Testing Text Only Chat ---")
    try:
        data = {
            "context": "The chart shows a Bullish Flag pattern on RELIANCE 15m.",
            "question": "What is the target for this pattern?"
        }
        res = requests.post(url, data=data) # sending as form data
        print(f"Status: {res.status_code}")
        print(f"Response: {res.text}")
    except Exception as e:
        print(f"Test 1 Failed: {e}")

    # Test 2: With Image (Mock)
    print("\n--- Testing Chat with Image ---")
    try:
        # Create a dummy image
        from PIL import Image
        import io
        img = Image.new('RGB', (100, 100), color = 'red')
        img_byte_arr = io.BytesIO()
        img.save(img_byte_arr, format='PNG')
        img_byte_arr.seek(0)
        
        files = {'file': ('test.png', img_byte_arr, 'image/png')}
        data = {
            "context": "This is a second chart for confirmation.",
            "question": "Does this look bearish?"
        }
        
        res = requests.post(url, data=data, files=files)
        print(f"Status: {res.status_code}")
        print(f"Response: {res.text}")
    except Exception as e:
        print(f"Test 2 Failed: {e}")

if __name__ == "__main__":
    test_chat()
