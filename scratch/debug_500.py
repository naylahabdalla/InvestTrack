from app import app
import sys

with app.test_client() as client:
    try:
        response = client.get('/')
        print(f"Status: {response.status_code}")
        if response.status_code == 500:
            # Flask debug mode usually prints the error to stdout/stderr
            print("Received 500 error. Check console for traceback.")
        else:
            print("Successfully reached home page.")
    except Exception as e:
        print(f"Caught exception: {e}")
        import traceback
        traceback.print_exc()
