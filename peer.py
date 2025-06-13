import os
import sys
import json
import time
import uuid
import random
import socket
import hashlib
import datetime
import threading

#---# WELL KNOWN HOST INFORMATION #---#
# You may adjust these values to      #
# match a well-known-host of your own #
KNOWN_HOST = "localhost"
KNOWN_PORT = "8270"
#-------------------------------------#

#---# Program Defaults #---#
DEFAULT_HOST = "localhost"
DEFAULT_P2P_PORT = 8270
DEFAULT_HTTP_PORT = 8080
DEFAULT_BASE_PATH = "./"
DEBUG_ENABLED = False
#--------------------------#

#---# Program Constants #---#
METADATA_FILE = "metadata.json"
FILE_UPLOAD_PATH = "FileUploads"
PEER_TIMEOUT = 60 #seconds # How long must a peer be inactive for before it is untracked
PEER_CLEANUP_INTERVAL = 10 #seconds # How long between checking for inactive peers
GOSSIP_INTERVAL = 30 #seconds -- How often peer gossips
GOSSIP_PEER_COUNT = 3 # how many peers do we attempt to gossip to
#---------------------------#

#---# Program Globals #---#
tracked_peers = {} # key: peerId, value: dict with host, port, last_seen
seen_gossip_ids = set() # uses a set to avoid repeats
server_ready = threading.Event()
#-------------------------#

def debug(*args):
    """
    Helper function to print [DEBUG] in front of the args. Only prints when DEBUG_ENABLED
    """
    if DEBUG_ENABLED:
        print("[DEBUG]", *args)
# end debug()

#-----------------------------#
#---# Metadata Management #---#
#                             #
# code related to managing    #
# the metadata of files       #
#-----------------------------#
def load_metadata():
    """
    Attempts to load metadata from METADATA_FILE into a dictionary and return the metadata as a dictionary
    If a metadata file does not exist, it creates it and returns an empty dictionary
    """
    try:
        with open(METADATA_FILE, "r") as f:
            metadata = json.load(f)
    except FileNotFoundError:
        debug(f"Metadata file does not exist. Creating file '{METADATA_FILE}'")
        metadata = {}
        with open(METADATA_FILE, "w") as f:
            json.dump(metadata, f, indent=2)
    return metadata
#end load_metadata()

def update_metadata(file_id, file_metadata):
    """
    Add or update a file entry in the metadata.
    Only updates if the file is new or has a newer timestamp
    """
    metadata = load_metadata()
    old = metadata.get(file_id)

    if old is None or file_metadata["file_timestamp"] > old["file_timestamp"]:
        metadata[file_id] = file_metadata
        save_metadata(metadata)
        return True # updated or added successfully
    return False # No update
# end update_metadata()

def save_metadata(data):
    """
    Saves the metadata to the file
    """
    try:
        with open(METADATA_FILE, "w") as f:
            json.dump(data, f, indent=2)
    except IOError as e:
        debug(f"Failed to write metadata to {METADATA_FILE}: {e}")
#end save_metadata()

# def addMetadata(filename, owner):
#     """
#     Adds relevant metadata (owner, timestamp, filesize) to filename and then saves the metadata 
#     """
#     try:
#         metadata = loadMetadata()
#         timestamp = datetime.now().strftime(TIMESTAMP_FORMAT)
#         metadata[filename] = {
#             "owner": owner,
#             "filesize": os.path.getsize(f"{SERVER_FILE_PATH}/{filename}"),
#             "timestamp": timestamp
#         }
#         saveMetadata(metadata)
#     except FileNotFoundError as e:
#         print(f"Error: {e}")

# def deleteMetadata(filename):
#     """
#     Removes metadata for filename from METADATA_FILE
#     """
#     try:
#         metadata = loadMetadata()
#         if filename in metadata:
#             metadata.pop(filename)
#             saveMetadata(metadata)
#     except FileNotFoundError as e:
#         print(f"Error: {e}")
# # end of Functions for Managing the file Metadata
#-----------------------------#
# end of Metadata Management  #
#-----------------------------#



#-------------------------#
#---# Message Sending #---#
#                         #
# code related to sending #
# messages that will be   #
# over the p2p server     #
#-------------------------#
def hash_sha256(data, time):
    """
    Hashes data using sha256 and the time timestamp
    """
    hashBase = hashlib.sha256()
    hashBase.update(data)
    hashBase.update(str(time).encode())
    hash = hashBase.hexdigest()
    return hash
