import argparse
import json
import sys
from pathlib import Path

# Tabla de la ALU sacada de la hoja "Operation".
# Cada byte son las 8 señales en este orden: SX ZX NX SY ZY NY F NO
# 08, 0A, 0C y 0E dividen el resultado entre 2 (antes eran !2x/PC+1, !2y, -2x y -2y).
# La ROM da la operacion de base y una puerta (O3 y no O4 y no O0) enciende el desplazador.
OPERACIONES = [
    (0x00, "0", 0x4A),
    (0x01, "1", 0x6F),
    (0x02, "-1", 0x6A),
    (0x03, "x", 0x0C),
    (0x04, "2x", 0x8C),
    (0x05, "y", 0x60),
    (0x06, "2y", 0x70),
    (0x07, "!x", 0x0D),
    (0x08, "x/2", 0x0C),
    (0x09, "!y", 0x61),
    (0x0A, "y/2", 0x60),
    (0x0B, "-x", 0x0F),
    (0x0C, "(x+y)/2", 0x02),
    (0x0D, "-y", 0x63),
    (0x0E, "(x-y)/2", 0x23),
    (0x0F, "x+1", 0x2F),
    (0x10, "y+1", 0x67),
    (0x11, "x-1", 0x0E),
    (0x12, "y-1", 0x62),
    (0x13, "x+y", 0x02),
    (0x14, "2x+y", 0x82),
    (0x15, "x+2y", 0x12),
    (0x16, "2x+2y", 0x92),
    (0x17, "x-y", 0x23),
    (0x18, "2x-y", 0xA3),
    (0x19, "x-2y", 0x33),
    (0x1A, "2x-2y", 0xB3),
    (0x1B, "y-x", 0x07),
    (0x1C, "y-2x", 0x87),
    (0x1D, "2y-x", 0x17),
    (0x1E, "x&y", 0x00),
    (0x1F, "x|y", 0x25),
]
SENALES_ALU = ["SX", "ZX", "NX", "SY", "ZY", "NY", "F", "NO"]

ROM_ALU = {op: rom for op, _, rom in OPERACIONES}
MITADES = {op for op in ROM_ALU if op & 0b11001 == 0b01000}

CONMUTATIVAS = {
    "x+y": "y+x",
    "(x+y)/2": "(y+x)/2",
    "2x+y": "y+2x",
    "x+2y": "2y+x",
    "2x+2y": "2y+2x",
    "x&y": "y&x",
    "x|y": "y|x",
}

DESTINOS = {"A": 0, "B": 1, "C": 2, "M": 3, "N": 4}

CONDICIONES = {
    "": 0, ">0": 1, "=0": 2, ">=0": 3,
    "<0": 4, "!=0": 5, "<=0": 6, "jmp": 7,
}
NOMBRE_CONDICION = {v: k for k, v in CONDICIONES.items()}
# Las largas primero: si no, ">=0" se leeria como "=0".
ORDEN_CONDICIONES = [">=0", "<=0", "!=0", ">0", "<0", "=0", "jmp"]
QUE_SALTA = ["nunca", "> 0", "= 0", ">= 0", "< 0", "!= 0", "<= 0", "siempre"]

PRIMERA_VARIABLE = 16
NIVELES_PILA_R = 16
MAX_NUMERO = 0x7FFF
MASCARA = 0xFFFF
TAM_RAM = 0x10000

RUTA_SISTEMA = Path(__file__).with_name("sistema.json")

