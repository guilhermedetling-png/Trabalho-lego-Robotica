# ev3/main.py
# LEGO EV3 Rubik's Cube solver client.
#
# Requer:
# - EV3 rodando Python compatível com ev3dev2
# - 3 motores:
#   A = base
#   B = troca/virada de face
#   C = movimentação do sensor de cor
# - 1 sensor de cor
#
# Observação importante:
# Os valores de posição do sensor e os movimentos mecânicos
# precisam ser ajustados à sua montagem.

import socket
from time import sleep
from typing import Dict, Tuple, List

from ev3dev2.motor import LargeMotor, MediumMotor, OUTPUT_A, OUTPUT_B, OUTPUT_C
from ev3dev2.sensor.lego import ColorSensor


# =========================================================
# CONFIGURAÇÃO GERAL
# =========================================================

PC_HOST = "192.168.0.10"   # Troque pelo IP do PC que executa o solver
PC_PORT = 9999

# Portas do EV3
base_motor = LargeMotor(OUTPUT_A)      # gira a base do cubo
face_motor = LargeMotor(OUTPUT_B)      # vira o cubo para outra face
sensor_motor = MediumMotor(OUTPUT_C)   # move o sensor de cor

sensor = ColorSensor()

# Tente usar RGB bruto para melhorar a detecção.
# Se o seu firmware não suportar exatamente esse modo, ajuste aqui.
try:
    sensor.mode = "RGB-RAW"
except Exception:
    pass


# =========================================================
# CALIBRAÇÃO DE CORES
# =========================================================
# O sensor de cor do EV3 varia bastante conforme luz ambiente.
# Os valores abaixo são referências NORMALIZADAS (r,g,b) e devem
# ser ajustados com leituras reais do seu robô.
#
# A saída final precisa ser uma letra do conjunto:
# U, R, F, D, L, B
#
# Aqui usamos a convenção mais comum do cubo:
# W -> U
# R -> R
# G -> F
# Y -> D
# O -> L
# B -> B

COLOR_REFERENCES: Dict[str, Tuple[float, float, float]] = {
    "W": (0.34, 0.33, 0.33),
    "R": (0.55, 0.23, 0.22),
    "G": (0.23, 0.55, 0.22),
    "Y": (0.40, 0.40, 0.20),
    "O": (0.50, 0.30, 0.20),
    "B": (0.20, 0.30, 0.50),
}

# Conversão da cor detectada para a face do solver.
COLOR_TO_FACE = {
    "W": "U",
    "R": "R",
    "G": "F",
    "Y": "D",
    "O": "L",
    "B": "B",
}

# Ordem das faces no cubo para o solver.
FACE_ORDER = ["U", "R", "F", "D", "L", "B"]


# =========================================================
# POSIÇÕES DO SENSOR
# =========================================================
# O sensor vai precisar de posições absolutas. Como a mecânica
# muda de robô para robô, estes valores são só ponto de partida.
#
# Exemplo de uso:
# - pos 4 = centro
# - os outros índices representam os demais pontos da face
#
# Ajuste esses ângulos conforme o seu mecanismo.

SENSOR_POSITIONS = {
    0: -160,
    1: -110,
    2: -60,
    3: -10,
    4: 0,      # centro
    5: 10,
    6: 60,
    7: 110,
    8: 160,
}

# Ordem de leitura: centro primeiro, depois os demais pontos.
# Isso ajuda na calibração, mas a string final continua em ordem
# padrão 0..8.
SCAN_SEQUENCE = [4, 0, 1, 2, 3, 5, 6, 7, 8]


# =========================================================
# FUNÇÕES DE BAIXO NÍVEL
# =========================================================

def reset_all_motors() -> None:
    """Zera os encoders dos motores."""
    base_motor.reset()
    face_motor.reset()
    sensor_motor.reset()


def move_sensor_to(slot: int) -> None:
    """
    Move o sensor para uma posição predefinida.

    slot: inteiro de 0 a 8.
    """
    target = SENSOR_POSITIONS[slot]
    sensor_motor.on_to_position(speed=20, position=target)
    sleep(0.15)


def normalize_rgb(rgb: Tuple[int, int, int]) -> Tuple[float, float, float]:
    """
    Normaliza o RGB para reduzir o efeito da iluminação.
    Retorna valores que somam 1.
    """
    r, g, b = rgb
    r = max(0, int(r))
    g = max(0, int(g))
    b = max(0, int(b))
    total = r + g + b
    if total == 0:
        return (0.0, 0.0, 0.0)
    return (r / total, g / total, b / total)


