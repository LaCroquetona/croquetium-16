#!/usr/bin/env python3
# Croquetium 16 - terminal de colores (movil y PC)
# Un solo archivo: ensamblador + emulador + terminal. Sin librerias externas.
# Uso: python croquetium_terminal.py   y escribe "ayuda"

import json
import os
import sys
from pathlib import Path

if os.name == "nt":
    os.system("")  # activa los colores en la consola de Windows
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass


# =====================================================================
#  NUCLEO (el mismo de croquetium.py)
# =====================================================================

OPERACIONES = [
    (0x00, "0", 0x4A), (0x01, "1", 0x6F), (0x02, "-1", 0x6A), (0x03, "x", 0x0C),
    (0x04, "2x", 0x8C), (0x05, "y", 0x60), (0x06, "2y", 0x70), (0x07, "!x", 0x0D),
    (0x08, "PC+1", 0x2F), (0x09, "!y", 0x61), (0x0A, "!2y", 0x71), (0x0B, "-x", 0x0F),
    (0x0C, "-2x", 0x8F), (0x0D, "-y", 0x63), (0x0E, "-2y", 0x73), (0x0F, "x+1", 0x2F),
    (0x10, "y+1", 0x67), (0x11, "x-1", 0x0E), (0x12, "y-1", 0x62), (0x13, "x+y", 0x02),
    (0x14, "2x+y", 0x82), (0x15, "x+2y", 0x12), (0x16, "2x+2y", 0x92), (0x17, "x-y", 0x23),
    (0x18, "2x-y", 0xA3), (0x19, "x-2y", 0x33), (0x1A, "2x-2y", 0xB3), (0x1B, "y-x", 0x07),
    (0x1C, "y-2x", 0x87), (0x1D, "2y-x", 0x17), (0x1E, "x&y", 0x00), (0x1F, "x|y", 0x25),
]
OP_PC = 0x08
ROM_ALU = {op: rom for op, _, rom in OPERACIONES}
CONMUTATIVAS = {"x+y": "y+x", "2x+y": "y+2x", "x+2y": "2y+x",
                "2x+2y": "2y+2x", "x&y": "y&x", "x|y": "y|x"}
DESTINOS = {"A": 0, "B": 1, "C": 2, "M": 3, "N": 4}
CONDICIONES = {"": 0, ">0": 1, "=0": 2, ">=0": 3, "<0": 4, "!=0": 5, "<=0": 6, "jmp": 7}
NOMBRE_CONDICION = {v: k for k, v in CONDICIONES.items()}
ORDEN_CONDICIONES = [">=0", "<=0", "!=0", ">0", "<0", "=0", "jmp"]

PRIMERA_VARIABLE = 16
MAX_NUMERO = 0x7FFF
MASCARA = 0xFFFF
TAM_RAM = 0x10000

SISTEMA_POR_DEFECTO = {
    "cables": [
        {"nombre": "PARA", "que_hace": "para el reloj"},
        {"nombre": "SALTO_C", "que_hace": "el PC carga C"},
        {"nombre": "SALTO_R", "que_hace": "el PC y el banco cargan lo guardado en R"},
        {"nombre": "GUARDA_R", "que_hace": "R guarda PC+1 y el banco actual"},
        {"nombre": "BANCO_RAM", "que_hace": "las instrucciones salen de la RAM de programas"},
        {"nombre": "BANCO_ROM", "que_hace": "las instrucciones salen de la ROM"},
        {"nombre": "GRABA_PROG", "que_hace": "RAM de programas[B] = M[A], solo con banco ROM"},
        {"nombre": "A_MITAD", "que_hace": "A = A / 2: desplaza a la derecha y mantiene el signo"},
        {"nombre": "A_TECLA", "que_hace": "A = tecla pulsada, y la tecla se borra"},
    ],
    "instrucciones": [
        {"codigo": 1, "texto": "PARA", "cables": ["PARA"], "que_hace": "para la máquina"},
        {"codigo": 2, "texto": "LANZA", "cables": ["GUARDA_R", "BANCO_RAM", "SALTO_C"],
         "que_hace": "salta a C dentro de la RAM de programas y guarda la vuelta en R"},
        {"codigo": 3, "texto": "VUELVE", "cables": ["GUARDA_R", "BANCO_ROM", "SALTO_C"],
         "que_hace": "salta a C dentro de la ROM y guarda la vuelta en R"},
        {"codigo": 4, "texto": "RETORNA", "cables": ["SALTO_R"],
         "que_hace": "vuelve a donde dice R, en su banco"},
        {"codigo": 5, "texto": "GRABA", "cables": ["GRABA_PROG"],
         "que_hace": "copia M[A] en la RAM de programas, en la dirección B"},
        {"codigo": 6, "texto": "A/2 => A", "cables": ["A_MITAD"], "que_hace": "divide A entre 2"},
        {"codigo": 7, "texto": "TECLA => A", "cables": ["A_TECLA"],
         "que_hace": "lee la tecla pulsada (0 si no hay)"},
    ],
}


