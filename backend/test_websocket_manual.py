"""
Manual WebSocket test script.
This demonstrates the WebSocket implementation works correctly.

To run this test:
1. Start the server: uvicorn main:app --reload
2. In another terminal: python test_websocket_manual.py
"""
import asyncio
import json
from datetime import datetime

try:
    import websockets
    WEBSOCKETS_AVAILABLE = True
except ImportError:
    print("websockets library not installed. Install with: pip install websockets")
    WEBSOCKETS_AVAILABLE = False
    exit(1)

from api.services.auth import create_access_token


async def test_websocket_connection():
    """Test basic WebSocket connection with authentication."""
    print("=" * 60)
    print("Testing WebSocket Connection")
    print("=" * 60)

    # Create a test token (you need to use a real user ID from your database)
    # For this test, we'll use user_id=1 (typically the superadmin)
    test_token = create_access_token({"sub": "1", "token_version": 0})
    print(f"\n1. Created test token: {test_token[:50]}...")

    # Connect to WebSocket
    ws_url = f"ws://localhost:8000/ws?token={test_token}"
    print(f"\n2. Connecting to: {ws_url}")

    try:
        async with websockets.connect(ws_url) as websocket:
            print("✓ Successfully connected to WebSocket")
            print(f"✓ Connection state: {websocket.state.name}")

            # Wait for a ping or message
            print("\n3. Waiting for messages (10 seconds)...")
            try:
                message = await asyncio.wait_for(websocket.recv(), timeout=10.0)
                data = json.loads(message)
                print(f"✓ Received message: {data}")
            except asyncio.TimeoutError:
                print("✓ No messages received (this is expected if no events are triggered)")

            print("\n✓ WebSocket connection test PASSED")

    except websockets.exceptions.InvalidStatusCode as e:
        print(f"✗ Connection rejected with status code: {e.status_code}")
        print(f"  This indicates authentication failed or endpoint is not available")
        return False
    except ConnectionRefusedError:
        print("✗ Connection refused - make sure the server is running")
        print("  Start server with: uvicorn main:app --reload")
        return False
    except Exception as e:
        print(f"✗ Error: {e}")
        return False

    return True


async def test_websocket_without_token():
    """Test that WebSocket rejects connections without token."""
    print("\n" + "=" * 60)
    print("Testing WebSocket Rejection (No Token)")
    print("=" * 60)

    ws_url = "ws://localhost:8000/ws"
    print(f"\n1. Connecting without token to: {ws_url}")

    try:
        async with websockets.connect(ws_url) as websocket:
            print("✗ Connection should have been rejected but wasn't")
            return False
    except websockets.exceptions.InvalidStatusCode as e:
        if e.status_code in [401, 403, 1008]:
            print(f"✓ Connection properly rejected with status: {e.status_code}")
            return True
        else:
            print(f"✗ Unexpected status code: {e.status_code}")
            return False
    except Exception as e:
        print(f"✗ Unexpected error: {e}")
        return False


async def test_websocket_invalid_token():
    """Test that WebSocket rejects connections with invalid token."""
    print("\n" + "=" * 60)
    print("Testing WebSocket Rejection (Invalid Token)")
    print("=" * 60)

    invalid_token = "invalid.jwt.token.here"
    ws_url = f"ws://localhost:8000/ws?token={invalid_token}"
    print(f"\n1. Connecting with invalid token to: {ws_url}")

    try:
        async with websockets.connect(ws_url) as websocket:
            print("✗ Connection should have been rejected but wasn't")
            return False
    except websockets.exceptions.InvalidStatusCode as e:
        if e.status_code in [401, 403, 1008]:
            print(f"✓ Connection properly rejected with status: {e.status_code}")
            return True
        else:
            print(f"✗ Unexpected status code: {e.status_code}")
            return False
    except Exception as e:
        print(f"✗ Unexpected error: {e}")
        return False


async def main():
    """Run all manual tests."""
    print("\n" + "=" * 60)
    print("WebSocket Implementation Manual Tests")
    print("=" * 60)
    print("\nNOTE: Server must be running on localhost:8000")
    print("Start with: uvicorn main:app --reload")
    print("=" * 60)

    results = []

    # Test 1: Valid connection
    results.append(await test_websocket_connection())

    # Test 2: No token rejection
    results.append(await test_websocket_without_token())

    # Test 3: Invalid token rejection
    results.append(await test_websocket_invalid_token())

    # Summary
    print("\n" + "=" * 60)
    print("Test Summary")
    print("=" * 60)
    passed = sum(results)
    total = len(results)
    print(f"Passed: {passed}/{total}")

    if passed == total:
        print("\n✓ All manual tests PASSED")
    else:
        print(f"\n✗ {total - passed} test(s) FAILED")

    return passed == total


if __name__ == "__main__":
    success = asyncio.run(main())
    exit(0 if success else 1)
