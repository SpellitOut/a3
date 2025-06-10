import os
import sys
import json
import socket
import threading



#---# Program Defaults #---#
DEFAULT_HOST = "localhost"
DEFAULT_P2P_PORT = 8270
DEFAULT_HTTP_PORT = 8080
DEFAULT_BASE_PATH = "./"
DEBUG_ENABLED = False
#--------------------------#

#---# Program Constants #---#
METADATA_FILE = "metadata.json"
#---------------------------#

#---# Program Globals #---#
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
#-----------------------------#
# end of Metadata Management  #
#-----------------------------#



#---------------------------------#
#---# Peer-to-Peer Management #---#
#                                 #
# code related to managing        #
# the p2p server                  #
#---------------------------------#
def receive_message(client_socket):
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
            msg = decoder.raw_decode(buffer.decode())
            return msg
        except json.JSONDecodeError:
            # keep reading
            continue

    # if connection has closed, but JSON is still invalid, throw an error
    raise ConnectionError("Invalid JSON received before connection was closed.")

def handle_client(client_socket, addr):
    debug(f"Accepted connection from {addr}")
    try:
        msg = receive_message(client_socket)
        if msg:
            print(f"Received from {addr}: {msg}")
    except Exception as e:
        print(f"Exception while communicating with {addr}: {e}")
    finally:
        client_socket.close()
        print(f"Connection closed from {addr}")

def p2p_help_commands():
    """
    Helper function to print the list of commands and how to use them
    """
    print(f"Use 'get <file_id> [destination]' to download files\n" + 
          "Use 'push <filepath>' to upload files\n" + 
          "Use 'list' to view available files\n" +
          "Use 'peers' to view connected peers\n" + 
          "Use 'exit' to quit"
          )

def p2p_server(peer_id, host, port, http_port):
    """
    Start the p2p server on the host and port with peer_id
    """
    server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_sock.bind((host, port))
    server_sock.listen()
    server_sock.settimeout(10) # seconds
    print(f"Peer {peer_id} running on {host}:{port}, HTTP on {http_port}")
    p2p_help_commands()
    server_ready.set() # Server is ready

    while True:
        try:
            client_socket, addr = server_sock.accept()
            threading.Thread(target=handle_client, args=(client_socket, addr), daemon=True).start()
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

def command_line():
    """
    Repeatedly takes in inputs to process
    """
    while True:
        cmd = input("> ").strip()
        match cmd:
            case "list":
                # show file metadata
                debug("listing received")
            case "peers":
                # show tracked peers
                debug("tracking peers")
            case "push":
                # handle push
                debug("handling push")
            case "get":
                # handle get
                debug("handling get") 
            case "delete":
                # handle delete
                debug("handling delete")
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
    peer_id, host, p2p_port, http_port, base_path = parse_cli_args() # get initial arguments
    debug("Peer ID:", peer_id, "Host:", host, "P2P Port:", p2p_port, "HTTP Port:", http_port, "Base Path:", base_path)

    server_thread = threading.Thread(target=p2p_server, args=(peer_id, host, p2p_port, http_port), daemon=True)
    server_thread.start()

    server_ready.wait() # wait on P2P server to start

    try:
        command_line()
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