class ErrorEnsamblado(Exception):
    pass


def normalizar(texto):
    return texto.replace(" ", "").replace("\t", "")


class Sistema:
    def __init__(self, datos):
        self.cables = datos["cables"]
        self.instrucciones = sorted(datos["instrucciones"], key=lambda i: i["codigo"])
        self.bit_cable = {c["nombre"]: i for i, c in enumerate(self.cables)}
        self.por_codigo = {}
        self.por_texto = {}
        for ins in self.instrucciones:
            self.por_codigo[ins["codigo"]] = ins
            self.por_texto[normalizar(ins["texto"])] = ins

    def mascara(self, codigo):
        ins = self.por_codigo.get(codigo)
        if not ins:
            return 0
        return sum(1 << self.bit_cable[c] for c in ins["cables"])

    def buscar(self, texto):
        texto = normalizar(texto)
        for clave, ins in self.por_texto.items():
            if clave.upper() == texto.upper():
                return ins
        return None


def cargar_sistema():
    # Si hay un sistema.json al lado (el del proyecto) lo usa; si no, el de serie.
    for ruta in (Path(__file__).resolve().with_name("sistema.json"), Path.cwd() / "sistema.json"):
        try:
            if ruta.exists():
                return Sistema(json.loads(ruta.read_text(encoding="utf-8"))), str(ruta)
        except Exception:
            pass
    return Sistema(SISTEMA_POR_DEFECTO), "de serie"


SISTEMA, ORIGEN_SISTEMA = cargar_sistema()


def formas_de(plantilla):
    if plantilla == "PC+1":
        return [("PC+1", 0, 0)]
    textos = [plantilla] + ([CONMUTATIVAS[plantilla]] if plantilla in CONMUTATIVAS else [])
    ux, uy = "x" in plantilla, "y" in plantilla
    formas = []
    for bx, X in ((0, "A"), (1, "M")):
        if not ux and bx:
            continue
        for by, Y in ((0, "B"), (1, "N")):
            if not uy and by:
                continue
            for t in textos:
                formas.append((t.replace("x", X).replace("y", Y), bx, by))
    return formas


COMP = {}
TEXTO_COMP = {}
for _op, _pl, _ in OPERACIONES:
    for _t, _bx, _by in formas_de(_pl):
        COMP.setdefault(_t, (_op, _bx, _by))
        TEXTO_COMP.setdefault((_op, _bx, _by), _t)


def usa_x(op):
    return op != OP_PC and "x" in OPERACIONES[op][1]


def usa_y(op):
    return "y" in OPERACIONES[op][1]


def leer_numero(texto):
    try:
        return int(texto, 0)
    except ValueError:
        return None


def limpiar(linea):
    return normalizar(linea.split("//")[0])


def separar_condicion(t):
    bajo = t.lower()
    for cond in ORDEN_CONDICIONES:
        if bajo.endswith(cond):
            return t[:-len(cond)], cond
    return t, ""


def ensamblar(fuente, sistema=None):
    sistema = sistema or SISTEMA
    lineas, etiquetas = [], {}
    for num, linea in enumerate(fuente.splitlines(), 1):
        t = limpiar(linea)
        if not t:
            continue
        if t.startswith("(") and t.endswith(")"):
            nombre = t[1:-1]
            if nombre in etiquetas:
                raise ErrorEnsamblado(f"línea {num}: la etiqueta {nombre} ya existe")
            etiquetas[nombre] = len(lineas)
            continue
        lineas.append((num, t, linea.split("//")[0].strip()))
    variables, programa = {}, []
    for num, t, original in lineas:
        if t.startswith("@"):
            palabra = instruccion_numero(t[1:], num, etiquetas, variables)
        else:
            palabra = instruccion(t, num, sistema)
        programa.append((palabra, original))
    return programa, etiquetas, variables


def instruccion_numero(simbolo, num, etiquetas, variables):
    valor = leer_numero(simbolo)
    if valor is None:
        if simbolo in etiquetas:
            valor = etiquetas[simbolo]
        else:
            if simbolo not in variables:
                variables[simbolo] = PRIMERA_VARIABLE + len(variables)
            valor = variables[simbolo]
    if not 0 <= valor <= MAX_NUMERO:
        raise ErrorEnsamblado(f"línea {num}: @{simbolo} no cabe en 15 bits (0 a {MAX_NUMERO}). "
                              "Para negativos: mete el positivo y haz -A => A")
    return 0x8000 | valor


