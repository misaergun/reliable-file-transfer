import socket

HOST = "127.0.0.1"
PORT = 5050

client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

client_socket.connect((HOST, PORT))

print("Connected to server")

message = "Hello Server"

client_socket.sendall(message.encode())

client_socket.close()