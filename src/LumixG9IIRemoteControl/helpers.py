import socket


def get_local_ip() -> str:
    local_ip = socket.gethostbyname(socket.gethostname())
    if local_ip.startswith("127."):
        local_ip = socket.gethostbyname(socket.getfqdn())
        if local_ip.startswith("127."):
            raise "cannot determine ip"
    return local_ip
