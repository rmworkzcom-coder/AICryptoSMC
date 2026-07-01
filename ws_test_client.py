import asyncio
import websockets
import json
import time

async def run():
    uri = "ws://127.0.0.1:8005/api/ws"
    print("Connecting to", uri)
    try:
        async with websockets.connect(uri, ping_interval=None) as ws:
            print("Connected; waiting for initial message (5s timeout)")
            try:
                msg = await asyncio.wait_for(ws.recv(), timeout=5)
                print("Received initial:", msg)
            except Exception as e:
                print("No initial message or recv error:", repr(e))

            # Stay connected for a short period to observe server behavior
            start = time.time()
            while time.time() - start < 30:
                try:
                    msg = await asyncio.wait_for(ws.recv(), timeout=10)
                    print("Recv:", msg)
                except asyncio.TimeoutError:
                    print("No message within 10s; sending keepalive text")
                    try:
                        await ws.send("client-keepalive")
                    except Exception as e:
                        print("Send failed:", repr(e))
                        break
                except Exception as e:
                    print("Recv failed:", repr(e))
                    break

            print("Closing client")
    except Exception as e:
        print("Connection failed:", repr(e))

if __name__ == '__main__':
    asyncio.run(run())