SISTEMA_POR_DEFECTO = {
    "cables": [
        {"nombre": "PARA", "que_hace": "para el reloj"},
        {"nombre": "SALTO_C", "que_hace": "el PC carga C"},
        {"nombre": "SALTO_R", "que_hace": "el PC y el banco cargan la cima de la pila R y la desapilan"},
        {"nombre": "GUARDA_R", "que_hace": "apila en R el PC+1 y el banco actual"},
        {"nombre": "BANCO_RAM", "que_hace": "las instrucciones salen de la RAM de programas"},
        {"nombre": "BANCO_ROM", "que_hace": "las instrucciones salen de la ROM"},
        {"nombre": "GRABA_PROG", "que_hace": "RAM de programas[B] = M[A], solo con banco ROM"},
        {"nombre": "GUARDA_C", "que_hace": "C guarda PC+1"},
        {"nombre": "A_TECLA", "que_hace": "A = tecla pulsada, y la tecla se borra"},
        {"nombre": "SI_CARRY", "que_hace": "el PC carga C si el carry vale 1"},
        {"nombre": "SI_NO_CARRY", "que_hace": "el PC carga C si el carry vale 0"},
        {"nombre": "ROTAR_SI", "que_hace": "enciende el modo rotar"},
        {"nombre": "ROTAR_NO", "que_hace": "apaga el modo rotar"},
        {"nombre": "ENCADENAR_SI", "que_hace": "enciende el modo encadenar"},
        {"nombre": "ENCADENAR_NO", "que_hace": "apaga el modo encadenar"},
        {"nombre": "A_R", "que_hace": "A carga la cima de la pila R y la desapila"},
    ],
    "instrucciones": [
        {"codigo": 1, "texto": "PARA", "cables": ["PARA"],
         "que_hace": "para la máquina"},
        {"codigo": 2, "texto": "LANZA", "cables": ["GUARDA_R", "BANCO_RAM", "SALTO_C"],
         "que_hace": "salta a C dentro de la RAM de programas y guarda la vuelta en R"},
        {"codigo": 3, "texto": "VUELVE", "cables": ["GUARDA_R", "BANCO_ROM", "SALTO_C"],
         "que_hace": "salta a C dentro de la ROM y guarda la vuelta en R"},
        {"codigo": 4, "texto": "RETORNA", "cables": ["SALTO_R"],
         "que_hace": "vuelve a donde dice R, en su banco"},
        {"codigo": 5, "texto": "GRABA", "cables": ["GRABA_PROG"],
         "que_hace": "copia M[A] en la RAM de programas, en la dirección B"},
        {"codigo": 6, "texto": "PC+1 => C", "cables": ["GUARDA_C"],
         "que_hace": "guarda en C la dirección de la siguiente línea (inicio de bucle)"},
        {"codigo": 7, "texto": "TECLA => A", "cables": ["A_TECLA"],
         "que_hace": "lee la tecla pulsada (0 si no hay)"},
        {"codigo": 8, "texto": "SI CARRY", "cables": ["SI_CARRY"],
         "que_hace": "salta a C si la última operación de la ALU dio carry"},
        {"codigo": 9, "texto": "SI NO CARRY", "cables": ["SI_NO_CARRY"],
         "que_hace": "salta a C si la última operación de la ALU no dio carry"},
        {"codigo": 10, "texto": "ROTAR", "cables": ["ROTAR_SI"],
         "que_hace": "al desplazar, el bit que sale entra por el otro lado"},
        {"codigo": 11, "texto": "NO ROTAR", "cables": ["ROTAR_NO"],
         "que_hace": "al desplazar vuelve a entrar un 0"},
        {"codigo": 12, "texto": "ENCADENAR", "cables": ["ENCADENAR_SI"],
         "que_hace": "las sumas y restas suman el carry (números de varias palabras)"},
        {"codigo": 13, "texto": "NO ENCADENAR", "cables": ["ENCADENAR_NO"],
         "que_hace": "las sumas y restas vuelven a ignorar el carry"},
        {"codigo": 14, "texto": "R => A", "cables": ["A_R"],
         "que_hace": "saca la cima de la pila R a A"},
    ],
}

# Lo que hace cada cable dentro del emulador. Un cable nuevo de sistema.json que no
# este aqui se acepta, pero no hace nada hasta que se le programe su circuito.
CABLES_CON_CIRCUITO = {c["nombre"] for c in SISTEMA_POR_DEFECTO["cables"]}


class ErrorEnsamblado(Exception):
    pass


def normalizar(texto):
    return texto.replace(" ", "").replace("\t", "")


