"""
Name:           Ian Spellman
Student number: 7891649
Course:         A01 - COMP3010
Instructor:     Dr. Saulo dos Santos

Assignment 3

peer.py

    Creates a Filesharing peer that stores files, metadata and statistic about the peer.

    Allows peers to connect to other peers in a Peer-to-Peer (P2P) network.

    peer.py maintains file metadata and files uploaded by the invidivual peer (this)

    peer.py runs a command-line terminal to allow you to run commands and interact with other peers

    See the README.md for further functionality
"""

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
NUM_FILES_ON_JOIN = 3 # how many files do we attempt to get on join
#---------------------------#

#---# Program Globals #---#
tracked_peers = {} # key: peerId, value: dict with host, port, last_seen
seen_gossip_ids = set() # uses a set to avoid repeats
server_ready = threading.Event()
METADATA_LOCK = threading.RLock()
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
    with METADATA_LOCK:
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
    with METADATA_LOCK:
        metadata = load_metadata()
        old = metadata.get(file_id)

        if old is None:
            # New file - initialize peers_with_file if missing
            if "peers_with_file" not in file_metadata:
                file_metadata["peers_with_file"] = []
            metadata[file_id] = file_metadata
            save_metadata(metadata)
            return True

        if file_metadata["file_timestamp"] > old["file_timestamp"]:
            # keep dynamic lists like peers_with_file
            preserve_fields = {}
            preserve_fields["peers_with_file"] = old.get("peers_with_file", [])

            # build an updated entry
            updated = dict(file_metadata) # start with new data
            updated.update(preserve_fields) # add the preserved fields

            metadata[file_id] = updated
            save_metadata(metadata)
            return True # updated or added successfully
        
        return False # No update
# end update_metadata()

def save_metadata(data):
    """
    Saves the metadata to the file
    """
    with METADATA_LOCK:
        try:
            with open(METADATA_FILE, "w") as f:
                json.dump(data, f, indent=2)
        except IOError as e:
            debug(f"Failed to write metadata to {METADATA_FILE}: {e}")
#end save_metadata()

def get_local_file_entries(metadata, directory="FileUploads"):
    """Return list of file metadata for files present in the directory"""
    with METADATA_LOCK:
        local_files = set(os.listdir(directory))
        local_entries = []

        for file_id, entry in metadata.items():
            if file_id in local_files:
                local_entries.append(entry)

        return local_entries
# end get_local_file_entries()

def get_remote_file_entries(metadata, directory="FileUploads"):
    """Return list of file metadata for files NOT present in the directory"""
    with METADATA_LOCK:
        local_files = set(os.listdir(directory))
        remote_entries = []

        for file_id, entry in metadata.items():
            if file_id not in local_files:
                remote_entries.append(entry)

        return remote_entries
# end get_remote_file_entries()

def add_peer_to_file(file_id, peer_id):
    """
    Adds a peer_id to the peers_with_file list for a file's metadata
    """
    with METADATA_LOCK:
        metadata = load_metadata()

        if file_id not in metadata:
            return False # cannot add
        
        entry = metadata[file_id]

        if "peers_with_file" not in entry:
            entry["peers_with_file"] = []

        if peer_id not in entry["peers_with_file"]:
            entry["peers_with_file"].append(peer_id)
            save_metadata(metadata)
            return True #peer added to metadata
        
        return False # Peer already listed
#end add_peer_to_file()

def remove_peer_from_files(peer_id):
    """
    Removes the given peer_id from peers_with_file list in all file entries in metadata.
    Saves metadata if any changes are made.
    """
    with METADATA_LOCK:
        metadata = load_metadata()
        updated = False

        for file_id, entry in metadata.items():
            peers = entry.get("peers_with_file")
            if isinstance(peers, list) and peer_id in peers:
                peers.remove(peer_id)
                updated = True

        if updated:
            save_metadata(metadata)

        return updated
#end remove_peer_from_files()

def cleanup_on_exit(my_peer_id):
    """
    Cleanly exit the peer by cleaning up it's metadata

    Removes all files not stored locally.

    Removes all peers_with_file entries except for itself on local files.
    """
    with METADATA_LOCK:
        metadata = load_metadata()
        clean_metadata = {}
        local_files = get_local_file_entries(metadata)
        local_files_ids = {entry["file_id"] for entry in local_files}

        for file_id, entry in metadata.items():
            if file_id in local_files_ids:
                # keep that file, clean up peers_with_file
                entry["peers_with_file"] = [my_peer_id]
                clean_metadata[file_id] = entry
                debug(f"Preserving {entry['file_name']} (local file), resetting peers_with_file to this peer.")
            else:
                debug(f"Removing metadata for {entry['file_name']} (remote file).")

        save_metadata(clean_metadata)
        debug("Cleaned metadata for this peer.")
