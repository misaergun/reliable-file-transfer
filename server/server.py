import socket

HOST = "127.0.0.1"
PORT = 5050

server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

server_socket.bind((HOST, PORT))
server_socket.listen(1)

print(f"Server listening on {HOST}:{PORT}")

client_socket, client_address = server_socket.accept()

print(f"Client connected: {client_address}")

data = client_socket.recv(1024)

print(f"Received: {data.decode()}")

client_socket.close()
server_socket.close()