class Sistema:
    def __init__(self, datos):
        self.cables = datos["cables"]
        self.instrucciones = sorted(datos["instrucciones"], key=lambda i: i["codigo"])
        nombres = [c["nombre"] for c in self.cables]
        self.bit_cable = {nombre: i for i, nombre in enumerate(nombres)}
        self.por_codigo = {}
        self.por_texto = {}
        for ins in self.instrucciones:
            codigo = ins["codigo"]
            texto = normalizar(ins["texto"])
            if not 1 <= codigo <= 127:
                raise ValueError(f"{ins['texto']}: el código tiene que ir de 1 a 127 (el 0 es NOP)")
            if codigo in self.por_codigo:
                raise ValueError(f"el código {codigo} está repetido")
            if texto.upper() in {normalizar(i).upper() for i in self.por_texto} or texto.upper() == "NOP":
                raise ValueError(f"'{ins['texto']}' está repetida")
            for cable in ins["cables"]:
                if cable not in self.bit_cable:
                    raise ValueError(f"{ins['texto']}: el cable {cable} no existe")
            if "BANCO_RAM" in ins["cables"] and "BANCO_ROM" in ins["cables"]:
                raise ValueError(f"{ins['texto']}: BANCO_RAM y BANCO_ROM a la vez se pelean")
            self.por_codigo[codigo] = ins
            self.por_texto[texto] = ins

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

    def chips(self):
        return max(1, (len(self.cables) + 7) // 8)

    def datos(self):
        return {"cables": self.cables, "instrucciones": self.instrucciones}


def cargar_sistema(ruta=RUTA_SISTEMA):
    ruta = Path(ruta)
    if not ruta.exists():
        ruta.write_text(json.dumps(SISTEMA_POR_DEFECTO, indent=2, ensure_ascii=False), encoding="utf-8")
    return Sistema(json.loads(ruta.read_text(encoding="utf-8")))


def guardar_sistema(sistema, ruta=RUTA_SISTEMA):
    Path(ruta).write_text(json.dumps(sistema.datos(), indent=2, ensure_ascii=False), encoding="utf-8")


SISTEMA = cargar_sistema()


def formas_de(plantilla):
    textos = [plantilla]
    if plantilla in CONMUTATIVAS:
        textos.append(CONMUTATIVAS[plantilla])
    usa_x = "x" in plantilla
    usa_y = "y" in plantilla
    formas = []
    for bit_x, X in ((0, "A"), (1, "M")):
        if not usa_x and bit_x:
            continue
        for bit_y, Y in ((0, "B"), (1, "N")):
            if not usa_y and bit_y:
                continue
            for t in textos:
                formas.append((t.replace("x", X).replace("y", Y), bit_x, bit_y))
    return formas


COMP = {}
TEXTO_COMP = {}
for _op, _plantilla, _ in OPERACIONES:
    for _texto, _bx, _by in formas_de(_plantilla):
        COMP.setdefault(_texto, (_op, _bx, _by))
        TEXTO_COMP.setdefault((_op, _bx, _by), _texto)


def usa_x(op):
    return "x" in OPERACIONES[op][1]


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
    lineas = []
    etiquetas = {}
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

    variables = {}
    programa = []
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
        raise ErrorEnsamblado(
            f"línea {num}: @{simbolo} no cabe en 15 bits (0 a {MAX_NUMERO}). "
            "Para negativos: mete el positivo y haz -A => A"
        )
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
        raise ErrorEnsamblado(
            f"línea {num}: '{t}' parece de la sintaxis vieja. "
            "Ahora va al revés: OPERACION => DESTINO CONDICION, por ejemplo M+B => M >0")
    if not comp:
        comp = "0"

    if comp not in COMP:
        if "A" in comp and "M" in comp:
            raise ErrorEnsamblado(f"línea {num}: A y M no pueden ir juntos en la ALU (el bit X elige uno)")
        if "B" in comp and "N" in comp:
            raise ErrorEnsamblado(f"línea {num}: B y N no pueden ir juntos en la ALU (el bit Y elige uno)")
        sola = sistema.buscar(comp)
        if sola:
            raise ErrorEnsamblado(f"línea {num}: {sola['texto']} va sola, sin => ni condición")
        destino_fijo = [i for i in sistema.instrucciones if "=>" in i["texto"]
                        and normalizar(i["texto"]).split("=>")[0].upper() == comp.upper()]
        if destino_fijo:
            raise ErrorEnsamblado(
                f"línea {num}: '{t}' solo se puede escribir tal cual: {destino_fijo[0]['texto']}")
        raise ErrorEnsamblado(f"línea {num}: la operación '{comp}' no existe (mira la datasheet)")
    op, bx, by = COMP[comp]

    bits_d = 0
    for letra in destino:
        if letra not in DESTINOS:
            raise ErrorEnsamblado(f"línea {num}: destino '{letra}' no existe, solo A B C M N")
        bits_d |= 1 << DESTINOS[letra]

    if not bits_d and not cond:
        raise ErrorEnsamblado(
            f"línea {num}: '{t}' no guarda nada ni salta, así que no hace nada. "
            "Esos huecos son las instrucciones de sistema; si quieres no hacer nada, escribe NOP")

    return (bx << 14) | (by << 13) | (op << 8) | (bits_d << 3) | CONDICIONES[cond]


def desensamblar(ins, sistema=None):
    sistema = sistema or SISTEMA
    if ins & 0x8000:
        return f"@{ins & MAX_NUMERO}"
    op = (ins >> 8) & 0x1F
    d = (ins >> 3) & 0x1F
    j = ins & 0x7
    if d == 0 and j == 0:
        codigo = (ins >> 8) & 0x7F
        if codigo == 0:
            return "NOP"
        encontrada = sistema.por_codigo.get(codigo)
        return encontrada["texto"] if encontrada else f"SISTEMA {codigo} (vacía)"
    bx = (ins >> 14) & 1 if usa_x(op) else 0
    by = (ins >> 13) & 1 if usa_y(op) else 0
    comp = TEXTO_COMP[(op, bx, by)]
    destino = "".join(letra for letra, bit in DESTINOS.items() if d >> bit & 1)
    if not destino and j == 7 and op == 0:
        return "jmp"
    texto = comp
    if destino:
        texto += f" => {destino}"
    if j:
        texto += f" {NOMBRE_CONDICION[j]}"
    return texto


def alu(x, y, senales, mitad=False, carry=0, rotar=False, encadenar=False):
    sx, zx, nx, sy, zy, ny, f, no = ((senales >> (7 - i)) & 1 for i in range(8))
    sale = 0
    if sx:
        sale = x >> 15
        x = ((x << 1) | (sale if rotar else 0)) & MASCARA
    if zx:
        x = 0
    if nx:
        x = ~x & MASCARA
    if sy:
        sale = y >> 15
        y = ((y << 1) | (sale if rotar else 0)) & MASCARA
    if zy:
        y = 0
    if ny:
        y = ~y & MASCARA
    bit17 = 0
    if f:
        suma = x + y + (carry if encadenar else 0)
        bit17 = suma >> 16
        salida = suma & MASCARA
    else:
        salida = x & y
    if no:
        salida = ~salida & MASCARA
    nuevo_carry = bit17 if f else sale
    if mitad:
        cae = salida & 1
        # Sin rotar entra el bit 17 de la suma: la media sale bien aunque la suma se pase.
        arriba = cae if rotar else bit17
        salida = (salida >> 1) | (arriba << 15)
        nuevo_carry = cae
    return salida, nuevo_carry


def con_signo(v):
    return v - 0x10000 if v & 0x8000 else v


def se_cumple(salto, z, n, p):
    return {
        0: False, 1: p, 2: z, 3: z or p,
        4: n, 5: not z, 6: z or n, 7: True,
    }[salto]


class Croquetium:
    def __init__(self, programa, sistema=None):
        self.sistema = sistema or SISTEMA
        self.rom = [p for p, _ in programa]
        self.texto = [t for _, t in programa]
        self.A = self.B = self.C = self.PC = 0
        # Pila R: lista de (vuelta, banco), la cima al final.
        self.pila_r = []
        self.desbordes_r = 0
        self.vacias_r = 0
        self.carry = 0
        self.rotar = 0
        self.encadenar = 0
        self.banco = 0
        self.TECLA = 0
        self.M = [0] * TAM_RAM
        self.N = [0] * TAM_RAM
        self.P = [0] * TAM_RAM
        self.usadas_m = set()
        self.usadas_n = set()
        self.usadas_p = set()
        self.ciclos = 0
        self.ultima_escritura = 0
        self.vistos = set()
        self.escritura_vista = 0
        self.parado = False

    @property
    def R(self):
        return self.pila_r[-1][0] if self.pila_r else 0

    @R.setter
    def R(self, valor):
        if self.pila_r:
            self.pila_r[-1] = (valor, self.pila_r[-1][1])
        else:
            self.pila_r.append((valor, 0))

    @property
    def R_banco(self):
        return self.pila_r[-1][1] if self.pila_r else 0

    def apilar_r(self, vuelta, banco):
        if len(self.pila_r) == NIVELES_PILA_R:
            # En el chip la pila da la vuelta y pisa la mas vieja.
            self.pila_r.pop(0)
            self.desbordes_r += 1
        self.pila_r.append((vuelta, banco))

    def desapilar_r(self):
        if not self.pila_r:
            self.vacias_r += 1
            return 0, 0
        return self.pila_r.pop()

    def bucle_final(self):
        # Si vuelve a saltar al mismo sitio sin que nada haya cambiado, ya no sale nunca.
        # Tras una escritura los estados viejos no pueden repetirse, asi que se olvidan.
        if self.ultima_escritura != self.escritura_vista:
            self.vistos.clear()
            self.escritura_vista = self.ultima_escritura
        estado = (self.PC, self.banco, self.A, self.B, self.C, tuple(self.pila_r), self.carry,
                  self.rotar, self.encadenar, self.ultima_escritura)
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
        ins = self.instruccion_actual()
        pc = self.PC
        self.ciclos += 1

        # Con el bit 15 a 1 los bits D y J estan bloqueados: solo se carga A.
        if ins & 0x8000:
            self.A = ins & MAX_NUMERO
            self.PC = (pc + 1) & MASCARA
            return {"pc": pc, "salida": self.A, "flags": "", "salta": False, "cables": None}

        bx = (ins >> 14) & 1
        by = (ins >> 13) & 1
        op = (ins >> 8) & 0x1F
        d = (ins >> 3) & 0x1F
        j = ins & 0x7

        if d == 0 and j == 0:
            return self.paso_sistema(pc, (ins >> 8) & 0x7F)

        x = self.M[self.A] if bx else self.A
        y = self.N[self.B] if by else self.B

        salida, self.carry = alu(x, y, ROM_ALU[op], op in MITADES, self.carry, self.rotar, self.encadenar)
        z = salida == 0
        n = bool(salida & 0x8000)
        p = not z and not n
        salta = se_cumple(j, z, n, p)

        # La RAM escribe en la mitad baja, antes del flanco: con A y B viejos.
        a_viejo, b_viejo, c_viejo = self.A, self.B, self.C
        if d & 0b11000:
            self.ultima_escritura = self.ciclos
        if d & 0b01000:
            self.M[a_viejo] = salida
            self.usadas_m.add(a_viejo)
        if d & 0b10000:
            self.N[b_viejo] = salida
            self.usadas_n.add(b_viejo)
        if d & 0b00001:
            self.A = salida
        if d & 0b00010:
            self.B = salida
        if d & 0b00100:
            self.C = salida

        # El PC carga la salida de C antes del flanco, o sea el C viejo.
        self.PC = c_viejo if salta else (pc + 1) & MASCARA
        flags = "Z" if z else "N" if n else "P"
        return {"pc": pc, "salida": salida, "flags": flags, "salta": salta, "cables": None}

    def paso_sistema(self, pc, codigo):
        mascara = self.sistema.mascara(codigo)
        cables = [c["nombre"] for c in self.sistema.cables if mascara >> self.sistema.bit_cable[c["nombre"]] & 1]
        activo = set(cables)

        # Todo se calcula con los valores de antes del flanco, como en el hardware.
        banco_viejo = self.banco
        nuevo_pc = (pc + 1) & MASCARA
        nuevo_banco = banco_viejo
        salta = False
        if "SALTO_C" in activo:
            nuevo_pc, salta = self.C, True
        if "SI_CARRY" in activo and self.carry:
            nuevo_pc, salta = self.C, True
        if "SI_NO_CARRY" in activo and not self.carry:
            nuevo_pc, salta = self.C, True
        if "SALTO_R" in activo:
            nuevo_pc, nuevo_banco = self.desapilar_r()
            salta = True
        if "BANCO_RAM" in activo:
            nuevo_banco = 1
        if "BANCO_ROM" in activo:
            nuevo_banco = 0
        if "GUARDA_R" in activo:
            self.apilar_r((pc + 1) & MASCARA, banco_viejo)
        if "GRABA_PROG" in activo and banco_viejo == 0:
            self.P[self.B] = self.M[self.A]
            self.usadas_p.add(self.B)
            self.ultima_escritura = self.ciclos
        if "A_R" in activo:
            self.A = self.desapilar_r()[0]
        if "ROTAR_SI" in activo:
            self.rotar = 1
        if "ROTAR_NO" in activo:
            self.rotar = 0
        if "ENCADENAR_SI" in activo:
            self.encadenar = 1
        if "ENCADENAR_NO" in activo:
            self.encadenar = 0
        if "GUARDA_C" in activo:
            self.C = (pc + 1) & MASCARA
        if "A_TECLA" in activo:
            self.A, self.TECLA = self.TECLA, 0
            # Leer el teclado cuenta como cambio: un bucle que espera una tecla no es un bucle final.
            self.ultima_escritura = self.ciclos
        if "PARA" in activo:
            self.parado = True
            nuevo_pc = pc

        self.PC = nuevo_pc
        self.banco = nuevo_banco
        return {"pc": pc, "salida": None, "flags": "", "salta": salta, "cables": cables, "codigo": codigo}

    def correr(self, max_ciclos=1_000_000, traza=False):
        if traza:
            print(f"{'ciclo':>5} {'PC':>5}  {'instruccion':<22}{'A':>7}{'B':>7}{'C':>7}{'ALU':>7} flag")
        while self.ciclos < max_ciclos:
            if self.fuera_del_programa():
                return "se acabo el programa"
            banco = "P" if self.banco else " "
            texto = self.texto_actual()
            r = self.paso()
            if traza:
                salto = f" -> {self.PC}" if r["salta"] else ""
                salida = "" if r["salida"] is None else con_signo(r["salida"])
                print(f"{self.ciclos:>5} {banco}{r['pc']:>4}  {texto[:21]:<22}"
                      f"{con_signo(self.A):>7}{con_signo(self.B):>7}{self.C:>7}"
                      f"{salida:>7} {r['flags']}{salto}")
            if self.parado:
                return f"PARA en {r['pc']}"
            if r["salta"] and self.bucle_final():
                return f"bucle final en {self.PC}"
        return f"parado tras {max_ciclos} ciclos (bucle infinito?)"

    def resumen(self, variables):
        print(f"\nA={con_signo(self.A)}  B={con_signo(self.B)}  C={self.C}  R={self.R}  "
              f"PC={self.PC}  banco={'RAM' if self.banco else 'ROM'}  carry={self.carry}  ciclos={self.ciclos}")
        nombres = {v: k for k, v in variables.items()}
        for ram, usadas, letra in ((self.M, self.usadas_m, "M"), (self.N, self.usadas_n, "N"),
                                   (self.P, self.usadas_p, "P")):
            for dir_ in sorted(usadas):
                nombre = f" ({nombres[dir_]})" if letra == "M" and dir_ in nombres else ""
                print(f"{letra}[{dir_}]{nombre} = {con_signo(ram[dir_])}")


def convertir(fuente):
    # Pasa un programa de la sintaxis vieja (M=M+1;JGT) a la nueva (M+1 => M >0).
    salida = []
    for num, linea in enumerate(fuente.splitlines(), 1):
        codigo, separador, comentario = linea.partition("//")
        t = normalizar(codigo)
        if not t or t.startswith("@") or (t.startswith("(") and t.endswith(")")):
            salida.append(linea)
            continue
        destino, comp, salto = "", t, ""
        if "=" in comp:
            destino, comp = comp.split("=", 1)
        if ";" in comp:
            comp, salto = comp.split(";", 1)
        viejos = {"": "", "JGT": ">0", "JEQ": "=0", "JGE": ">=0",
                  "JLT": "<0", "JNE": "!=0", "JLE": "<=0", "JMP": "jmp"}
        if comp == "PC+1" and destino == "C" and not salto:
            salida.append(linea.replace(codigo.strip(), "PC+1 => C", 1))
            continue
        if comp not in COMP or salto not in viejos:
            raise ErrorEnsamblado(f"línea {num}: no se entiende '{t}'")
        if not destino and not salto:
            nuevo = "NOP"
        elif not destino and salto == "JMP" and comp == "0":
            nuevo = "jmp"
        else:
            nuevo = comp + (f" => {destino}" if destino else "") + (f" {viejos[salto]}" if salto else "")
        sangria = codigo[:len(codigo) - len(codigo.lstrip())]
        if not separador:
            salida.append(sangria + nuevo)
            continue
        # Mantiene el comentario en su columna si cabe.
        ancho = len(codigo) - len(sangria)
        nuevo = nuevo.ljust(ancho) if len(nuevo) < ancho else nuevo + "  "
        salida.append(f"{sangria}{nuevo}//{comentario}")
    return "\n".join(salida) + "\n"


def guardar_binarios(programa, base):
    base.with_suffix(".bin").write_text(
        "\n".join(f"{p:016b}" for p, _ in programa) + "\n")
    base.with_suffix(".hex").write_text(
        "v2.0 raw\n" + "\n".join(f"{p:04x}" for p, _ in programa) + "\n")


def guardar_rom_alu(ruta):
    datos = " ".join(f"{rom:02x}" for _, _, rom in OPERACIONES)
    Path(ruta).write_text("v2.0 raw\n" + datos + "\n")


def guardar_rom_sistema(ruta, sistema=None):
    sistema = sistema or SISTEMA
    ancho = sistema.chips() * 2
    datos = " ".join(f"{sistema.mascara(c):0{ancho}x}" for c in range(128))
    Path(ruta).write_text("v2.0 raw\n" + datos + "\n")


def tabla(cabecera, filas):
    lineas = ["| " + " | ".join(cabecera) + " |", "|" + "|".join("---" for _ in cabecera) + "|"]
    for fila in filas:
        lineas.append("| " + " | ".join(str(c).replace("|", "\\|") for c in fila) + " |")
    return lineas


def datasheet(sistema=None):
    sistema = sistema or SISTEMA
    d = ["# Croquetium 16 - Datasheet", ""]
    d += [
        "CPU de 16 bits hecha con chips 74HC. Una instrucción por ciclo, sin microcódigo: "
        "los bits de la instrucción mandan directamente en el hardware.",
        "",
        "## 1. Qué tiene dentro",
        "",
    ]
    d += tabla(["Pieza", "Tamaño", "Para qué"], [
        ["A", "16 bits", "dato, y dirección de la RAM M"],
        ["B", "16 bits", "dato, y dirección de la RAM N y de la RAM de programas al grabar"],
        ["C", "16 bits", "adónde salta el PC"],
        ["PC", "16 bits", "instrucción que toca"],
        ["R", f"pila de {NIVELES_PILA_R} x (16 bits + 1)", "vueltas guardadas por LANZA y VUELVE, con su banco; RETORNA y R => A sacan la de arriba"],
        ["carry", "1 bit", "lo que sobró en la última operación de la ALU"],
        ["rotar", "1 bit", "modo: al desplazar, el bit que sale entra por el otro lado"],
        ["encadenar", "1 bit", "modo: las sumas y restas suman también el carry"],
        ["banco", "1 bit", "0: instrucciones de la ROM; 1: de la RAM de programas"],
        ["TECLA", "16 bits", "última tecla pulsada (0 si no hay)"],
        ["RAM M", "64K x 16", "datos, dirección A"],
        ["RAM N", "64K x 16", "datos, dirección B"],
        ["ROM de programa", "32K x 16 o más", "el programa del sistema"],
        ["RAM de programas", "64K x 16", "programas cargados en marcha"],
        ["ROM de la ALU", "32 x 8", "traduce OOOOO a las 8 señales de la ALU"],
        ["ROM de sistema", f"128 x {sistema.chips() * 8}", "traduce el código de sistema a cables"],
    ])
    d += [
        "",
        "Flags: Z (resultado 0), N (negativo), P (positivo y no 0). Salen solos del resultado "
        "de la ALU y no se guardan: el salto mira el de la misma instrucción. No hay desbordamiento.",
        "",
        "Carry: un biestable que se actualiza en cada operación de ALU (los números y las de sistema no lo tocan). "
        "Guarda el bit 17 de las sumas y restas; en `2x` y `2y`, el bit 15 que se cae; en las de `/2`, el bit 0 "
        "que se cae; en `&`, `|` y `!`, un 0. Se mira con `SI CARRY` y `SI NO CARRY` en la instrucción siguiente.",
        "",
        "Modo rotar (`ROTAR` / `NO ROTAR`): al desplazar, el bit que sale entra por el otro lado en el mismo ciclo. "
        "Sin rotar, en `2x` entra un 0 y en las de `/2` entra el bit 17 de la suma (así `(A+B)/2` da la media "
        "aunque la suma se pase de 16 bits).",
        "",
        "Modo encadenar (`ENCADENAR` / `NO ENCADENAR`): las operaciones que pasan por el sumador suman también "
        "el carry, para números de varias palabras. Ojo: también lo suman las que usan el sumador por dentro "
        "(`0`, `1`, `-1`, `x+1`, `x-1`, `-x`...): enciéndelo solo para la suma de arriba y apágalo después.",
        "",
        "## 2. Los tres tipos de instrucción",
        "",
        "```",
        "bit:  15  14 13  12 11 10 9 8   7 6 5 4 3   2 1 0",
        "      1   n  n   n  n  n  n n   n n n n n   n n n    número: A = 15 bits",
        "      0   X  Y   O  O  O  O O   D D D D D   J J J    ALU (D o J distinto de 0)",
        "      0   s  s   s  s  s  s s   0 0 0 0 0   0 0 0    sistema: código = X Y OOOOO",
        "```",
        "",
        "Una instrucción de ALU que no guarda nada ni salta no tendría ningún efecto, así que "
        "esos 128 huecos son las instrucciones de sistema. Las detecta un 74HC688 (D y J contra 0, "
        "bit 15 en su enable). El 0x0000 es NOP.",
        "",
        "## 3. Cómo se escribe",
        "",
    ]
    d += tabla(["Forma", "Ejemplo", "Hace"], [
        ["`@número`", "`@20`", "A = 20 (0 a 32767, también `0x14` o `0b10100`)"],
        ["`@variable`", "`@vidas`", "A = dirección de vidas (desde la 16)"],
        ["`@ETIQUETA`", "`@BUCLE`", "A = dirección de la línea (BUCLE)"],
        ["`(ETIQUETA)`", "`(BUCLE)`", "marca la siguiente instrucción, no ocupa sitio"],
        ["`OPERACIÓN => DESTINO`", "`M+B => M`", "calcula y guarda"],
        ["`OPERACIÓN => DESTINO COND`", "`M-1 => AM >0`", "calcula, guarda y salta a C si se cumple"],
        ["`OPERACIÓN COND`", "`M-B <=0`", "calcula y salta si se cumple, sin guardar"],
        ["`jmp`", "`jmp`", "salta a C siempre"],
        ["`NOP`", "`NOP`", "no hace nada"],
        ["instrucción de sistema", "`LANZA`, `PC+1 => C`", "ver apartado 8"],
        ["`// texto`", "`// hola`", "comentario"],
    ])
    d += [
        "",
        "Los espacios dan igual. El destino puede llevar varias letras en cualquier orden: `M+1 => AM`.",
        "",
        "## 4. Entradas de la ALU (X e Y)",
        "",
    ]
    d += tabla(["X", "Y", "Primera", "Segunda"], [
        [0, 0, "A", "B"], [0, 1, "A", "N"], [1, 0, "M", "B"], [1, 1, "M", "N"]])
    d += [
        "",
        "M es la casilla de la RAM M a la que apunta A; N, la de la RAM N a la que apunta B. "
        "A y M nunca van juntos en una operación, ni B y N.",
        "",
        "## 5. Operaciones (OOOOO) y ROM de la ALU",
        "",
    ]
    filas = []
    for op, plantilla, rom in OPERACIONES:
        formas = [t for t, _, _ in formas_de(plantilla) if COMP[t][0] == op]
        bits = [str((rom >> (7 - i)) & 1) for i in range(8)]
        filas.append([f"{op:02X}", f"{op:05b}", f"`{plantilla}`", " ".join(f"`{f}`" for f in formas),
                      f"{rom:02X}"] + bits + ["1" if op in MITADES else "0"])
    d += tabla(["Op", "OOOOO", "Plantilla", "Se escribe", "ROM"] + SENALES_ALU + ["/2"], filas)
    d += [
        "",
        "La columna /2 no sale de la ROM: la enciende una puerta cuando O3 = 1, O4 = 0 y O0 = 0 "
        "(operaciones 08, 0A, 0C y 0E). Entonces el resultado pasa por el desplazador a la derecha "
        "de la salida (cableado movido un bit y 4 x 74HC157 para elegir), y por arriba entra un 0.",
        "",
        "## 6. Destinos (DDDDD)",
        "",
    ]
    d += tabla(["Bit", "Letra", "Guarda en"], [
        ["D0", "A", "registro A"], ["D1", "B", "registro B"], ["D2", "C", "registro C"],
        ["D3", "M", "RAM M en la dirección de la A de antes"],
        ["D4", "N", "RAM N en la dirección de la B de antes"]])
    d += ["", "## 7. Condiciones de salto (JJJ)", ""]
    d += tabla(["JJJ", "Se escribe", "Salta a C si el resultado es"],
               [[f"{v:03b}", f"`{NOMBRE_CONDICION[v]}`" if v else "(nada)", QUE_SALTA[v]] for v in range(8)])
    d += ["", "## 8. Instrucciones de sistema", ""]
    filas = []
    for ins in sistema.instrucciones:
        c = ins["codigo"]
        filas.append([c, f"{c >> 6} {c >> 5 & 1} {c & 31:05b}", f"{c << 8:04X}", f"`{ins['texto']}`",
                      ", ".join(ins["cables"]), ins.get("que_hace", "")])
    d += tabla(["Código", "X Y OOOOO", "Hex", "Se escribe", "Cables", "Hace"], filas)
    chips = "1 chip" if sistema.chips() == 1 else f"{sistema.chips()} chips"
    d += ["", "## 9. ROM de sistema: cables", "",
          f"Cada bit de salida es un cable que enciende un circuito. Ahora hay {len(sistema.cables)} "
          f"cables, o sea {chips} de 8 bits.", ""]
    filas = []
    for i, cable in enumerate(sistema.cables):
        emulado = "sí" if cable["nombre"] in CABLES_CON_CIRCUITO else "no (cable nuevo, falta su circuito)"
        filas.append([i, i // 8, cable["nombre"], cable.get("que_hace", ""), emulado])
    d += tabla(["Bit", "Chip", "Cable", "Qué hace", "En el emulador"], filas)
    d += [
        "",
        "## 10. Reglas y trampas",
        "",
        "1. Un número solo entra por A, y A es también la dirección de M: para guardar un número, pasa por B.",
        "2. `M+1 => AM`: M se escribe en la dirección de la A de antes. Igual con B y N.",
        "3. Para saltar, C ya tiene que tener la dirección. Si la misma instrucción escribe C y salta, salta al C viejo.",
        "4. `@algo` machaca A.",
        "5. Negativos: `@5` y luego `-A => A`.",
        "6. 32767 + 1 da -32768 sin avisar: el carry no mira el signo, mira el bit 17.",
        "7. La RAM real arranca con basura: inicializa lo que uses.",
        "8. Ojo con `M =0`: es saltar si M vale 0. Para guardar un 0 es `0 => M`.",
        "9. `GRABA` solo funciona ejecutando desde la ROM: un programa en la RAM de programas no puede reescribirse.",
        f"10. La pila R guarda {NIVELES_PILA_R} vueltas. Con una más se pisa la más vieja (el IDE avisa).",
        "11. `/2` mete un 0 por arriba: con negativos no da la mitad (-4/2 da 32766). En `(A+B)/2` la suma se pasa de 16 bits antes de dividir: con números grandes sale mal.",
        "",
        "## 11. Archivos",
        "",
    ]
    d += tabla(["Comando", "Escribe"], [
        ["`python croquetium.py prog.cro`", "`prog.bin` y `prog.hex` (ROM de programa, Logisim)"],
        ["`--rom-alu`", "`rom_alu.hex`"],
        ["`--rom-sistema`", "`rom_sistema.hex`"],
        ["`--datasheet`", "`DATASHEET.md`"],
        ["`--convertir viejo.cro`", "`viejo_nuevo.cro` en la sintaxis nueva"],
    ])
    return "\n".join(d) + "\n"


def main():
    parser = argparse.ArgumentParser(description="Ensamblador y emulador de Croquetium 16")
    parser.add_argument("programa", nargs="?", help="archivo .cro")
    parser.add_argument("--traza", action="store_true", help="ensena cada ciclo")
    parser.add_argument("--ciclos", type=int, default=1_000_000, help="maximo de ciclos")
    parser.add_argument("--datasheet", action="store_true", help="escribe DATASHEET.md")
    parser.add_argument("--rom-alu", action="store_true", help="escribe rom_alu.hex")
    parser.add_argument("--rom-sistema", action="store_true", help="escribe rom_sistema.hex")
    parser.add_argument("--convertir", action="store_true", help="pasa el programa a la sintaxis nueva")
    args = parser.parse_args()

    if args.datasheet:
        Path("DATASHEET.md").write_text(datasheet(), encoding="utf-8")
        print("DATASHEET.md escrito")
    if args.rom_alu:
        guardar_rom_alu("rom_alu.hex")
        print("rom_alu.hex escrito")
    if args.rom_sistema:
        guardar_rom_sistema("rom_sistema.hex")
        print("rom_sistema.hex escrito")
    if not args.programa:
        if not (args.datasheet or args.rom_alu or args.rom_sistema):
            parser.print_help()
        return

    ruta = Path(args.programa)
    if args.convertir:
        try:
            nuevo = convertir(ruta.read_text(encoding="utf-8"))
        except ErrorEnsamblado as e:
            sys.exit(f"Error: {e}")
        destino = ruta.with_name(ruta.stem + "_nuevo" + ruta.suffix)
        destino.write_text(nuevo, encoding="utf-8")
        print(f"{destino.name} escrito")
        return

    try:
        programa, etiquetas, variables = ensamblar(ruta.read_text(encoding="utf-8"))
    except ErrorEnsamblado as e:
        sys.exit(f"Error: {e}")

    guardar_binarios(programa, ruta)
    print(f"{len(programa)} instrucciones -> {ruta.with_suffix('.bin').name}, {ruta.with_suffix('.hex').name}")
    if variables:
        print("Variables: " + ", ".join(f"{k}={v}" for k, v in variables.items()))

    maquina = Croquetium(programa)
    final = maquina.correr(args.ciclos, args.traza)
    print(f"\nFin: {final}")
    maquina.resumen(variables)


if __name__ == "__main__":
    main()