# end hash_sha256

def send_message(msg, to_host, to_port):
    """
    Sends a message to the port and host
    """
    try:
        with socket.create_connection((to_host, to_port), timeout=5) as sock:
            sock.sendall(json.dumps(msg).encode())
            return True
    except Exception as e:
        print(f"Failed to send message to {to_host}:{to_port}: {e}")
        return False
# end send_message()

def push_file(file_path, my_peer_id):
    """
    Pushes a file locally to this peer, and forwards the file to up to 1 other peer.
    Then announces the new file to all tracked peers.
    """
    if not os.path.isfile(file_path):
        print(f"File '{file_path}' not found.")
        return
    
    print(f"Pushing file '{file_path}'...")

    # load up the file
    with open(file_path, "rb") as f:
        file_contents = f.read()

    timestamp = int(time.time())

    file_id = hash_sha256(file_contents, timestamp) # create a file_id

    file_metadata = {
        "file_name": os.path.basename(file_path),
        "file_size": len(file_contents),
        "file_id": file_id,
        "file_owner": my_peer_id,
        "file_timestamp": timestamp
    }

    # save the file locally
    path = os.path.join(FILE_UPLOAD_PATH, file_id)
    with open(path, "wb") as f:
        f.write(file_contents)

    print(f"File saved locally as: {file_id}")

    update_metadata(file_id, file_metadata) # add/update metadata on a file

    if tracked_peers: # if we have a tracked peer, send to 1 of them
        to_peer = random.choice(list(tracked_peers.items()))
        to_host = to_peer[1]["host"]
        to_port = to_peer[1]["port"]
        send_file(file_contents, file_metadata, to_host, to_port, to_peer)

    # ANNOUNCE to all peers
    for peer_id, peer_info in list(tracked_peers.items()):
        msg_send_announce(my_peer_id, file_metadata, peer_info["host"], peer_info["port"], peer_id)

    print(f"File '{file_metadata["file_name"]}' pushed to the network with ID: {file_id}")
# end push_file()

def send_file(content, file_metadata, to_host, to_port, to_peer):
    """
    Sends a file from this peer to a peer
    """
    msg = msg_build_file_data(content, file_metadata)
    sent = send_message(msg, to_host, to_port)
    if sent:
        print(f"File '{file_metadata["file_name"]}' pushed to peer {to_peer} ({to_host}:{to_port})")

def msg_send_announce(my_peer_id, file_metadata, to_host, to_port, to_peer):
    """
    Sends an announce message with info on a file to the to_host at to_port
    """
    msg = msg_build_announce(my_peer_id, file_metadata)

    try:
        with socket.create_connection((to_host, to_port), timeout=5) as sock:
            sock.sendall(json.dumps(msg).encode())
            print(f"Announced file to peer {to_peer} at {to_host}:{to_port}")
    except Exception as e:
        print(f"Failed to announce to peer {to_peer} at {to_host}:{to_port}: {e}")
# end msg_send_announce

def first_gossip(my_host, my_port, my_peer_id):
    """
    Send a first gossip message to a known host to let them know this peer exists
    """
    msg_send_gossip(my_host, my_port, my_peer_id, KNOWN_HOST, KNOWN_PORT)
    print(f"Sent initial gossip to well-known-host at {KNOWN_HOST}:{KNOWN_PORT}")
# end first_gossip()

def n_peer_gossip(n, my_host, my_port, my_peer_id, msg_override=None):
    """
    Send a message to n tracked peers. If n < len(tracked_peers), the peers are randomly selected.

    Parameters:
        n (int): the number of peers to send gossip message to.
        my_host: the host of sender
        my_port: the port of sender
        my_peer_id: the peer id of sender
        msg_override: the msg to send. If None, create new gossip message
    """
    known_peers = list(tracked_peers.items())
    random.shuffle(known_peers)

    for peer_id, peer_info in known_peers[:n]:
        if peer_id == my_peer_id:
            continue # skip this peer
        msg_send_gossip(my_host, my_port, my_peer_id, peer_info["host"], peer_info["port"], msg_override)
# end n_peer_gossip()