def distance(a: Tuple[float, float, float], b: Tuple[float, float, float]) -> float:
    """Distância euclidiana entre dois vetores RGB normalizados."""
    return ((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2 + (a[2] - b[2]) ** 2) ** 0.5


def read_raw_rgb() -> Tuple[int, int, int]:
    """Lê o RGB bruto do sensor."""
    try:
        return tuple(sensor.rgb)
    except Exception:
        # Fallback se o firmware expuser a cor em modo diferente.
        # Você pode adaptar isso conforme necessário.
        c = sensor.color
        # Mapeamento simples para algo razoável.
        fallback = {
            1: (255, 255, 255),  # branco
            2: (0, 0, 255),      # azul
            3: (0, 255, 0),      # verde
            4: (255, 255, 0),    # amarelo
            5: (255, 0, 0),      # vermelho
            6: (255, 128, 0),    # laranja
        }
        return fallback.get(c, (0, 0, 0))


def classify_color(rgb: Tuple[int, int, int]) -> str:
    """
    Classifica a cor lida para uma das letras:
    W, R, G, Y, O, B
    """
    norm = normalize_rgb(rgb)
    best_color = None
    best_distance = 1e9

    for label, reference in COLOR_REFERENCES.items():
        d = distance(norm, reference)
        if d < best_distance:
            best_distance = d
            best_color = label

    return best_color or "W"


# =========================================================
# LEITURA DAS FACES
# =========================================================

def read_face() -> str:
    """
    Lê uma face inteira do cubo e retorna 9 letras no padrão do solver.

    A ordem final da face é:
    0 1 2
    3 4 5
    6 7 8

    Internamente, o centro é lido primeiro, mas a string final fica
    reorganizada na ordem correta.
    """
    face_letters = [""] * 9

    for slot in SCAN_SEQUENCE:
        move_sensor_to(slot)
        rgb = read_raw_rgb()
        color_label = classify_color(rgb)

        # Converte a cor física para a letra da face do cubo.
        face_letter = COLOR_TO_FACE.get(color_label, "U")
        face_letters[slot] = face_letter

    return "".join(face_letters)


def turn_to_next_face() -> None:
    """
    Rotação mecânica para passar à próxima face do cubo.

    Essa função depende totalmente da sua montagem.
    O valor abaixo é apenas um ponto de partida.
    """
    face_motor.on_for_degrees(speed=25, degrees=90)
    sleep(0.25)


def read_cube() -> str:
    """
    Lê as 6 faces e retorna a string de 54 caracteres
    no formato exigido pelo Kociemba.
    """
    cube_faces: Dict[str, str] = {}

    for face_name in FACE_ORDER:
        cube_faces[face_name] = read_face()
        if face_name != FACE_ORDER[-1]:
            turn_to_next_face()

    return "".join(cube_faces[f] for f in FACE_ORDER)


# =========================================================
# COMUNICAÇÃO COM O PC
# =========================================================

def request_solution(cube_string: str) -> str:
    """
    Envia a string do cubo para o PC e recebe a solução.
    Protocolo simples:
    - envia: cube_string + "\\n"
    - recebe: uma linha com os movimentos
    """
    with socket.create_connection((PC_HOST, PC_PORT), timeout=15) as sock:
        sock.sendall((cube_string + "\n").encode("utf-8"))
        data = sock.recv(8192).decode("utf-8").strip()
        return data


# =========================================================
# EXECUÇÃO DOS MOVIMENTOS
# =========================================================
# Este bloco é o ponto que mais depende da sua mecânica.
# Abaixo está uma base simples.
#
# Se o seu robô executa movimentos diferentes para cada face,
# ajuste aqui sem mexer no restante do projeto.

def turn_base(quarter_turns: int) -> None:
    """Gira a base em múltiplos de 90°."""
    degrees = quarter_turns * 90
    base_motor.on_for_degrees(speed=30, degrees=degrees)
    sleep(0.15)


def turn_face(quarter_turns: int) -> None:
    """Gira a face mecânica em múltiplos de 90°."""
    degrees = quarter_turns * 90
    face_motor.on_for_degrees(speed=30, degrees=degrees)
    sleep(0.15)


def apply_move(move: str) -> None:
    """
    Executa um movimento do solver.

    Exemplo:
    U, U', U2, R, R', R2, etc.
    """
    if not move:
        return

    face = move[0]
    suffix = move[1:] if len(move) > 1 else ""

    turns = 1
    if suffix == "2":
        turns = 2
    elif suffix == "'":
        turns = -1

    # Mapeamento básico:
    # U / D -> base
    # R / L -> face
    # F / B -> aqui você pode adicionar a lógica da sua mecânica
    #
    # Se o seu robô não tiver uma ação específica para F/B,
    # use uma rotina de reorientação do cubo.
    if face in ("U", "D"):
        turn_base(turns)
    elif face in ("R", "L"):
        turn_face(turns)
    elif face in ("F", "B"):
        # Ajuste conforme sua montagem.
        # Esta implementação é propositalmente centralizada
        # para não quebrar o restante do projeto.
        turn_base(turns)
        turn_face(turns)
    else:
        # Movimento desconhecido, ignora.
        pass


def execute_solution(solution: str) -> None:
    """Executa a sequência recebida do PC."""
    moves = solution.split()
    for move in moves:
        apply_move(move)
        sleep(0.2)


# =========================================================
# MAIN
# =========================================================

def main() -> None:
    reset_all_motors()
    sleep(1)

    print("Lendo cubo...")
    cube_string = read_cube()
    print("Estado lido:", cube_string)

    print("Enviando para o PC...")
    solution = request_solution(cube_string)
    print("Solução recebida:", solution)

    if solution:
        print("Executando solução...")
        execute_solution(solution)
        print("Fim.")
    else:
        print("Nenhuma solução recebida.")


if __name__ == "__main__":
    main()