# end cleanup_on_exit()
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

def msg_send_delete(file_id, my_peer_id):
    """
    Deletes a file locally from this peer if it owns it, and forwards the delete message to all tracked peers that have the file.
    """
    msg = msg_build_delete(my_peer_id, file_id)

    metadata = load_metadata()
    file_info = metadata.get(file_id)
    file_owner = file_info.get("file_owner")

    if my_peer_id == file_owner: # if we own the file, can attempt to delete locally
        file_path = os.path.join(FILE_UPLOAD_PATH, file_id)
        if os.path.isfile(file_path): # if we have it
            os.remove(file_path) # delete it
            print(f"Deleted local file {file_id} on request from owner {my_peer_id}")
        
        metadata.pop(file_id)
        save_metadata(metadata)

    # send a delete request to all tracked peers
    for peer_id, peer_info in list(tracked_peers.items()):
        if peer_info:
            send_message(msg, peer_info["host"], peer_info["port"])
# end msg_send_delete

def msg_send_get(file_id, my_peer_id):
    """
    Sends a get message to a peer who has the file we want.
    """
    file_path = os.path.join(FILE_UPLOAD_PATH, file_id)
    if os.path.isfile(file_path):
        print(f"File {file_id} is already present locally.")
        return

    peers = peers_with_file(file_id) # get a list of peers who have the file
    if not peers:
        print(f"Cannot get file. No tracked peers have file {file_id}")
        return
    
    peer = random.choice(peers)
    peer_info = tracked_peers.get(peer)
    if not peer_info:
        print(f"No connection info for peer {peer}")
        return
    
    to_host = peer_info["host"]
    to_port = peer_info["port"]

    msg = msg_build_get(file_id)

    try:
        # Open a socket to send the message, and maintain that socket
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as client_socket:
            client_socket.connect((to_host, to_port))
            client_socket.settimeout(30)
            client_socket.sendall(json.dumps(msg).encode())
            print(f"Get request sent to peer {peer}. Awaiting response.")

            # Wait to receive file data from them
            file_msg = receive_message(client_socket)
            debug(f"received file message: {file_msg} from SOCKET: {client_socket}")
            if file_msg:
                handle_message(file_msg, my_peer_id, to_host, to_port, client_socket)
            else:
                print(f"No FILE_DATA received in response to GET for {file_id} from peer {peer}")
    except Exception as e:
        print(f"Error sending GET or receiving FILE_DATA: {e}")
# end msg_send_get()

def load_files_on_join(my_peer_id):
    """
    Attempt to get a number of files (that we don't have) on join by sending GET requests to peers
    """
    local_files = set(os.listdir(FILE_UPLOAD_PATH))

    timeout = 10  # seconds to wait max
    waited = 0
    missing_files = []

    # checks if we have any missing files, waits some time to make sure we get some gossip info back first
    while waited < timeout:
        with METADATA_LOCK:
            metadata = load_metadata()
            missing_files = [
                (file_id, entry) for file_id, entry in metadata.items()
                if file_id not in local_files and entry["peers_with_file"]
            ]

        if missing_files:
            break

        time.sleep(1)
        waited += 1
        debug(f"Waiting for gossip replies... Waited {waited} second(s)")

    if not missing_files:
        print("No missing files discovered after gossip replies.")
        return

    files_to_get = random.sample(missing_files, min(NUM_FILES_ON_JOIN, len(missing_files)))

    for file_id, entry in files_to_get:
        print(f"Requesting file {file_id} ({entry['file_name']}) from peers...")
        msg_send_get(file_id, my_peer_id)
# end load_files_on_join()

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
        "file_size": round(len(file_contents) / (1024 * 1024), 2), # saved as MB
        "file_id": file_id,
        "file_owner": my_peer_id,
        "file_timestamp": timestamp,
        "peers_with_file": [my_peer_id]
    }

    # save the file locally
    path = os.path.join(FILE_UPLOAD_PATH, file_id)
    with open(path, "wb") as f:
        f.write(file_contents)

    print(f"File saved locally as: {file_id}")

    update_metadata(file_id, file_metadata) # add/update metadata on a file

    if tracked_peers: # if we have a tracked peer, send to 1 of them
        to_peer, peer_info = random.choice(list(tracked_peers.items()))
        to_host = peer_info["host"]
        to_port = peer_info["port"]
        send_file(file_contents, file_metadata, to_host, to_port, to_peer)

    # ANNOUNCE to all peers
    for peer_id, peer_info in list(tracked_peers.items()):
        msg_send_announce(my_peer_id, file_metadata, peer_info["host"], peer_info["port"], peer_id)

    print(f"File '{file_metadata['file_name']}' pushed to the network with ID: {file_id}")
