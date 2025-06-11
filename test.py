# test_client.py
import socket
import json
import time
import sys

HOST = "localhost"
PORT = 8270

arg = sys.argv[1]

msg = {
    "type": "GOSSIP_REPLY",
    "host": "192.168.0.28",
    "port": 8001,
    "peerId": f"{arg}",
    "files": [{"name": "file1.txt", "size": 123}, {"name": "file2.txt", "size": 456}]
}

# Option 1: send whole message at once
# data = json.dumps(msg).encode()

# Option 2: send message in chunks
data_str = json.dumps(msg)
chunk1 = data_str[:len(data_str)//2].encode()
chunk2 = data_str[len(data_str)//2:].encode()

with socket.create_connection((HOST, PORT)) as sock:
    # sock.sendall(data)
    sock.sendall(chunk1)
    time.sleep(1)  # simulate delay between chunks
    sock.sendall(chunk2)