def msg_send_gossip(my_host, my_port, my_peer_id, to_host, to_port, msg_override=None):
    """
    Sends a gossip message.

    Parameters:
        my_host : the host of sender
        my_port : the port of sender
        my_peer_id : the peer id of the sender

        to_host : the host of receiver
        to_port : the port of receiver

        msg_override: the msg to send. If None, create new gossip message
    """
    remove_old_peers() # make sure we only send to active peers

    if msg_override is None:
        gossip_message = msg_build_gossip(my_host, my_port, my_peer_id)
    else:
        gossip_message = msg_override

    seen_gossip_ids.add(gossip_message["id"])

    try:
        with socket.create_connection((to_host, to_port), timeout=5) as sock:
            sock.sendall(json.dumps(gossip_message).encode())
    except Exception as e:
        debug(f"Failed to send gossip to {to_host}:{to_port}: {e}")
        remove_peer(to_host, to_port)


# end msg_send_gossip

def interval_send_gossip(my_host, my_port, my_peer_id):
    """
    Send gossip from host, port, peer_id periodically, to all this peers known peers.
    Runs on a thread to happen while other things run
    """
    while True:
        n_peer_gossip(len(tracked_peers), my_host, my_port, my_peer_id)
        if(len(tracked_peers) > 0):
            print(f"Sent gossip message to {len(tracked_peers)} peers")
        time.sleep(GOSSIP_INTERVAL)
# end interval_send_gossip

def msg_send_gossip_reply(my_host, my_port, my_peer_id, to_host, to_port):
    """
    Sends a gossip reply message.

    Parameters:
        my_host : the host of sender
        my_port : the port of sender
        my_peer_id : the peer id of the sender

        to_host : the host of receiver
        to_port : the port of receiver
    """
    reply_message = msg_build_gossip_reply(my_host, my_port, my_peer_id) # replace [] with a method to get local files from metadata
    try:
        with socket.create_connection((to_host, to_port), timeout=5) as sock:
            sock.sendall(json.dumps(reply_message).encode())
    except Exception as e:
        print(f"Failed to send gossip_reply to {to_host}:{to_port}: {e}")
# end msg_send_gossip_reply()
#-------------------------#
# end of Message Sending  #
#-------------------------#



#--------------------------#
#---# Message Building #---#
#                          #
# code related to building #
# messages that will be    #
# sent over the p2p server #
#--------------------------#
def msg_build_gossip(host, port, peer_id):
    """Build a message for GOSSIP format"""
    return {
        "type": "GOSSIP",
        "host": host,
        "port": port,
        "id": str(uuid.uuid4()),
        "peerId": peer_id 
    }
# end msg_build_gossip()

def msg_build_gossip_reply(host, port, peer_id):
    """Build a message for GOSSIP_REPLY format"""

    # make sure we include the files known to us
    metadata = load_metadata()
    local_files = list(metadata.values())

    return {
        "type": "GOSSIP_REPLY",
        "host": host,
        "port": port,
        "peerId": peer_id,
        "files": local_files
    }
# end msg_build_gossip_reply()

def msg_build_announce(peer_id, file_metadata):
    """Build a message for ANNOUNCE format"""
    return {
        "type": "ANNOUNCE",
        "from": peer_id,
        **file_metadata
    }
# end msg_build_announce()

def msg_build_file_data(content, file_metadata):
    """Build a message for FILE_DATA format"""
    return {
        "type": "FILE_DATA",
        **file_metadata,
        "data": content.hex()
    }
# end msg_build_file_data()
#--------------------------#
# end of Message Building  #
#--------------------------#



#-----------------------#
#---# Peer Tracking #---#
#                       #
# code related to       #
# tracking peers        #
#-----------------------#
def update_tracked_peer(host, port, peer_id):
    """
    Update the tracked_peers dictionary with new info on a peer
    """
    tracked_peers[peer_id] = {
        "host": host,
        "port": port,
        "last_seen": time.time(),
    }
# end update_tracked_peer()

def peer_cleanup():
    """
    Periodically checks our tracked peers to see if any are inactive. Interval set by PEER_CLEANUP_INTERVAL
    """
    while True:
        remove_old_peers()
        time.sleep(PEER_CLEANUP_INTERVAL)
# end peer_cleanup()

def remove_peer(host, port):
    """
    Remove a peer from tracked peers right away
    """
    for peer_id, peer_info in list(tracked_peers.items()):
        if peer_info["host"] == host and peer_info["port"] == port:
            print(f"Removing unreachable peer {peer_id} at {host}:{port}")
            del tracked_peers[peer_id]
            break
# end remove_peer()