# end push_file()

def send_file(content, file_metadata, to_host, to_port, to_peer):
    """
    Sends a file from this peer to a peer
    """
    msg = msg_build_file_data(content, file_metadata)
    sent = send_message(msg, to_host, to_port)
    if sent:
        print(f"File '{file_metadata['file_name']}' pushed to peer {to_peer} ({to_host}:{to_port})")

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
    local_files = get_local_file_entries(metadata)

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

def msg_build_delete(peer_id, file_id):
    """Build a message for DELETE format"""
    return {
        "type": "DELETE",
        "from": peer_id,
        "file_id": file_id
    }
# end msg_build_delete()

def msg_build_get(file_id):
    """Build a message for GET format"""
    return {
        "type": "GET_FILE",
        "file_id": file_id
    }
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
            remove_peer_from_files(peer_id)
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
            remove_peer_from_files(peer_id)
# end remove_old_peers()

def peers_with_file(file_id):
    """
    Returns a list of tracked peers that have file_id
    """
    metadata = load_metadata()
    file_info = metadata.get(file_id)
    if not file_info or "peers_with_file" not in file_info:
        return []
    
    # make sure to only return peers that we are still tracking
    peers = [
        peer_id for peer_id in file_info["peers_with_file"]
        if peer_id in tracked_peers
    ]

    return peers
# end peers_with_file()
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
        debug(f"receive_message: recv returned {len(data)} bytes: {data}")
        if not data:
            break
        buffer += data
        try:
            msg, index = decoder.raw_decode(buffer.decode())
            return msg
        except json.JSONDecodeError:
            continue  # need more data

    if buffer:
        # final attempt to parse
        try:
            msg, _ = decoder.raw_decode(buffer.decode())
            return msg
        except json.JSONDecodeError:
            raise ConnectionError("Connection closed before valid JSON was received.")
    else:
        return None
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
        add_peer_to_file(file_id, the_peer_id)
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
    add_peer_to_file(file_id, peer_id)
    if updated_file:
        print(f"Metadata updated for announced file: '{file_name}'")
# end receive_msg_announce()

def receive_msg_delete(msg):
    """
    Handles a DELETE message by deleting the file locally if the sender owns the file.
    """
    from_peer = msg["from"]
    file_id = msg["file_id"]

    metadata = load_metadata()
    file_info = metadata.get(file_id)

    if not file_info:
        return # nothing to delete
    
    # only delete if the owner sent the message
    if from_peer not in file_info.get("file_owner"):
        print(f"Rejecting delete for {file_id}: Not from owner")
        return
    
    # Remove file if this peer has it
    file_path = os.path.join(FILE_UPLOAD_PATH, file_id)
    if os.path.isfile(file_path):
        os.remove(file_path)
        print(f"Deleted local file {file_id} on request from owner {from_peer}")

    # update metadata
    metadata.pop(file_id)
    save_metadata(metadata)
# end receive_msg_delete()

def receive_msg_get(msg, client_socket):
    """
    Handles a GET message by checking if I still have the file that's been requested, then sending it.
    Maintains a TCP connection
    """
    file_id = msg["file_id"]

    file_path = os.path.join(FILE_UPLOAD_PATH, file_id)

    if not os.path.isfile(file_path):
        # We don't have the file, so send a None type FILE_DATA
        file_contents = b""
        file_metadata = {
            "file_name": None,
            "file_size": None,
            "file_id": None,
            "file_owner": None,
            "file_timestamp": None,
            "peers_with_file": None
        }
    else:
        # We have the file, so send it
        # load up the file
        metadata = load_metadata()
        file_metadata = metadata.get(file_id)
        with open(file_path, "rb") as f:
            file_contents = f.read()
    
    response = msg_build_file_data(file_contents, file_metadata)

    client_socket.sendall(json.dumps(response).encode())

    debug(f"FILE_DATA sent on socket: {client_socket.getsockname()} -> {client_socket.getpeername()}")
# end receive_msg_get()

