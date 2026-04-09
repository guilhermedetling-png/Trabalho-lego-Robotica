# pc/solver_server.py
# Servidor simples que recebe o estado do cubo e devolve a solução.
#
# Requer:
#   pip install kociemba
#
# O EV3 envia uma string de 54 caracteres no padrão:
# UUUUUUUUURRRRRRRRRFFFFFFFFFDDDDDDDDDLLLLLLLLLBBBBBBBBB
#
# O servidor devolve algo como:
# R U R' U' ...

import argparse
import socket
from typing import Tuple

import kociemba


def is_valid_cube_string(cube: str) -> bool:
    """
    Valida se a string tem 54 caracteres e usa apenas U, R, F, D, L, B.
    """
    if len(cube) != 54:
        return False
    allowed = set("URFDLB")
    return all(ch in allowed for ch in cube)


def solve_cube(cube: str) -> str:
    """
    Resolve o cubo usando kociemba.
    Retorna string vazia se houver erro.
    """
    try:
        return kociemba.solve(cube)
    except Exception:
        return ""


def handle_client(conn: socket.socket, addr: Tuple[str, int]) -> None:
    """
    Processa uma conexão por vez.
    """
    print(f"Conectado: {addr[0]}:{addr[1]}")
    with conn:
        buffer = ""
        while True:
            data = conn.recv(1024)
            if not data:
                break

            buffer += data.decode("utf-8", errors="ignore")

            # Processa linha por linha
            while "\n" in buffer:
                line, buffer = buffer.split("\n", 1)
                cube = line.strip().upper()

                if not cube:
                    conn.sendall(b"\n")
                    continue

                if not is_valid_cube_string(cube):
                    conn.sendall(b"ERROR: invalid cube string\n")
                    continue

                solution = solve_cube(cube)
                if not solution:
                    conn.sendall(b"ERROR: solver failed\n")
                    continue

                conn.sendall((solution + "\n").encode("utf-8"))
                print("Estado:", cube)
                print("Solucao:", solution)


def main() -> None:
    parser = argparse.ArgumentParser(description="EV3 cube solver server")
    parser.add_argument("--host", default="0.0.0.0", help="IP de escuta")
    parser.add_argument("--port", default=9999, type=int, help="Porta TCP")
    args = parser.parse_args()

    print(f"Servidor ouvindo em {args.host}:{args.port}")
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server:
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server.bind((args.host, args.port))
        server.listen(1)

        while True:
            conn, addr = server.accept()
            handle_client(conn, addr)


if __name__ == "__main__":
    main()