def instruccion(t, num, sistema):
    if t.upper() == "NOP":
        return 0
    ins = sistema.buscar(t)
    if ins:
        return ins["codigo"] << 8
    resto, cond = separar_condicion(t)
    comp, destino = resto, ""
    if "=>" in resto:
        comp, destino = resto.split("=>", 1)
    if "=" in comp or "=" in destino or ";" in t:
        raise ErrorEnsamblado(f"línea {num}: '{t}' parece de la sintaxis vieja. "
                              "Ahora es OPERACION => DESTINO CONDICION, ej. M+B => M >0")
    if not comp:
        comp = "0"
    if comp not in COMP:
        if "A" in comp and "M" in comp:
            raise ErrorEnsamblado(f"línea {num}: A y M no pueden ir juntos en la ALU")
        if "B" in comp and "N" in comp:
            raise ErrorEnsamblado(f"línea {num}: B y N no pueden ir juntos en la ALU")
        if sistema.buscar(comp):
            raise ErrorEnsamblado(f"línea {num}: {comp} va sola, sin => ni condición")
        raise ErrorEnsamblado(f"línea {num}: la operación '{comp}' no existe (escribe: ops)")
    op, bx, by = COMP[comp]
    bits_d = 0
    for letra in destino:
        if letra not in DESTINOS:
            raise ErrorEnsamblado(f"línea {num}: destino '{letra}' no existe, solo A B C M N")
        bits_d |= 1 << DESTINOS[letra]
    if not bits_d and not cond:
        raise ErrorEnsamblado(f"línea {num}: '{t}' no guarda nada ni salta. "
                              "Si quieres no hacer nada, escribe NOP")
    return (bx << 14) | (by << 13) | (op << 8) | (bits_d << 3) | CONDICIONES[cond]


def desensamblar(ins, sistema=None):
    sistema = sistema or SISTEMA
    if ins & 0x8000:
        return f"@{ins & MAX_NUMERO}"
    op, d, j = (ins >> 8) & 0x1F, (ins >> 3) & 0x1F, ins & 0x7
    if d == 0 and j == 0:
        codigo = (ins >> 8) & 0x7F
        if codigo == 0:
            return "NOP"
        e = sistema.por_codigo.get(codigo)
        return e["texto"] if e else f"SISTEMA {codigo} (vacía)"
    bx = (ins >> 14) & 1 if usa_x(op) else 0
    by = (ins >> 13) & 1 if usa_y(op) else 0
    comp = TEXTO_COMP[(op, bx, by)]
    destino = "".join(l for l, b in DESTINOS.items() if d >> b & 1)
    if not destino and j == 7 and op == 0:
        return "jmp"
    texto = comp + (f" => {destino}" if destino else "")
    return texto + (f" {NOMBRE_CONDICION[j]}" if j else "")


def alu(x, y, s):
    sx, zx, nx, sy, zy, ny, f, no = ((s >> (7 - i)) & 1 for i in range(8))
    if sx: x = (x << 1) & MASCARA
    if zx: x = 0
    if nx: x = ~x & MASCARA
    if sy: y = (y << 1) & MASCARA
    if zy: y = 0
    if ny: y = ~y & MASCARA
    salida = (x + y) & MASCARA if f else x & y
    return ~salida & MASCARA if no else salida


def con_signo(v):
    return v - 0x10000 if v & 0x8000 else v


def se_cumple(salto, z, n, p):
    return {0: False, 1: p, 2: z, 3: z or p, 4: n, 5: not z, 6: z or n, 7: True}[salto]


