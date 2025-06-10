import os
import sys
import json


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

def save_metadata(data):
    """
    Saves the metadata to the file
    """
    try:
        with open(METADATA_FILE, "w") as f:
            json.dump(data, f, indent=2)
    except IOError as e:
        debug(f"Failed to write metadata to {METADATA_FILE}: {e}")

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


def main():
    peer_id, host, p2p_port, http_port, base_path = parse_cli_args() # get initial arguments
    debug("Peer ID:", peer_id, "Host:", host, "P2P Port:", p2p_port, "HTTP Port:", http_port, "Base Path:", base_path)

    command_line()
#end main()





#=================

main()

#=================