def remove_old_peers(timeout=PEER_TIMEOUT):
    """
    Removes peers from tracked peers that have not been heard from in timeout seconds
    """
    now = time.time()
    for peer_id in list(tracked_peers.keys()):
        if now - tracked_peers[peer_id]["last_seen"] > timeout:
            debug(f"Removing old peer {peer_id}")
            del tracked_peers[peer_id]
# end remove_old_peers()
#-----------------------#
# end of Peer Tracking  #
#-----------------------#



#---------------------------------#
#---# Peer-to-Peer Management #---#
#                                 #
# code related to managing        #
# the p2p server                  #
#---------------------------------#
def receive_message(client_socket):
    """
    Receive in a valid-formatted JSON message from client_socket
    """
    buffer = b""
    decoder = json.JSONDecoder()
    while True:
        data = client_socket.recv(4096)
        if not data:
            if not buffer:
                # no data and an empty buffer means connection is closed
                return None
            else:
                # connection closed, but buffer still has data
                break
        buffer += data
        
        # Attempt to decode JSON from a buffer
        try:
            msg, _ = decoder.raw_decode(buffer.decode())
            return msg
        except json.JSONDecodeError:
            # keep reading
            continue

    # if connection has closed, but JSON is still invalid, throw an error
    raise ConnectionError("Invalid JSON received before connection was closed.")
# end receive_message()

def receive_msg_gossip(msg, my_peer_id, my_host, my_port):
    """
    Handles a GOSSIP message received by this peer.
    """
    the_host = msg["host"]
    the_port = msg["port"]
    gossip_id = msg["id"]
    the_peer_id = msg["peerId"]

    if gossip_id in seen_gossip_ids:
        return # we have seen the gossip so do no more
    
    seen_gossip_ids.add(gossip_id) # new gossip to us, so add and process
    update_tracked_peer(the_host, the_port, the_peer_id) # track the peer who gossiped to us

    msg_send_gossip_reply(my_host, my_port, my_peer_id, the_host, the_port)

    # Forward the message to some of my known peers
    n_peer_gossip(GOSSIP_PEER_COUNT, my_host, my_port, my_peer_id, msg)
# end receive_msg_gossip()

def receive_msg_gossip_reply(msg, my_peer_id, my_host, my_port):
    """
    Handles a GOSSIP_REPLY message received by this peer.
    """
    the_host = msg["host"]
    the_port = msg["port"]
    the_peer_id = msg["peerId"]
    the_local_files = msg["files"]

    update_tracked_peer(the_host, the_port, the_peer_id) # track the peer who gossiped a reply to us

    # update metadata of all the received files
    for file_metadata in the_local_files:
        file_id = file_metadata["file_id"]
        updated_file = update_metadata(file_id, file_metadata)
        if updated_file:
            print(f"Updated metadata for file '{file_id}'")
# end receive_msg_gossip_reply()

def receive_msg_announce(msg):
    """
    Handles an ANNOUNCE message by updating this peers known metadata
    """
    file_metadata = {
        "file_name": msg["file_name"],
        "file_size": msg["file_size"],
        "file_id": msg["file_id"],
        "file_owner": msg["file_owner"],
        "file_timestamp": msg["file_timestamp"]
    }
    peer_id = msg["from"]
    file_name = msg["file_name"]
    file_id = file_metadata["file_id"]
    print(f"Received file announcement from {peer_id}: {file_name} ({file_id})")

    updated_file = update_metadata(file_id, file_metadata)
    if updated_file:
        print(f"Metadata updated for announced file: '{file_name}'")
# end receive_msg_announce()

def receive_msg_file_data(msg):
    """
    Handles a FILE_DATA message by saving the file locally and updates metadata
    """
    file_name = msg["file_name"]
    file_size = msg["file_size"]
    file_id = msg["file_id"]
    file_owner = msg["file_owner"]
    file_timestamp = msg["file_timestamp"]
    data_hex = msg["data"]

    # decode hex back into bytes
    try:
        file_bytes = bytes.fromhex(data_hex)
    except ValueError:
        debug("Received FILE_DATA with invalid hex data.")
        return

    # save the file locally
    file_path = os.path.join(FILE_UPLOAD_PATH, file_id)
    print(f"Saving file '{file_name}' - this may take a while for large files...")
    try:
        with open(file_path, "wb") as f:
            f.write(file_bytes)
        print(f"Downloaded {file_size/1024:.2f} KB for file '{file_name}'")
    except IOError as e:
        print(f"Failed to save file '{file_name}': {e}")
        return
    
    # create the metadata from the message so we can update our metadata
    file_metadata = {
        "file_name": file_name,
        "file_size": file_size,
        "file_id": file_id,
        "file_owner": file_owner,
        "file_timestamp": file_timestamp
    }

    # update our metadata
    update_metadata(file_id, file_metadata)
