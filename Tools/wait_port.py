import socket, sys, time

host, port, tries = sys.argv[1], int(sys.argv[2]), int(sys.argv[3])
for _ in range(tries):
    try:
        socket.create_connection((host, port), 2).close()
        sys.exit(0)
    except OSError:
        time.sleep(1)
sys.exit(1)