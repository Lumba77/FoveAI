import socket
import sys
import threading
import time

TARGET_HOST = "127.0.0.1"
TARGET_PORT = 8000
LISTEN_PORTS = [8400, 8414, 8402, 8403, 8404, 8405]


def handle_client(client_socket, target_host, target_port):
    try:
        server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server_socket.connect((target_host, target_port))

        def forward(src, dst):
            try:
                while True:
                    data = src.recv(4096)
                    if not data:
                        break
                    dst.send(data)
            except:
                pass
            finally:
                try:
                    src.close()
                except:
                    pass
                try:
                    dst.close()
                except:
                    pass

        threading.Thread(target=forward, args=(client_socket, server_socket)).start()
        threading.Thread(target=forward, args=(server_socket, client_socket)).start()
    except Exception:
        client_socket.close()


def start_proxy(listen_port):
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        server.bind(("0.0.0.0", listen_port))
    except Exception as e:
        print(f"[Nervous System Router] Port {listen_port} already bound or error: {e}")
        return

    server.listen(5)
    print(
        f"[Nervous System Router] Listening on 0.0.0.0:{listen_port} -> forwarding to {TARGET_PORT}"
    )

    while True:
        client_sock, addr = server.accept()
        threading.Thread(
            target=handle_client, args=(client_sock, TARGET_HOST, TARGET_PORT)
        ).start()


if __name__ == "__main__":
    print("Starting Nervous System Port Forwarders...")
    for port in LISTEN_PORTS:
        threading.Thread(target=start_proxy, args=(port,), daemon=True).start()

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        sys.exit(0)