# end receive_msg_file_data()

def handle_message(msg, my_peer_id, my_host, my_port):
    """
    Takes in a msg message and parses the info to pass it off to the correct message type handler
    """
    type = msg["type"]

    if type == "GOSSIP":
        debug("Handling GOSSIP")
        receive_msg_gossip(msg, my_peer_id, my_host, my_port)
    elif type == "GOSSIP_REPLY":
        debug("Handling GOSSIP_REPLY")
        receive_msg_gossip_reply(msg, my_peer_id, my_host, my_port)
    elif type == "ANNOUNCE":
        debug("Handling ANNOUNCE")
        receive_msg_announce(msg)
    elif type == "FILE_DATA":
        debug("Handling file_data")
        receive_msg_file_data(msg)
    else:
        print(f"Unhandled Message Type: {type}")
# end handle_message()

def handle_client(client_socket, addr, peer_id, host, port):
    """
    Handles receiving messages from a client and passing off responsibility to the correct handlers
    """
    debug(f"Accepted connection from {addr}")
    try:
        msg = receive_message(client_socket)
        if msg.get("peerId") == peer_id:
            debug(f"Received connection my myself. Ignoring.")
            return # ignore because it's my own message
        if msg:
            debug(f"Received from {addr}: {msg}")
            handle_message(msg, peer_id, host, port)
    except Exception as e:
        print(f"Exception while communicating with {addr}: {e}")
    finally:
        client_socket.close()
        debug(f"Connection closed from {addr}")
# end handle_client()

def p2p_help_commands():
    """
    Helper function to print the list of commands and how to use them
    """
    print(f"Use 'get <file_id> [destination]' to download files\n" + 
          "Use 'push <filepath>' to upload files\n" + 
          "Use 'list' to view available files\n" +
          "Use 'peers' to view connected peers\n" + 
          "User 'ls' to list the contents of your current directory\n" +
          "Use 'help' to view these commands again\n" +
          "Use 'exit' to quit"
          )
# end p2p_help_commands()

def p2p_server(peer_id, host, port, http_port):
    """
    Start the p2p server on the host and port with peer_id
    """
    server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_sock.bind((host, port))
    server_sock.listen()
    server_sock.settimeout(1) # seconds
    print(f"Peer {peer_id} running on {host}:{port}, HTTP on {http_port}")
    p2p_help_commands()
    server_ready.set() # Server is ready

    while True:
        try:
            client_socket, addr = server_sock.accept()
            threading.Thread(target=handle_client, args=(client_socket, addr, peer_id, host, port), daemon=True).start()
        except socket.timeout:
            continue # no connection, so we check again
        except Exception as e:
            print(f"Unexpected P2P Server error: {e}")
# end p2p_server
#---------------------------------#
# end of Peer-to-Peer Management  #
#---------------------------------#



#---------------------------------#
#---# Command Line Management #---#
#                                 #
# code related to managing        #
# the command line                #
#---------------------------------#
def command_list():
    """
    List file metadatas on this peer
    """
    metadata = load_metadata()
    local_files = list(metadata.values())
    for file in local_files:
        file_id = file["file_id"]
        file_name = file["file_name"]
        #TODO - track the peers that have the file
        print(f"{file_id}: {file_name} - Peers: *TODO*")
# end command_list()

def command_peers():
    """
    Print all currently tracked peers
    """
    for peer_id, peer_info in tracked_peers.items():
        host = peer_info["host"]
        port = peer_info["port"]
        last_seen = datetime.datetime.fromtimestamp(peer_info["last_seen"]).strftime("%a %b %d %H:%M:%S %Y")
        print(f"{peer_id} at {host}:{port} - Last seen: {last_seen}")
# end command_peers()

def command_ls(path=DEFAULT_BASE_PATH):
    """
    Print the file contents of the path with details
    """
    print(f"{'Name':30}\t{'Size (bytes)':12}\t{'Modified Time'}")
    print("-" * 70)
    for entry in os.scandir(path):
        info = entry.stat()
        name = entry.name
        size = info.st_size
        mtime = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(info.st_mtime))
        print(f"{name:30}\t{size:12}\t{mtime}")
# end command_ls()