class Croquetium:
    def __init__(self, programa, sistema=None):
        self.sistema = sistema or SISTEMA
        self.rom = [p for p, _ in programa]
        self.texto = [t for _, t in programa]
        self.A = self.B = self.C = self.PC = self.R = 0
        self.R_banco = self.banco = self.TECLA = 0
        self.M, self.N, self.P = [0] * TAM_RAM, [0] * TAM_RAM, [0] * TAM_RAM
        self.usadas_m, self.usadas_n, self.usadas_p = set(), set(), set()
        self.ciclos = self.ultima_escritura = 0
        self.vistos = set()
        self.escritura_vista = 0
        self.parado = False

    def bucle_final(self):
        # Si vuelve a saltar al mismo sitio sin que nada haya cambiado, ya no sale nunca.
        # Tras una escritura los estados viejos no pueden repetirse, asi que se olvidan.
        if self.ultima_escritura != self.escritura_vista:
            self.vistos.clear()
            self.escritura_vista = self.ultima_escritura
        estado = (self.PC, self.banco, self.A, self.B, self.C, self.R, self.ultima_escritura)
        if estado in self.vistos:
            return True
        self.vistos.add(estado)
        return False

    def instruccion_actual(self):
        if self.banco:
            return self.P[self.PC]
        return self.rom[self.PC] if self.PC < len(self.rom) else 0

    def texto_actual(self):
        if not self.banco and self.PC < len(self.texto):
            return self.texto[self.PC]
        return desensamblar(self.instruccion_actual(), self.sistema)

    def fuera_del_programa(self):
        return not self.banco and self.PC >= len(self.rom)

    def paso(self):
        ins, pc = self.instruccion_actual(), self.PC
        self.ciclos += 1
        if ins & 0x8000:
            self.A = ins & MAX_NUMERO
            self.PC = (pc + 1) & MASCARA
            return {"pc": pc, "salida": self.A, "flags": "", "salta": False}
        bx, by = (ins >> 14) & 1, (ins >> 13) & 1
        op, d, j = (ins >> 8) & 0x1F, (ins >> 3) & 0x1F, ins & 0x7
        if d == 0 and j == 0:
            return self.paso_sistema(pc, (ins >> 8) & 0x7F)
        x = pc if op == OP_PC else (self.M[self.A] if bx else self.A)
        y = self.N[self.B] if by else self.B
        salida = alu(x, y, ROM_ALU[op])
        z, n = salida == 0, bool(salida & 0x8000)
        p = not z and not n
        salta = se_cumple(j, z, n, p)
        a_viejo, b_viejo, c_viejo = self.A, self.B, self.C
        if d & 0b11000:
            self.ultima_escritura = self.ciclos
        if d & 0b01000:
            self.M[a_viejo] = salida
            self.usadas_m.add(a_viejo)
        if d & 0b10000:
            self.N[b_viejo] = salida
            self.usadas_n.add(b_viejo)
        if d & 0b00001: self.A = salida
        if d & 0b00010: self.B = salida
        if d & 0b00100: self.C = salida
        self.PC = c_viejo if salta else (pc + 1) & MASCARA
        return {"pc": pc, "salida": salida, "flags": "Z" if z else "N" if n else "P", "salta": salta}

    def paso_sistema(self, pc, codigo):
        mascara = self.sistema.mascara(codigo)
        activo = {c["nombre"] for c in self.sistema.cables
                  if mascara >> self.sistema.bit_cable[c["nombre"]] & 1}
        banco_viejo = self.banco
        nuevo_pc, nuevo_banco, salta = (pc + 1) & MASCARA, banco_viejo, False
        if "SALTO_C" in activo: nuevo_pc, salta = self.C, True
        if "SALTO_R" in activo: nuevo_pc, nuevo_banco, salta = self.R, self.R_banco, True
        if "BANCO_RAM" in activo: nuevo_banco = 1
        if "BANCO_ROM" in activo: nuevo_banco = 0
        if "GUARDA_R" in activo: self.R, self.R_banco = (pc + 1) & MASCARA, banco_viejo
        if "GRABA_PROG" in activo and banco_viejo == 0:
            self.P[self.B] = self.M[self.A]
            self.usadas_p.add(self.B)
            self.ultima_escritura = self.ciclos
        if "A_MITAD" in activo: self.A = (self.A >> 1) | (self.A & 0x8000)
        if "A_TECLA" in activo:
            self.A, self.TECLA = self.TECLA, 0
            # Leer el teclado cuenta como cambio: un bucle que espera una tecla no es un bucle final.
            self.ultima_escritura = self.ciclos
        if "PARA" in activo:
            self.parado = True
            nuevo_pc = pc
        self.PC, self.banco = nuevo_pc, nuevo_banco
        return {"pc": pc, "salida": None, "flags": "", "salta": salta}


# =====================================================================
#  TERMINAL
# =====================================================================

class C:
    on = os.environ.get("NO_COLOR") is None
    R, NEG, TEN = "\033[0m", "\033[1m", "\033[2m"
    ROJO, VERDE, AMAR = "\033[91m", "\033[92m", "\033[93m"
    AZUL, MAG, CIAN, GRIS = "\033[94m", "\033[95m", "\033[96m", "\033[90m"


def c(texto, *estilos):
    if not C.on:
        return str(texto)
    return "".join(estilos) + str(texto) + C.R


def out(*a):
    print(*a, flush=True)


def error(msg):
    out(c(" ✗ " + msg, C.ROJO))


def ok(msg):
    out(c(" ✓ ", C.VERDE) + msg)


def carpeta_programas():
    for base in (Path(__file__).resolve().parent, Path.cwd()):
        d = base / "programas"
        try:
            d.mkdir(exist_ok=True)
            prueba = d / ".prueba"
            prueba.write_text("x")
            prueba.unlink()
            return d
        except Exception:
            continue
    return None


DEMO = """// demo: cuenta atras de 5 a 0 en la variable cuenta
@5
A => B          // B = 5
@cuenta
B => M          // cuenta = 5
@BUCLE
A => C          // C = adonde salta
(BUCLE)
@cuenta
M-1 => M >0     // resta 1 y si sigue > 0 vuelve a BUCLE
PARA
"""

VACIO = "// programa nuevo\n"


