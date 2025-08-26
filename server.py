import socket
import time
import threading

HOST = "192.168.3.120"  # Your laptop's static IP
PORT = 8888
PING_INTERVAL = 5       # Seconds between pings

def ping_client(sock):
    while True:
        time.sleep(PING_INTERVAL)
        try:
            sock.sendall(b'ping\n')
        except (BrokenPipeError, ConnectionResetError, OSError):
            print("Client disconnected during ping.")
            break

def handle_client(client_socket, addr):
    print(f"Connected by {addr}")
    ping_thread = threading.Thread(target=ping_client, args=(client_socket,), daemon=True)
    ping_thread.start()
    
    try:
        while True:
            command = input("Enter command (or 'quit'): ").strip()
            if command.lower() in ['quit', 'exit']:
                break
            try:
                client_socket.sendall((command + '\n').encode('utf-8'))
                response = client_socket.recv(1024)
                if not response:
                    print("Client disconnected.")
                    break
                print(f"Received: {response.decode('utf-8').strip()}")
            except (ConnectionResetError, BrokenPipeError, OSError):
                print("Connection lost.")
                break
    finally:
        client_socket.close()
        print("Closed connection with client.")

# Main server loop
server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
server_socket.bind((HOST, PORT))
server_socket.listen(1)

print(f"Server listening on {HOST}:{PORT}...")

try:
    while True:
        print("Waiting for client...")
        client_socket, addr = server_socket.accept()
        handle_client(client_socket, addr)
finally:
    server_socket.close()
    print("Server shut down.")
