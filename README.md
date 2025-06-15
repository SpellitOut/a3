# TreeDrive P2P FileSharing
### Ian Spellman - 7891649

This is a Python-based peer-to-peer (P2P) file-sharing system with a built-in web server that displays live statistics about tracked peers and files.

## Table of Contents

- [Features](#features)

- [Files](#files)

- [How to Run](#how-to-run)

    - [Command Line Arguments](#command-line-arguments)

- [Available Commands](#available-commands)

- [Peer and File Stats](#peer-and-file-stats)

- [Some notes on Code](#some-notes-on-code)

    - [Handling of Metadata](#handling-of-metadata)

    - [Cleaning Peers](#cleaning-peers)

- [Reliable Aviary Birds](#reliable-aviary-birds)

## Features
- Peer-to-peer file sharing using TCP sockets.
- Gossip protocol for peer discovery.
- Web server using raw sockets (no external frameworks).
- Stats page served as HTML + JS, auto-updates using `XMLHttpRequest` without page refresh.
- Displays tracked peers, file metadata, and live updates.

## Files
- `peer.py` - main Python script running the P2P node and HTTP server.
- `index.html` - webpage displaying the peer stats.
- `stats.js` - handles periodic stats fetching via `XMLHttpRequest`.
- `style.css` - styling for the webpage.
- `metadata.json` - file metadata storage (created/used at runtime).

## How to Run

Before you run the program, you must first configure the Well-Known-Host in `peer.py`, which can be found at the top of the file `peer.py`.

    #---# WELL KNOWN HOST INFORMATION #---#
    # You may adjust these values to      #
    # match a well-known-host of your own #
    KNOWN_HOST = "localhost"
    KNOWN_PORT = "8270"
    #-------------------------------------#

Set `KNOWN_HOST` and `KNOWN_PORT` to the known host and port that you would like to join the P2P network through.

**NOTE:** Some example Well-Known-Hosts are, `silicon.cs.umanitoba.ca:8999`, `hawk.cs.umanitoba.ca:8999`, `grebe.cs.umanitoba.ca:8999`, `eagle.cs.umanitoba.ca:8999`

The last thing to do before running the program is ensure that in the same directory as `peer.py` you have the following files:

    index.html
    stats.js
    style.css

If you do not have these files in the same directory as `peer.py` you will not be able to access the web-page for stats.

Once you have configured the Well-Known-Host, you may run the program with the following Command Line Arguments.

### Command Line Arguments

    <peer_id>: The peerID you want to connect as.
    [host]: The host machine you are connecting from.
    [p2p_port]: The port your machine will connect from.
    [http_port]: The port that the stats page will run on.

**Note:** by default, the peer_id is `spellmai`.

**Note:** by default, the host and port will be `localhost:8270` so remember to include a host and port when you run the program.

In your terminal where the files are stored, run:

    python peer.py <peer_ID> [host] [p2p_port] [http_port]

Upon running this command in your terminal, the program will create a `metadata.json` file and a directory `/FileUploads`. These files must exist in the same directory as `peer.py` to correctly maintain file data for the P2P FileSharing network.

Wait a few seconds for things to get initialized. The peer will attempt to gossip to a Well-Known-Host to enter a P2P network. If it cannot reach a Well-Known-Host, the peer will exist partitioned on its own. Other peers then may connect to it as if it were the Well-Known-Host.

Upon joining a Well-Known-Host, the peer will wait to receive `GOSSIP_REPLY`s about files that exist on the network, then will attempt to download up to 3 files that this peer does not have saved locally.

After waiting on gossip replies for a few seconds the webserver will start and provide you a link to connect to if you would like to view peer and file stats through your browser.

Once a peer is connected to other peers, it will `GOSSIP` every `GOSSIP_INTERVAL = 30` seconds so other peers know it is still alive.

## Available Commands

While running a peer through a Command-Line-Interface (CLI) there are a number of commands you may use.

**Note:** Commands are case sensitive. `list` and `LIST` are not the same.

`list <option>` : Displays a list of the peer's tracked files.
option may be `local`, `remote`, or `both`. If left blank, `both` is the default selected.

    list local : shows a list of files saved locally
    list remote : shows a list of files NOT stored locally
    list both : shows a list of both locally and remotely saved files 

`peers` : Displays a list of the peer's tracked peers.

`get <file_id>` : Requests to download a file from a peer that has a copy. Announces to other peers when it receives a new file.

`push <filepath>` : Pushes a file to the peer locally, and attempts to forward it to 1 other peer.

`ls` : List the contents of your current directory.

`exit` : quits safely.

`help` : Shows a list of these commands.

## Peer and File Stats

To view peer and file stats in your browser, you may connect to the webpage at:

    http://<host>:<http_port>

## Some notes on Code

There are a few important pieces of code that I would like to highlight, as they represent core features of making sure the P2P FileSharing system stays sychonized.

### Handling of Metadata

There are multiple functions to manage the file metadata for the peers. They can be found from lines 79-139 of `peer.py`.

    load_metadata(): Attempts to load metadata from metadata.json into a dictionary and returns it.

    update_metadata(file_id, file_metadata): Adds or updates a file entry in the metadata. It only updates if the file is new or has a newer timestamp. Properly appends and removes the field "peers_with_file".

    save_metadata(data): Writes data to the metadata file.

The metadata functions use thread-locking to ensure that multiple threads are not handling the metadata at the same time so that we can safely read and write to `metadata.json`.

Thread locking was important because if a peer receives multiple `GOSSIP_REPLY`s or `ANNOUNCE`ments at once, we need to ensure the metadata is not being accessed by multiple threads concurrently or we risk corruption and bad json data.

### Cleaning Peers

From lines 211-235 there is a function used to clean up the file metadata on the peer, so that the metadata only contains files that this peer has locally.

    cleanup_on_exit(my_peer_id): Cleanly exits the peer by cleaning up its metadata. Removes all files not stored locally from metadata. Removes all peers_with_file entries except for itself on local files.

This function runs when starting the peer to make sure the peer only has up-to-date metadata, so if a peer were to crash, its metadata is cleaned on next start. It also runs when a peer exits safely.

In addition to cleaning the file metadata stored on the peer, we also need to clean up outdated peers who have not gossiped to us in some time.

From lines 641-672 there are some functions used to remove peers, and old peers.

    peer_cleanup(): Periodically checks tracked peers to see if any have timed out.

    remove_peer(host, port): Immediately removes a tracked peer.

    remove_old_peers(timeout=PEER_TIMEOUT): Removes peers from tracked peers that have not been heard from in timeout seconds. Called periodically by peer_cleanup().

When the program starts, peer_cleanup() runs on a thread where it waits `PEER_CLEANUP_INTERVAL = 10` before attempting to remove old peers. If peers have not been heard from in over `PEER_TIMEOUT = 60` seconds, they are pruned from the tracked peers.

## Reliable Aviary Birds

This is a list of the reliable aviary birds at UManitoba. Please refer to this list for their IP addresses.

    130.179.28.110  rookery.cs.umanitoba.ca
    130.179.28.111  cormorant.cs.umanitoba.ca
    130.179.28.112  crow.cs.umanitoba.ca
    130.179.28.113  eagle.cs.umanitoba.ca
    130.179.28.114  falcon.cs.umanitoba.ca
    130.179.28.115  finch.cs.umanitoba.ca
    130.179.28.116  goose.cs.umanitoba.ca
    130.179.28.117  grebe.cs.umanitoba.ca
    130.179.28.118  grouse.cs.umanitoba.ca
    130.179.28.119  hawk.cs.umanitoba.ca
    130.179.28.120  heron.cs.umanitoba.ca
    130.179.28.121  killdeer.cs.umanitoba.ca
    130.179.28.122  kingfisher.cs.umanitoba.ca
    130.179.28.123  loon.cs.umanitoba.ca
    130.179.28.124  nuthatch.cs.umanitoba.ca
    130.179.28.125  oriole.cs.umanitoba.ca
    130.179.28.126  osprey.cs.umanitoba.ca
    130.179.28.127  owl.cs.umanitoba.ca
    130.179.28.128  pelican.cs.umanitoba.ca