class Sesion:
    def __init__(self):
        self.carpeta = carpeta_programas()
        self.nombre = None
        self.lineas = []
        self.programa = []
        self.etiquetas = {}
        self.variables = {}
        self.linea_de = []       # instruccion -> numero de linea del texto
        self.maquina = None
        self.traza = True
        self.cambios = False
        if self.carpeta and not any(self.carpeta.glob("*.cro")):
            try:
                (self.carpeta / "demo.cro").write_text(DEMO, encoding="utf-8")
            except Exception:
                pass

    # ---------- programa ----------
    def ruta(self, nombre):
        if not nombre.endswith(".cro"):
            nombre += ".cro"
        return self.carpeta / nombre if self.carpeta else Path(nombre)

    def ensamblar(self, avisar=True):
        fuente = "\n".join(self.lineas)
        try:
            self.programa, self.etiquetas, self.variables = ensamblar(fuente)
        except ErrorEnsamblado as e:
            self.maquina = None
            error(str(e))
            return False
        self.linea_de = []
        for num, linea in enumerate(self.lineas, 1):
            t = limpiar(linea)
            if t and not (t.startswith("(") and t.endswith(")")):
                self.linea_de.append(num)
        self.maquina = Croquetium(self.programa)
        if avisar:
            extra = ""
            if self.variables:
                extra = "  " + c(" ".join(f"{k}={v}" for k, v in self.variables.items()), C.MAG)
            ok(f"{len(self.programa)} instrucciones" + extra)
        return True

    def necesita_maquina(self):
        if self.maquina is None:
            if not self.lineas:
                error("no hay programa. Usa: abre demo")
                return False
            return self.ensamblar()
        return True


# ---------- dibujo ----------

def ver_codigo(s, desde=1, hasta=None):
    if not s.lineas:
        out(c(" (vacío)", C.GRIS))
        return
    pc_linea = None
    m = s.maquina
    if m and not m.banco and m.PC < len(s.linea_de):
        pc_linea = s.linea_de[m.PC]
    hasta = hasta or len(s.lineas)
    ancho = len(str(len(s.lineas)))
    for num in range(desde, min(hasta, len(s.lineas)) + 1):
        linea = s.lineas[num - 1]
        marca = c("▶", C.AMAR, C.NEG) if num == pc_linea else " "
        out(f"{marca}{c(str(num).rjust(ancho), C.GRIS)} {colorear(linea)}")


def colorear(linea):
    if not C.on:
        return linea
    codigo, sep, coment = linea.partition("//")
    t = codigo.strip()
    if t.startswith("(") and t.endswith(")"):
        cuerpo = c(codigo, C.MAG, C.NEG)
    elif t.startswith("@"):
        cuerpo = c(codigo, C.CIAN)
    elif SISTEMA.buscar(t) or t.upper() == "NOP":
        cuerpo = c(codigo, C.ROJO, C.NEG)
    elif "=>" in codigo:
        op, _, dest = codigo.partition("=>")
        cuerpo = c(op, C.AMAR) + c("=>", C.GRIS) + c(dest, C.VERDE)
    else:
        cuerpo = c(codigo, C.AMAR)
    return cuerpo + (c(sep + coment, C.GRIS) if sep else "")


def linea_paso(s, ciclo, pc, texto, r):
    m = s.maquina
    salida = "" if r["salida"] is None else str(con_signo(r["salida"]))
    flag = r["flags"]
    color_flag = {"Z": C.AZUL, "N": C.ROJO, "P": C.VERDE}.get(flag, C.GRIS)
    salto = c(f"↷{m.PC}", C.MAG, C.NEG) if r["salta"] else ""
    out(f"{c(str(ciclo).rjust(3), C.GRIS)} {c(str(pc).rjust(3), C.AMAR)} "
        f"{texto[:13]:<13} {c(str(con_signo(m.A)).rjust(6), C.VERDE)}"
        f"{c(str(con_signo(m.B)).rjust(6), C.CIAN)}{salida.rjust(6)} {c(flag, color_flag, C.NEG)}{salto}")


def cabecera_paso():
    out(c("  #  pc instrucción        A     B   ALU F", C.GRIS))


def estado(s):
    m = s.maquina
    if not m:
        error("no hay máquina (ensambla primero)")
        return
    banco = c("RAM", C.MAG) if m.banco else c("ROM", C.CIAN)
    fin = c(" PARADA", C.ROJO, C.NEG) if m.parado else ""
    out(c(" ┌─ CPU ───────────────────────", C.AZUL))
    out(f" │ PC {c(m.PC, C.AMAR, C.NEG):<5} {banco}  ciclos {m.ciclos}{fin}")
    out(f" │ A {c(con_signo(m.A), C.VERDE, C.NEG)}   B {c(con_signo(m.B), C.VERDE, C.NEG)}"
        f"   C {c(m.C, C.VERDE, C.NEG)}")
    out(f" │ R {m.R}   TECLA {m.TECLA}")
    out(f" │ M[A] {con_signo(m.M[m.A])}   N[B] {con_signo(m.N[m.B])}")
    if m.fuera_del_programa():
        sig = c("(fin del programa)", C.GRIS)
    else:
        sig = colorear(m.texto_actual())
    out(f" │ ▶ {sig}")
    out(c(" └─────────────────────────────", C.AZUL))