def receive_msg_file_data(msg, my_peer_id):
    """
    Handles a FILE_DATA message by saving the file locally and updates metadata

    Can receive from PUSHes or GETs
    """
    file_name = msg["file_name"]
    file_size = msg["file_size"]
    file_id = msg["file_id"]
    file_owner = msg["file_owner"]
    file_timestamp = msg["file_timestamp"]
    data_hex = msg["data"]

    if file_id is None:
        return # they sent a bad file

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
    add_peer_to_file(file_id, file_owner)
    add_peer_to_file(file_id, my_peer_id)

    #reload and make sure we have up-to-date metadata before we announce to peers
    metadata = load_metadata()
    file_info = metadata.get(file_id)

    # ANNOUNCE to all peers
    for peer_id, peer_info in list(tracked_peers.items()):
        msg_send_announce(my_peer_id, file_info, peer_info["host"], peer_info["port"], peer_id)

# end receive_msg_file_data()

def handle_message(msg, my_peer_id, my_host, my_port, client_socket):
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
        receive_msg_file_data(msg, my_peer_id)
    elif type == "DELETE":
        debug("Handling DELETE")
        receive_msg_delete(msg)
    elif type == "GET_FILE":
        debug("Handling GET")
        receive_msg_get(msg, client_socket)
    else:
        print(f"Unhandled Message Type: {type}")
# end handle_message()

def handle_client(client_socket, addr, peer_id, host, port):
    """
    Handles receiving messages from a client and passing off responsibility to the correct handlers
    """
    debug(f"Accepted connection from {addr}")
    try:
        while True: # loop in case of multiple messages
            msg = receive_message(client_socket)
            if not msg:
                debug(f"Connection close by peer at {addr}")
                break
            if msg.get("peerId") == peer_id:
                debug(f"Received connection my myself. Ignoring.")
                continue # ignore because it's my own message
            debug(f"Received from {addr}: {msg}")
            handle_message(msg, peer_id, host, port, client_socket)
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
          "Use 'list' to view available files. Can also use 'list local', 'list remote', or 'list both' to show known files.\n" +
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



#------------------------------#
#---# Webserver Management #---#
#                              #
# code related to managing     #
# the webserver                #
#------------------------------#
def webserver(host, http_port, my_peer_id):
    """
    Starts a webserver at host and http_port
    """
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_socket.bind((host, http_port))
    server_socket.listen()
    print(f"Web server running at http://{host}:{http_port}")

    while True:
        conn, addr = server_socket.accept()
        threading.Thread(target=handle_http_client, args=(conn, my_peer_id,), daemon=True).start()
# end webserver()

def handle_http_client(client_socket, my_peer_id):
    """
    Parses HTTP requests then serves files to the client socket
    """
    try:
        request = client_socket.recv(1024).decode()
        if not request:
            client_socket.close()
            return
        
        # Parse request
        lines = request.splitlines()
        if len(lines) == 0:
            client_socket.close()
            return
        
        request_line = lines[0]
        tokens = request_line.split()
        if len(tokens) < 2:
            client_socket.close()
            return
        
        method, path = tokens[0], tokens[1]
        if method != 'GET':
            client_socket.close()
            return
        
        if path == '/' or path == 'index.html':
            serve_file(client_socket, 'index.html', 'text/html')
        elif path == '/stats.js':
            serve_file(client_socket, 'stats.js', 'application/javascript')
        elif path == '/style.css':
            serve_file(client_socket, 'style.css', 'text/css')
        elif path == '/stats.json':
            serve_stats(client_socket, my_peer_id)
        else:
            send_404(client_socket)
    except Exception as e:
        print(f"HTTP error: {e}")
    finally:
        client_socket.close()
# end handle_http_client()

def serve_file(client_socket, file_name, content_type):
    """
    Serves a file_name to the client_socket
    """
    try:
        with open(file_name, 'rb') as f:
            content = f.read()
        header = (
            f"HTTP/1.1 200 OK\r\n"
            f"Content-Type: {content_type}\r\n"
            f"Content-Length: {len(content)}\r\n"
            f"Connection: close\r\n"
            f"\r\n"
        )
        client_socket.sendall(header.encode() + content)
    except FileNotFoundError:
        send_404(client_socket)
# end serve_file