def parse_cli_args():
    """
    Parses the command line interface arguments provided at runtime, and sets program values accordingly

    Expected arguments are:
        python peer.py <peer_id> [host] [p2p_port] [http_port] [base_path] --debug

        --debug is an optional flag to enable [DEBUG] print lines at runtime. Useful in testing.
    """
    global DEBUG_ENABLED

    args = sys.argv[1:]

    if "--debug" in args: # Check if the debug flag exists and set accordingly
        DEBUG_ENABLED = True
        args.remove("--debug")

    if not (1 <= len(args) <= 5): # Check if we received any flags
        print("Usage: python peer.py <peer_id> [host] [p2p_port] [http_port] [base_path]")
        sys.exit(1) # exit if it's wrong and guide user

    #---# Setup defaults #---#
    peer_id = args[0]
    host = args[1] if len(args) > 1 else DEFAULT_HOST
    try:
        p2p_port = int(args[2] if len(args) > 2 else DEFAULT_P2P_PORT)
        http_port = int(args[3] if len(args) > 3 else DEFAULT_HTTP_PORT)
    except ValueError:
        print("Ports must be integers.")
        print("Usage: python peer.py <peer_id> [host] [p2p_port] [http_port] [base_path]")
        sys.exit(1) # exit if it's wrong and guide user

    base_path = args[4] if len(args) > 4 else DEFAULT_BASE_PATH

    return peer_id, host, p2p_port, http_port, base_path
#end parse_cli_args()

def command_line(my_peer_id):
    """
    Repeatedly takes in inputs to process
    """
    while True:
        cmd_input = input("> ").strip()
        if not cmd_input:
            continue # ignore the empty inputs

        tokens = cmd_input.split(maxsplit=1)
        cmd = tokens[0]
        arg = tokens[1] if len(tokens) > 1 else None

        match cmd:
            case "help":
                # show commands to peer
                p2p_help_commands()

            case "ls":
                # list directory
                command_ls()

            case "list":
                # show file metadata
                command_list()

            case "peers":
                # show tracked peers
                command_peers()

            case "push":
                # handle push
                if arg:
                    push_file(arg, my_peer_id)
                    debug(f"handling push for {arg}")
                else:
                    print("Usage: push <Path>")
            case "get":
                # handle get
                if arg:
                    #TODO
                    #get_file(arg, my_peer_id)
                    debug(f"handling get for {arg}")
                else:
                    print("Usage: get <fileId>")

            case "delete":
                # handle delete
                if arg:
                    #TODO
                    #delete_file(arg)
                    debug(f"handling delete for {arg}")
                else:
                    print("Usage: delete <fileId>")

            case "exit":
                # exit program
                print(f"Exiting program...")
                break

            case _: # default, error protection
                debug("Bad command")
# end command_line()
#---------------------------------#
# end of Command Line Management  #
#---------------------------------#

def main():
    """
    Handles setup of threads for multithreading and starts processes.
    """

    # If the server file directory is missing, creates it
    if not os.path.exists(FILE_UPLOAD_PATH):
        print(f"{FILE_UPLOAD_PATH} directory missing. Creating directory.")
        os.mkdir(FILE_UPLOAD_PATH)

    # Load metadata
    load_metadata()

    peer_id, host, p2p_port, http_port, base_path = parse_cli_args() # get initial arguments
    debug("Peer ID:", peer_id, "Host:", host, "P2P Port:", p2p_port, "HTTP Port:", http_port, "Base Path:", base_path)

    server_thread = threading.Thread(target=p2p_server, args=(peer_id, host, p2p_port, http_port), daemon=True)
    server_thread.start()

    server_ready.wait() # wait on P2P server to start

    try:
        first_gossip(host, p2p_port, peer_id) # Send a first gossip to a Well-Known-Host from this peer
    except KeyboardInterrupt:
        print("Exiting program...")
        sys.exit(0)

    peer_cleanup_thread = threading.Thread(target=peer_cleanup, daemon=True)
    peer_cleanup_thread.start()

    gossip_thread = threading.Thread(target=interval_send_gossip, args=(host, p2p_port, peer_id), daemon=True)
    gossip_thread.start()

    try:
        command_line(peer_id)
    except KeyboardInterrupt:
        print("Exiting program...")
        sys.exit(0)

#end main()





#--------------------------#
#---# The Main Program #---#
#                          #
# does the things          #
#--------------------------#
main()
#--------------------------#
# end of The Main Program  #
#--------------------------#