def ver_ram(s, letra, args):
    m = s.maquina
    if not m:
        error("no hay máquina")
        return
    ram = m.M if letra == "M" else m.N
    puntero = m.A if letra == "M" else m.B
    try:
        if args:
            ini = resolver(s, args[0])
        else:
            ini = max(0, puntero - 3)
        cuantas = int(args[1]) if len(args) > 1 else 8
    except ValueError as e:
        error(str(e))
        return
    nombres = {v: k for k, v in s.variables.items()} if letra == "M" else {}
    for d in range(ini, min(ini + cuantas, TAM_RAM)):
        marca = c("◀ " + ("A" if letra == "M" else "B"), C.AMAR, C.NEG) if d == puntero else ""
        nombre = c(nombres.get(d, "")[:8].ljust(8), C.MAG)
        v = ram[d]
        valor = c(str(con_signo(v)).rjust(6), C.VERDE if v else C.GRIS)
        out(f" {letra}[{c(str(d).rjust(5), C.CIAN)}] {nombre} {valor} {c(f'{v:04X}', C.GRIS)} {marca}")


def resolver(s, texto):
    if texto in s.variables:
        return s.variables[texto]
    if texto in s.etiquetas:
        return s.etiquetas[texto]
    v = leer_numero(texto)
    if v is None:
        raise ValueError(f"'{texto}' no es un número ni una variable")
    return v


COLORES_PIXEL = ["\033[97m", "\033[92m", "\033[96m", "\033[93m", "\033[95m", "\033[91m", "\033[94m"]


def rejilla(s, args):
    m = s.maquina
    if not m:
        error("no hay máquina")
        return
    if len(args) < 3:
        error("uso: rejilla <dirección|variable> <ancho> <alto>   ej: rejilla 100 10 10")
        return
    try:
        base, ancho, alto = resolver(s, args[0]), int(args[1]), int(args[2])
    except ValueError as e:
        error(str(e))
        return
    ram = m.N if len(args) > 3 and args[3].upper() == "N" else m.M
    out(c("    " + "".join(str(x % 10) + " " for x in range(ancho)), C.GRIS))
    for y in range(alto):
        fila = c(str(y).rjust(3) + " ", C.GRIS)
        for x in range(ancho):
            d = base + y * ancho + x
            v = ram[d] if d < TAM_RAM else 0
            if v == 0:
                fila += c("· ", C.GRIS)
            else:
                col = COLORES_PIXEL[(v - 1) % len(COLORES_PIXEL)] if C.on else ""
                fila += (col + "██" + C.R) if C.on else "##"
        out(fila)
    out(c(f"    casilla (x,y) = {base} + y*{ancho} + x", C.GRIS))


def ver_hex(s):
    if not s.necesita_maquina():
        return
    for i, (p, t) in enumerate(s.programa):
        out(f" {c(str(i).rjust(3), C.AMAR)} {c(f'{p:04X}', C.CIAN)} {c(f'{p:016b}', C.GRIS)} {t}")


def ver_ops():
    filas = []
    for op, pl, _ in OPERACIONES:
        formas = [t for t, _, _ in formas_de(pl) if COMP[t][0] == op]
        filas.append((op, " ".join(formas)))
    for op, formas in filas:
        out(f" {c(f'{op:02X}', C.CIAN)} {formas}")
    out(c(" Sistema:", C.ROJO, C.NEG) + " " + ", ".join(i["texto"] for i in SISTEMA.instrucciones))


SINTAXIS = [
    ("@20", "A = 20 (0..32767, vale 0x14 o 0b10100)"),
    ("@vidas", "A = dirección de la variable (desde la 16)"),
    ("@BUCLE", "A = dirección de la etiqueta"),
    ("(BUCLE)", "marca la siguiente línea, no ocupa"),
    ("M+B => M", "calcula y guarda"),
    ("M-1 => AM >0", "guarda y salta a C si se cumple"),
    ("M-B <=0", "calcula y salta, sin guardar"),
    ("jmp", "salta a C siempre"),
    ("NOP / PARA", "no hace nada / para la máquina"),
    ("// hola", "comentario"),
]

TRAMPAS = [
    "Un número solo entra por A, y A es la dirección de M: para guardarlo pasa por B.",
    "M+1 => AM escribe M en la dirección de la A de antes.",
    "Para saltar, C ya tiene que tener la dirección.",
    "@algo machaca A.",
    "Negativos: @5 y luego -A => A.",
    "Sin acarreo: 32767 + 1 da -32768 sin avisar.",
    "M =0 es saltar si M vale 0. Guardar un 0 es 0 => M.",
    "Condiciones: >0 =0 >=0 <0 !=0 <=0",
]


def ver_sintaxis():
    for forma, que in SINTAXIS:
        out(f" {colorear(forma.ljust(13))} {c(que, C.GRIS)}")
    out(c(" Trampas:", C.ROJO, C.NEG))
    for i, t in enumerate(TRAMPAS, 1):
        out(f" {c(i, C.AMAR)}. {t}")