def serve_stats(client_socket, my_peer_id):
    """
    Serves the peer and file statistics as a formatted json to the client_socket
    """
    metadata = load_metadata()

    # Format peers list from tracked_peers
    peers = []
    for peer_id, peer_info in tracked_peers.items():
        peers.append({
            "peerId": peer_id,
            "host": peer_info.get("host", ""),
            "port": peer_info.get("port", ""),
            "last_seen": peer_info.get("last_seen", 0)
        })

    # Format files from metadata
    files = []
    for file_id, file_info in metadata.items():
        files.append({
            "file_name": file_info.get("file_name", ""),
            "file_size": file_info.get("file_size", 0),
            "file_id": file_id,
            "file_owner": file_info.get("file_owner", ""),
            "file_timestamp": file_info.get("file_timestamp", 0),
            "has_copy": my_peer_id in file_info.get("peers_with_file"),
            "peers_with_file": file_info.get("peers_with_file", []),
        })

    stats_data = {
        "peerId": my_peer_id,
        "peers": peers,
        "files": files,
    }

    body = json.dumps(stats_data).encode()
    header = (
        f"HTTP/1.1 200 OK\r\n"
        f"Content-Type: application/json\r\n"
        f"Content-Length: {len(body)}\r\n"
        f"Connection: close\r\n"
        f"\r\n"
    )
    client_socket.sendall(header.encode() + body)
# end serve_stats

def send_404(client_socket):
    """
    Sends a 404 error to the client socket
    """
    body = b"404 Not Found"
    header = (
        f"HTTP/1.1 404 Not Found\r\n"
        f"Content-Type: text/plain\r\n"
        f"Content-Length: {len(body)}\r\n"
        f"Connection: close\r\n"
        f"\r\n"
    )
    client_socket.sendall(header.encode() + body)
# end send_404
#------------------------------#
# end of Webserver Management  #
#------------------------------#



#---------------------------------#
#---# Command Line Management #---#
#                                 #
# code related to managing        #
# the command line                #
#---------------------------------#
def command_list(option="both"):
    """
    List file metadatas on this peer

    Parameters:
        option (str): 'local', 'remote', or default, 'both'. Lists the file metadatas.
            'local': list files stored locally
            'remote': list files NOT stored locally
            'both': list files stored locally as well as files NOT stored locally
    """
    metadata = load_metadata()

    if option=="local":
        files = get_local_file_entries(metadata)
        print("Local files:")
    elif option=="remote":
        files = get_remote_file_entries(metadata)
        print("Remote files:")
    else:
        files = list(metadata.values())
        print("All known files:")

    for f in files:
        file_id = f["file_id"]
        file_name = f["file_name"]
        peers_with_file = f["peers_with_file"]
        print(f"{file_id}: {file_name} - Peers: {peers_with_file}")
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
                if arg:
                    command_list(arg)
                else:
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
                    msg_send_get(arg, my_peer_id)
                    debug(f"handling get for {arg}")
                else:
                    print("Usage: get <fileId>")

            case "delete":
                # handle delete
                if arg:
                    msg_send_delete(arg, my_peer_id)
                    debug(f"handling delete for {arg}")
                else:
                    print("Usage: delete <fileId>")

            case "exit":
                # exit program
                cleanup_on_exit(my_peer_id)
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
    peer_id, host, p2p_port, http_port, base_path = parse_cli_args() # get initial arguments
    debug("Peer ID:", peer_id, "Host:", host, "P2P Port:", p2p_port, "HTTP Port:", http_port, "Base Path:", base_path)

    # If the server file directory is missing, creates it
    if not os.path.exists(FILE_UPLOAD_PATH):
        print(f"{FILE_UPLOAD_PATH} directory missing. Creating directory.")
        os.mkdir(FILE_UPLOAD_PATH)

    # ensure our metadata is fresh to our local files
    cleanup_on_exit(peer_id) 
    # Load metadata
    load_metadata()

    server_thread = threading.Thread(target=p2p_server, args=(peer_id, host, p2p_port, http_port), daemon=True)
    server_thread.start()

    server_ready.wait() # wait on P2P server to start

    try:
        first_gossip(host, p2p_port, peer_id) # Send a first gossip to a Well-Known-Host from this peer
    except KeyboardInterrupt:
        print("Exiting program...")
        sys.exit(0)

    # attempt to load 3-5 files from other peers, after our first gossip
    load_files_on_join(peer_id)

    peer_cleanup_thread = threading.Thread(target=peer_cleanup, daemon=True)
    peer_cleanup_thread.start()

    gossip_thread = threading.Thread(target=interval_send_gossip, args=(host, p2p_port, peer_id), daemon=True)
    gossip_thread.start()

    webserver_thread = threading.Thread(target=webserver, args=(host, http_port, peer_id,), daemon=True)
    webserver_thread.start()

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