AYUDA = [
    ("Programas", [
        ("ls", "lista los .cro"),
        ("abre nombre", "carga un programa"),
        ("nuevo nombre", "programa vacío"),
        ("guarda [nombre]", "guarda en .cro"),
    ]),
    ("Editar", [
        ("ver [desde] [hasta]", "enseña el código"),
        ("escribe", "añade líneas al final (. para acabar)"),
        ("linea n texto", "cambia la línea n"),
        ("mete n texto", "inserta antes de la línea n"),
        ("borra n [hasta]", "borra líneas"),
    ]),
    ("Ejecutar", [
        ("corre [ciclos]", "ejecuta hasta parar"),
        ("p [n]", "avanza n pasos (por defecto 1)"),
        ("reset", "vuelve a empezar"),
        ("traza", "enciende/apaga la traza de corre"),
        ("tecla n", "pone la tecla pulsada"),
    ]),
    ("Mirar", [
        ("e", "estado de la CPU"),
        ("m [dir] [n]", "RAM M (por defecto alrededor de A)"),
        ("n [dir] [n]", "RAM N (alrededor de B)"),
        ("vars", "variables y lo que valen"),
        ("rejilla dir ancho alto", "trozo de M como píxeles"),
        ("hex", "código máquina"),
    ]),
    ("Chuleta", [
        ("sintaxis", "cómo se escribe + trampas"),
        ("ops", "las 32 operaciones"),
        ("color", "colores sí/no"),
        ("salir", ""),
    ]),
]


def ayuda():
    for grupo, cmds in AYUDA:
        out(c(f" ── {grupo} ", C.AZUL, C.NEG))
        for cmd, que in cmds:
            out(f"  {c(cmd, C.AMAR)}  {c(que, C.GRIS)}")


def banner():
    out(c(" ╔═══════════════════════════╗", C.MAG))
    out(c(" ║", C.MAG) + c("  C R O Q U E T I U M  16  ", C.AMAR, C.NEG) + c("║", C.MAG))
    out(c(" ╚═══════════════════════════╝", C.MAG))
    out(c(" CPU 16 bits TTL · emulador", C.GRIS))
    out(c(f" sistema: {ORIGEN_SISTEMA}", C.GRIS))
    out(f" escribe {c('ayuda', C.AMAR)} · prueba {c('abre demo', C.AMAR)}")


# ---------- ejecutar ----------

def correr(s, max_ciclos):
    m = s.maquina
    inicio = m.ciclos
    if s.traza:
        cabecera_paso()
    callado = 0
    while m.ciclos - inicio < max_ciclos:
        if m.fuera_del_programa():
            return "se acabó el programa"
        if m.parado:
            return "ya estaba parada (reset)"
        pc, texto = m.PC, m.texto_actual()
        r = m.paso()
        if s.traza and m.ciclos - inicio <= 200:
            linea_paso(s, m.ciclos, pc, texto, r)
        elif s.traza:
            callado += 1
        if m.parado:
            fin = f"PARA en {pc}"
            break
        if r["salta"] and m.bucle_final():
            fin = f"bucle final en {m.PC}"
            break
    else:
        fin = f"límite de {max_ciclos} ciclos (¿bucle infinito?)"
    if callado:
        out(c(f" ... {callado} pasos más sin enseñar", C.GRIS))
    return fin


def pasos(s, n):
    m = s.maquina
    cabecera_paso()
    for _ in range(n):
        if m.fuera_del_programa():
            out(c(" fin del programa", C.GRIS))
            return
        if m.parado:
            out(c(" máquina parada (reset)", C.ROJO))
            return
        pc, texto = m.PC, m.texto_actual()
        r = m.paso()
        linea_paso(s, m.ciclos, pc, texto, r)


def ver_vars(s):
    if not s.variables:
        out(c(" (sin variables)", C.GRIS))
        return
    m = s.maquina
    for nombre, d in s.variables.items():
        v = m.M[d] if m else 0
        out(f" {c(nombre.ljust(10), C.MAG)} M[{d}] = {c(con_signo(v), C.VERDE, C.NEG)}")


def escribir(s):
    out(c(" escribe líneas; una línea con solo . para acabar", C.GRIS))
    nuevas = []
    while True:
        try:
            linea = input(c(f" {len(s.lineas) + len(nuevas) + 1:>3}│ ", C.GRIS))
        except EOFError:
            break
        if linea.strip() == ".":
            break
        nuevas.append(linea)
    if nuevas:
        s.lineas += nuevas
        s.cambios = True
        s.ensamblar()


def numero(texto, s):
    n = int(texto)
    if not 1 <= n <= len(s.lineas) + 1:
        raise ValueError(f"no hay línea {n}")
    return n


def comando(s, linea):
    partes = linea.strip().split()
    if not partes:
        return True
    cmd, args = partes[0].lower(), partes[1:]
    resto = linea.strip()[len(partes[0]):].strip()

    if cmd in ("salir", "exit", "q"):
        if s.cambios:
            out(c(" hay cambios sin guardar; escribe salir otra vez o guarda", C.AMAR))
            s.cambios = False
            return True
        return False
    elif cmd in ("ayuda", "help", "?"):
        ayuda()
    elif cmd == "ls":
        if not s.carpeta:
            error("no encuentro carpeta donde guardar")
        else:
            archivos = sorted(s.carpeta.glob("*.cro"))
            out(c(f" {s.carpeta}", C.GRIS))
            for a in archivos:
                out("  " + c(a.stem, C.CIAN))
            if not archivos:
                out(c("  (nada)", C.GRIS))
    elif cmd == "abre":
        if not args:
            error("uso: abre nombre")
            return True
        ruta = s.ruta(args[0])
        if not ruta.exists():
            error(f"no existe {ruta.name}")
            return True
        s.nombre = ruta.stem
        s.lineas = ruta.read_text(encoding="utf-8").splitlines()
        s.cambios = False
        out(c(f" ── {s.nombre}.cro ──", C.AZUL, C.NEG))
        ver_codigo(s)
        s.ensamblar()
    elif cmd == "nuevo":
        if not args:
            error("uso: nuevo nombre")
            return True
        s.nombre = args[0].removesuffix(".cro")
        s.lineas = VACIO.splitlines()
        s.maquina = None
        s.cambios = True
        ok(f"{s.nombre}.cro nuevo. Usa escribe")
    elif cmd == "guarda":
        if args:
            s.nombre = args[0].removesuffix(".cro")
        if not s.nombre:
            error("uso: guarda nombre")
            return True
        try:
            s.ruta(s.nombre).write_text("\n".join(s.lineas) + "\n", encoding="utf-8")
            s.cambios = False
            ok(f"guardado {s.ruta(s.nombre)}")
        except Exception as e:
            error(f"no se pudo guardar: {e}")
    elif cmd == "ver":
        try:
            desde = int(args[0]) if args else 1
            hasta = int(args[1]) if len(args) > 1 else None
        except ValueError:
            error("uso: ver [desde] [hasta]")
            return True
        ver_codigo(s, desde, hasta)
    elif cmd == "escribe":
        escribir(s)
    elif cmd in ("linea", "línea", "mete"):
        try:
            n = numero(args[0], s)
            texto = resto[len(args[0]):].strip()
        except (IndexError, ValueError) as e:
            error(f"uso: {cmd} n texto ({e})")
            return True
        if cmd == "mete":
            s.lineas.insert(n - 1, texto)
        elif n == len(s.lineas) + 1:
            s.lineas.append(texto)
        else:
            s.lineas[n - 1] = texto
        s.cambios = True
        ver_codigo(s, max(1, n - 1), n + 1)
        s.ensamblar()
    elif cmd == "borra":
        try:
            a = numero(args[0], s)
            b = numero(args[1], s) if len(args) > 1 else a
        except (IndexError, ValueError) as e:
            error(f"uso: borra n [hasta] ({e})")
            return True
        del s.lineas[a - 1:b]
        s.cambios = True
        ok(f"borradas {b - a + 1}")
        s.ensamblar()
    elif cmd in ("ensambla", "asm"):
        s.ensamblar()
    elif cmd == "corre":
        if s.necesita_maquina():
            try:
                maximo = int(args[0]) if args else 100_000
            except ValueError:
                maximo = 100_000
            fin = correr(s, maximo)
            out(c(f" ■ {fin}", C.AMAR, C.NEG))
            estado(s)
            ver_vars(s)
    elif cmd in ("p", "paso"):
        if s.necesita_maquina():
            try:
                pasos(s, int(args[0]) if args else 1)
            except ValueError:
                error("uso: p [n]")
    elif cmd == "reset":
        if s.lineas and s.ensamblar(avisar=False):
            ok("reset: todo a 0")
    elif cmd == "traza":
        s.traza = not s.traza
        ok("traza " + ("encendida" if s.traza else "apagada"))
    elif cmd == "tecla":
        if s.necesita_maquina():
            try:
                s.maquina.TECLA = int(args[0], 0) & MASCARA
                ok(f"TECLA = {s.maquina.TECLA}")
            except (IndexError, ValueError):
                error("uso: tecla número")
    elif cmd in ("e", "estado"):
        if s.necesita_maquina():
            estado(s)
    elif cmd in ("m", "n"):
        if s.necesita_maquina():
            ver_ram(s, cmd.upper(), args)
    elif cmd == "vars":
        ver_vars(s)
    elif cmd == "rejilla":
        if s.necesita_maquina():
            rejilla(s, args)
    elif cmd == "hex":
        ver_hex(s)
    elif cmd == "ops":
        ver_ops()
    elif cmd == "sintaxis":
        ver_sintaxis()
    elif cmd == "color":
        C.on = not C.on
        ok("colores " + ("sí" if C.on else "no"))
    else:
        error(f"no conozco '{cmd}'. Escribe ayuda")
    return True


def main():
    s = Sesion()
    banner()
    while True:
        nombre = s.nombre or "-"
        try:
            linea = input(c(f"\n{nombre}", C.CIAN) + c(" ❯ ", C.MAG, C.NEG))
        except (EOFError, KeyboardInterrupt):
            out()
            break
        try:
            if not comando(s, linea):
                break
        except Exception as e:  # que un fallo no tire la terminal
            error(f"fallo interno: {e}")
    out(c(" hasta luego", C.GRIS))


if __name__ == "__main__":
    main()
