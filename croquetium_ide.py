import copy
import re
import sys
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog, ttk

import croquetium as cq

FUENTE = ("Consolas", 11)
FUENTE_GRANDE = ("Consolas", 14, "bold")
FUENTE_CHICA = ("Consolas", 8)

FONDO = "#1d1f21"
PANEL = "#26292b"
TEXTO = "#d9d5c8"
GRIS = "#6e7376"
AMBAR = "#e3a13b"
VERDE = "#93bd6b"
AZUL = "#6ea6c9"
ROJO = "#d76450"
ROSA = "#d58fae"
LINEA_ACTUAL = "#3d3622"
FILA_PUNTERO = "#2c3a28"
FILA_CAMBIADA = "#55401a"
FILA_RESALTADA = "#243746"
BIT_APAGADO = "#2e3133"

VELOCIDADES = [1, 2, 5, 10, 25, 50, 100, 500, 2000, "max"]
FILAS_RAM = 16
REGISTROS = ("A", "B", "C", "PC", "R", "TECLA")
ORIENTACIONES = ("filas", "columnas")
MAX_PALABRAS = 64

COLOR_CAMPO = {
    "15": GRIS, "X": AZUL, "Y": AZUL, "OOOOO": AMBAR,
    "DDDDD": VERDE, "JJJ": ROJO, "numero": TEXTO, "sistema": ROSA,
}

RE_CONDICION = re.compile(r"(>=0|<=0|!=0|>0|<0|=0|jmp)\s*$", re.IGNORECASE)

EJEMPLO = """// res = 6 * 7 (receta 7.17)
@7
A => B
@cont
B => M          // cont = 7
@6
A => B          // B = 6 todo el rato
@res
0 => M
PC+1 => C       // inicio del bucle
@res
M+B => M        // res = res + 6
@cont
M-1 => M >0

PARA
"""


def mapa_lineas(fuente):
    # Para cada instruccion, la linea del archivo de la que sale.
    lineas = []
    for num, linea in enumerate(fuente.splitlines(), 1):
        t = cq.limpiar(linea)
        if t and not (t.startswith("(") and t.endswith(")")):
            lineas.append(num)
    return lineas


def es_sistema(ins):
    return not ins & 0x8000 and (ins >> 3) & 0xFF == 0


def campos(ins):
    if ins & 0x8000:
        numero = ins & cq.MAX_NUMERO
        return [("15", "1", ""), ("numero", f"{numero:015b}", f"A = {numero}")]
    if es_sistema(ins):
        codigo = (ins >> 8) & 0x7F
        return [("15", "0", ""), ("sistema", f"{codigo:07b}", f"código {codigo}: {cq.desensamblar(ins)}"),
                ("DDDDD", "00000", ""), ("JJJ", "000", "")]
    bx = (ins >> 14) & 1
    by = (ins >> 13) & 1
    op = (ins >> 8) & 0x1F
    d = (ins >> 3) & 0x1F
    j = ins & 0x7
    plantilla = cq.OPERACIONES[op][1]
    if op == cq.OP_PC:
        x = "PC"
    else:
        x = ("M" if bx else "A") if cq.usa_x(op) else "-"
    y = ("N" if by else "B") if cq.usa_y(op) else "-"
    destino = "".join(letra for letra, bit in cq.DESTINOS.items() if d >> bit & 1)
    return [
        ("15", "0", ""),
        ("X", str(bx), x),
        ("Y", str(by), y),
        ("OOOOO", f"{op:05b}", plantilla),
        ("DDDDD", f"{d:05b}", destino or "-"),
        ("JJJ", f"{j:03b}", cq.NOMBRE_CONDICION[j] or "-"),
    ]


def bits_agrupados(ins):
    b = f"{ins:016b}"
    if ins & 0x8000:
        return f"{b[0]} {b[1:]}"
    if es_sistema(ins):
        return f"{b[0]} {b[1:8]} {b[8:13]} {b[13:]}"
    return f"{b[0]} {b[1]} {b[2]} {b[3:8]} {b[8:13]} {b[13:]}"


def boton(padre, texto, comando):
    return tk.Button(padre, text=texto, command=comando, font=FUENTE, bg=PANEL, fg=TEXTO,
                     activebackground="#3a3e40", activeforeground=TEXTO,
                     relief="flat", padx=10, pady=3)


def etiqueta(padre, texto, color=GRIS, **extra):
    return tk.Label(padre, text=texto, font=FUENTE, fg=color, bg=extra.pop("bg", PANEL), **extra)


def entrada(padre, variable, ancho):
    return tk.Entry(padre, textvariable=variable, width=ancho, font=FUENTE, bg=FONDO, fg=TEXTO,
                    insertbackground=TEXTO, relief="flat")


def nueva_tabla(padre, columnas, anchos, alto=12):
    marco = tk.Frame(padre, bg=PANEL)
    tabla = ttk.Treeview(marco, columns=columnas, show="headings", height=alto)
    for col, ancho in zip(columnas, anchos):
        tabla.heading(col, text=col)
        tabla.column(col, width=ancho, anchor="w", stretch=col == columnas[-1])
    barra = ttk.Scrollbar(marco, orient="vertical", command=tabla.yview)
    lateral = ttk.Scrollbar(marco, orient="horizontal", command=tabla.xview)
    tabla.configure(yscrollcommand=barra.set, xscrollcommand=lateral.set)
    barra.pack(side="right", fill="y")
    lateral.pack(side="bottom", fill="x")
    tabla.pack(side="left", fill="both", expand=True)
    tabla.tag_configure("actual", background=LINEA_ACTUAL)
    return marco, tabla


class PanelRAM:
    def __init__(self, padre, ide, letra, puntero):
        self.ide = ide
        self.letra = letra
        self.puntero = puntero
        self.modo = tk.StringVar(value="seguir")
        self.desde = tk.StringVar(value="0")
        self.texto_resaltar = tk.StringVar()
        self.resaltar = []
        self.filas = FILAS_RAM
        # Lo que se ha scrolleado en modo seguir. Dura hasta el siguiente paso.
        self.vistazo = None
        self.en_tablero = False
        self.desde_tablero = tk.StringVar(value=str(cq.PRIMERA_VARIABLE))
        self.palabras = tk.StringVar(value="16")
        self.orientacion = tk.StringVar(value=ORIENTACIONES[0])
        # Lo que valia cada palabra del tablero la ultima vez que se pinto.
        self.antes = {}

        marco = tk.Frame(padre, bg=PANEL, padx=6, pady=6)
        marco.pack(side="left", fill="both", expand=True, padx=4)
        cabecera = tk.Frame(marco, bg=PANEL)
        cabecera.pack(fill="x", pady=(0, 4))
        self.titulo = tk.Label(cabecera, text=f"RAM {letra}", font=FUENTE_GRANDE, fg=AMBAR, bg=PANEL)
        self.titulo.pack(side="left")
        self.boton_vista = boton(cabecera, "tablero", self.cambiar_vista)
        self.boton_vista.pack(side="right")

        self.ctrl_numeros = tk.Frame(cabecera, bg=PANEL)
        self.ctrl_numeros.pack(side="left")
        radio = dict(font=FUENTE, bg=PANEL, fg=TEXTO, selectcolor=FONDO,
                     activebackground=PANEL, activeforeground=TEXTO, command=self.cambiar_modo)
        tk.Radiobutton(self.ctrl_numeros, text=f"seguir {puntero}", variable=self.modo, value="seguir", **radio).pack(side="left", padx=(10, 0))
        tk.Radiobutton(self.ctrl_numeros, text="fija desde", variable=self.modo, value="fija", **radio).pack(side="left")
        caja = entrada(self.ctrl_numeros, self.desde, 6)
        caja.pack(side="left", padx=4)
        caja.bind("<Return>", self.fijar)

        self.fila_resaltar = tk.Frame(marco, bg=PANEL)
        self.fila_resaltar.pack(fill="x", pady=(0, 4))
        etiqueta(self.fila_resaltar, "resaltar").pack(side="left")
        caja = entrada(self.fila_resaltar, self.texto_resaltar, 18)
        caja.pack(side="left", padx=4)
        caja.bind("<Return>", self.poner_resaltado)
        self.aviso = etiqueta(self.fila_resaltar, "ej: 100-200, 300")
        self.aviso.pack(side="left", padx=4)

        self.ctrl_tablero = tk.Frame(marco, bg=PANEL)
        etiqueta(self.ctrl_tablero, "desde").pack(side="left")
        caja = entrada(self.ctrl_tablero, self.desde_tablero, 8)
        caja.pack(side="left", padx=(4, 8))
        caja.bind("<Return>", lambda e: ide.refrescar())
        caja.bind("<FocusOut>", lambda e: ide.refrescar())
        etiqueta(self.ctrl_tablero, "palabras").pack(side="left")
        cuantas = tk.Spinbox(self.ctrl_tablero, from_=1, to=MAX_PALABRAS, textvariable=self.palabras, width=3,
                             font=FUENTE, bg=FONDO, fg=TEXTO, buttonbackground=PANEL, insertbackground=TEXTO,
                             relief="flat", command=ide.refrescar)
        cuantas.pack(side="left", padx=4)
        cuantas.bind("<Return>", lambda e: ide.refrescar())
        etiqueta(self.ctrl_tablero, "en").pack(side="left")
        menu = tk.OptionMenu(self.ctrl_tablero, self.orientacion, *ORIENTACIONES,
                             command=lambda _v: ide.refrescar())
        menu.config(font=FUENTE, bg=PANEL, fg=TEXTO, activebackground="#3a3e40", activeforeground=TEXTO,
                    relief="flat", highlightthickness=0, padx=4)
        menu["menu"].config(font=FUENTE, bg=PANEL, fg=TEXTO, activebackground="#3a3e40")
        menu.pack(side="left")

        self.cuerpo = tk.Frame(marco, bg=PANEL)
        self.cuerpo.pack(fill="both", expand=True)
        self.lienzo = tk.Canvas(self.cuerpo, bg=FONDO, highlightthickness=0, width=300, height=FILAS_RAM * 21 + 24)
        self.lienzo.bind("<Configure>", lambda e: self.en_tablero and self.pintar_tablero())
        self.vista_numeros = tk.Frame(self.cuerpo, bg=PANEL)
        self.vista_numeros.pack(fill="both", expand=True)
        self.barra = ttk.Scrollbar(self.vista_numeros, orient="vertical", command=self.desplazar)
        self.barra.pack(side="right", fill="y")
        columnas = ("dir", "nombre", "valor", "hex")
        self.tabla = ttk.Treeview(self.vista_numeros, columns=columnas, show="headings", height=FILAS_RAM, selectmode="none")
        for col, ancho in zip(columnas, (70, 90, 75, 60)):
            self.tabla.heading(col, text=col)
            self.tabla.column(col, width=ancho, anchor="w" if col == "nombre" else "e")
        self.tabla.pack(side="left", fill="both", expand=True)
        self.tabla.tag_configure("puntero", background=FILA_PUNTERO)
        self.tabla.tag_configure("cambiada", background=FILA_CAMBIADA)
        self.tabla.tag_configure("resaltada", background=FILA_RESALTADA)
        self.tabla.tag_configure("input", foreground=AZUL)
        self.tabla.bind("<Double-1>", self.editar)
        self.tabla.bind("<Configure>", self.al_cambiar_tamano)
        self.tabla.bind("<MouseWheel>", lambda e: self.mover(-3 * e.delta // 120))
        self.tabla.bind("<Button-4>", lambda e: self.mover(-3))
        self.tabla.bind("<Button-5>", lambda e: self.mover(3))

    def cambiar_vista(self):
        self.en_tablero = not self.en_tablero
        if self.en_tablero:
            self.ctrl_numeros.pack_forget()
            self.fila_resaltar.pack_forget()
            self.vista_numeros.pack_forget()
            self.ctrl_tablero.pack(fill="x", pady=(0, 4), before=self.cuerpo)
            self.lienzo.pack(fill="both", expand=True)
            self.boton_vista.config(text="números")
        else:
            self.ctrl_tablero.pack_forget()
            self.lienzo.pack_forget()
            self.ctrl_numeros.pack(side="left", after=self.titulo)
            self.fila_resaltar.pack(fill="x", pady=(0, 4), before=self.cuerpo)
            self.vista_numeros.pack(fill="both", expand=True)
            self.boton_vista.config(text="tablero")
        self.ide.refrescar()

    def fijar(self, _evento=None):
        self.modo.set("fija")
        self.vistazo = None
        self.ide.refrescar()

    def cambiar_modo(self):
        self.vistazo = None
        self.ide.refrescar()

    def poner_resaltado(self, _evento=None):
        rangos = []
        for trozo in self.texto_resaltar.get().split(","):
            trozo = trozo.strip()
            if not trozo:
                continue
            desde, _, hasta = trozo.partition("-")
            a = cq.leer_numero(desde.strip())
            b = cq.leer_numero(hasta.strip()) if hasta else a
            if a is None or b is None:
                self.aviso.config(text=f"no entiendo '{trozo}'", fg=ROJO)
                return
            rangos.append((min(a, b), max(a, b)))
        self.resaltar = rangos
        self.aviso.config(text=f"{len(rangos)} rango(s)" if rangos else "ej: 100-200, 300", fg=GRIS)
        if rangos and self.modo.get() == "fija":
            self.desde.set(str(rangos[0][0]))
        self.ide.refrescar()

    def al_cambiar_tamano(self, evento):
        filas = max(4, (evento.height - 26) // 21)
        if filas != self.filas:
            self.filas = filas
            self.refrescar()

    def inicio_actual(self):
        if self.modo.get() == "seguir":
            if self.vistazo is not None:
                inicio = self.vistazo
            else:
                inicio = getattr(self.ide.maquina, self.puntero) - 4
        else:
            inicio = cq.leer_numero(self.desde.get()) or 0
        return max(0, min(inicio, cq.TAM_RAM - self.filas))

    def ir_a(self, inicio):
        inicio = max(0, min(inicio, cq.TAM_RAM - self.filas))
        if self.modo.get() == "seguir":
            self.vistazo = inicio
        else:
            self.desde.set(str(inicio))
        self.refrescar()

    def mover(self, filas):
        self.ir_a(self.inicio_actual() + filas)
        return "break"

    def desplazar(self, accion, cantidad, unidad=None):
        if accion == "moveto":
            self.ir_a(int(float(cantidad) * cq.TAM_RAM))
        elif unidad == "pages":
            self.mover(int(cantidad) * self.filas)
        else:
            self.mover(int(cantidad))

    def refrescar(self):
        if self.en_tablero:
            self.pintar_tablero()
            return
        maquina = self.ide.maquina
        ram = getattr(maquina, self.letra)
        apuntada = getattr(maquina, self.puntero)
        inicio = self.inicio_actual()
        if self.modo.get() == "seguir" and self.vistazo is None:
            # Asi al pasar a "fija" se queda donde estaba.
            self.desde.set(str(inicio))
        self.barra.set(inicio / cq.TAM_RAM, (inicio + self.filas) / cq.TAM_RAM)

        nombres = self.ide.nombres if self.letra == "M" else {}
        inputs = self.ide.inputs[self.letra]
        self.tabla.delete(*self.tabla.get_children())
        for dir_ in range(inicio, min(inicio + self.filas, cq.TAM_RAM)):
            valor = ram[dir_]
            marcas = []
            if dir_ == apuntada:
                marcas.append("puntero")
            if (self.letra, dir_) in self.ide.cambiadas:
                marcas.append("cambiada")
            if not marcas and any(a <= dir_ <= b for a, b in self.resaltar):
                marcas.append("resaltada")
            if dir_ in inputs:
                marcas.append("input")
            flecha = f"{self.puntero}> " if dir_ == apuntada else ""
            self.tabla.insert("", "end", iid=str(dir_), tags=marcas, values=(
                f"{flecha}{dir_}", nombres.get(dir_, ""), cq.con_signo(valor), f"{valor:04X}"))

    def inicio_tablero(self):
        texto = self.desde_tablero.get().strip()
        valor = cq.leer_numero(texto)
        if valor is None:
            # Tambien vale el nombre de una variable del programa.
            valor = {nombre: dir_ for dir_, nombre in self.ide.nombres.items()}.get(texto)
        if valor is None or not 0 <= valor < cq.TAM_RAM:
            return None
        return valor

    def pintar_tablero(self):
        lienzo = self.lienzo
        lienzo.delete("all")
        inicio = self.inicio_tablero()
        if inicio is None:
            lienzo.create_text(8, 8, anchor="nw", fill=ROJO, font=FUENTE,
                               text=f"'{self.desde_tablero.get().strip()}' no es\nuna dirección ni una variable")
            return
        cuantas = cq.leer_numero(self.palabras.get().strip()) or 16
        cuantas = max(1, min(cuantas, MAX_PALABRAS, cq.TAM_RAM - inicio))

        maquina = self.ide.maquina
        ram = getattr(maquina, self.letra)
        apuntada = getattr(maquina, self.puntero)
        en_filas = self.orientacion.get() == ORIENTACIONES[0]
        columnas, filas = (16, cuantas) if en_filas else (cuantas, 16)
        # Con palabra = columna las direcciones van giradas arriba.
        izquierda, arriba = (46, 16) if en_filas else (22, 44)
        ancho = max(lienzo.winfo_width(), 100)
        alto = max(lienzo.winfo_height(), 100)
        celda = min((ancho - izquierda - 4) // columnas, (alto - arriba - 4) // filas, 26)
        celda = max(celda, 3)
        cada = 1 if celda >= 11 else 4

        for bit in range(16):
            pos = 15 - bit
            if bit % cada:
                continue
            if en_filas:
                lienzo.create_text(izquierda + pos * celda + celda / 2, arriba - 3, anchor="s",
                                   text=str(bit), fill=GRIS, font=FUENTE_CHICA)
            else:
                lienzo.create_text(izquierda - 4, arriba + pos * celda + celda / 2, anchor="e",
                                   text=str(bit), fill=GRIS, font=FUENTE_CHICA)

        cambiadas = {dir_ for letra, dir_ in self.ide.cambiadas if letra == self.letra}
        for i in range(cuantas):
            dir_ = inicio + i
            valor = ram[dir_]
            viejo = self.antes.get(dir_, valor) if dir_ in cambiadas else valor
            if i % cada == 0:
                color = VERDE if dir_ == apuntada else GRIS
                if en_filas:
                    lienzo.create_text(izquierda - 4, arriba + i * celda + celda / 2, anchor="e",
                                       text=str(dir_), fill=color, font=FUENTE_CHICA)
                else:
                    lienzo.create_text(izquierda + i * celda + celda / 2, arriba - 3, anchor="w", angle=90,
                                       text=str(dir_), fill=color, font=FUENTE_CHICA)
            for bit in range(16):
                pos = 15 - bit
                col, fila = (pos, i) if en_filas else (i, pos)
                x = izquierda + col * celda
                y = arriba + fila * celda
                encendido = valor >> bit & 1
                if (valor ^ viejo) >> bit & 1:
                    color = AMBAR if encendido else FILA_CAMBIADA
                else:
                    color = TEXTO if encendido else BIT_APAGADO
                lienzo.create_rectangle(x, y, x + celda - 1, y + celda - 1, fill=color, outline="")
        self.antes = {inicio + i: ram[inicio + i] for i in range(cuantas)}

    def editar(self, evento):
        fila = self.tabla.identify_row(evento.y)
        if not fila:
            return
        dir_ = int(fila)
        ram = getattr(self.ide.maquina, self.letra)
        valor = self.ide.pedir_valor(f"{self.letra}[{dir_}]", ram[dir_])
        if valor is None:
            return
        ram[dir_] = valor
        self.ide.inputs[self.letra][dir_] = valor
        self.ide.maquina.vistos.clear()
        self.ide.refrescar()


class PestanaSistema:
    def __init__(self, padre, ide):
        self.ide = ide
        self.borrador = copy.deepcopy(cq.SISTEMA.datos())
        self.marcas = {}

        cuerpo = tk.Frame(padre, bg=FONDO)
        cuerpo.pack(fill="both", expand=True, padx=6, pady=6)

        etiqueta(cuerpo, "Instrucciones de sistema (bit 15 = 0, D = 0, J = 0; código = X Y OOOOO)",
                 bg=FONDO).pack(anchor="w")
        marco, self.lista = nueva_tabla(cuerpo, ("código", "se escribe", "cables", "hace"), (60, 120, 260, 300), 8)
        marco.pack(fill="both", expand=True, pady=(2, 6))
        self.lista.bind("<<TreeviewSelect>>", self.elegir)

        formulario = tk.Frame(cuerpo, bg=PANEL, padx=8, pady=8)
        formulario.pack(fill="x")
        self.codigo = tk.StringVar()
        self.texto = tk.StringVar()
        self.hace = tk.StringVar()
        fila = tk.Frame(formulario, bg=PANEL)
        fila.pack(fill="x")
        for nombre, var, ancho in (("código", self.codigo, 5), ("se escribe", self.texto, 16), ("hace", self.hace, 40)):
            etiqueta(fila, nombre).pack(side="left", padx=(0, 4))
            entrada(fila, var, ancho).pack(side="left", padx=(0, 12))
        self.casillas = tk.Frame(formulario, bg=PANEL)
        self.casillas.pack(fill="x", pady=6)
        botones = tk.Frame(formulario, bg=PANEL)
        botones.pack(fill="x")
        boton(botones, "Nueva", self.nueva).pack(side="left", padx=2)
        boton(botones, "Aplicar a la fila", self.aplicar).pack(side="left", padx=2)
        boton(botones, "Borrar fila", self.borrar).pack(side="left", padx=2)

        etiqueta(cuerpo, "Cables de la ROM de sistema (cada bit de salida enciende un circuito)",
                 bg=FONDO).pack(anchor="w", pady=(10, 0))
        marco, self.cables = nueva_tabla(cuerpo, ("bit", "cable", "hace", "emulador"), (40, 120, 360, 200), 6)
        marco.pack(fill="both", expand=True, pady=(2, 6))
        self.cables.bind("<<TreeviewSelect>>", self.elegir_cable)
        fila = tk.Frame(cuerpo, bg=PANEL, padx=8, pady=8)
        fila.pack(fill="x")
        self.nombre_cable = tk.StringVar()
        self.hace_cable = tk.StringVar()
        etiqueta(fila, "cable").pack(side="left", padx=(0, 4))
        entrada(fila, self.nombre_cable, 14).pack(side="left", padx=(0, 12))
        etiqueta(fila, "hace").pack(side="left", padx=(0, 4))
        entrada(fila, self.hace_cable, 40).pack(side="left", padx=(0, 12))
        boton(fila, "Añadir cable", self.anadir_cable).pack(side="left", padx=2)
        boton(fila, "Borrar cable", self.borrar_cable).pack(side="left", padx=2)

        abajo = tk.Frame(cuerpo, bg=FONDO)
        abajo.pack(fill="x", pady=(8, 0))
        boton(abajo, "Guardar sistema.json", self.guardar).pack(side="left", padx=2)
        boton(abajo, "Descartar cambios", self.descartar).pack(side="left", padx=2)
        self.aviso = etiqueta(abajo, "", bg=FONDO)
        self.aviso.pack(side="left", padx=10)
        self.pintar()

    def pintar(self):
        self.lista.delete(*self.lista.get_children())
        for ins in sorted(self.borrador["instrucciones"], key=lambda i: i["codigo"]):
            self.lista.insert("", "end", iid=str(ins["codigo"]), values=(
                ins["codigo"], ins["texto"], ", ".join(ins["cables"]), ins.get("que_hace", "")))
        self.cables.delete(*self.cables.get_children())
        for bit, cable in enumerate(self.borrador["cables"]):
            emulado = "sí" if cable["nombre"] in cq.CABLES_CON_CIRCUITO else "no: falta su circuito"
            self.cables.insert("", "end", iid=cable["nombre"], values=(
                bit, cable["nombre"], cable.get("que_hace", ""), emulado))
        for hijo in self.casillas.winfo_children():
            hijo.destroy()
        marcadas = {n for n, v in self.marcas.items() if v.get()}
        self.marcas = {}
        for i, cable in enumerate(self.borrador["cables"]):
            var = tk.BooleanVar(value=cable["nombre"] in marcadas)
            tk.Checkbutton(self.casillas, text=cable["nombre"], variable=var, font=FUENTE, bg=PANEL, fg=TEXTO,
                           selectcolor=FONDO, activebackground=PANEL, activeforeground=TEXTO
                           ).grid(row=i // 5, column=i % 5, sticky="w", padx=4)
            self.marcas[cable["nombre"]] = var

    def elegir(self, _evento=None):
        seleccion = self.lista.selection()
        if not seleccion:
            return
        ins = next(i for i in self.borrador["instrucciones"] if str(i["codigo"]) == seleccion[0])
        self.codigo.set(str(ins["codigo"]))
        self.texto.set(ins["texto"])
        self.hace.set(ins.get("que_hace", ""))
        for nombre, var in self.marcas.items():
            var.set(nombre in ins["cables"])

    def elegir_cable(self, _evento=None):
        seleccion = self.cables.selection()
        if seleccion:
            cable = next(c for c in self.borrador["cables"] if c["nombre"] == seleccion[0])
            self.nombre_cable.set(cable["nombre"])
            self.hace_cable.set(cable.get("que_hace", ""))

    def nueva(self):
        usados = {i["codigo"] for i in self.borrador["instrucciones"]}
        libre = next(c for c in range(1, 128) if c not in usados)
        self.codigo.set(str(libre))
        self.texto.set("")
        self.hace.set("")
        for var in self.marcas.values():
            var.set(False)
        self.lista.selection_remove(*self.lista.selection())

    def aplicar(self):
        codigo = cq.leer_numero(self.codigo.get().strip())
        if codigo is None or not self.texto.get().strip():
            self.avisar("Hace falta un código (1 a 127) y cómo se escribe", ROJO)
            return
        nueva = {"codigo": codigo, "texto": self.texto.get().strip(),
                 "cables": [n for n, v in self.marcas.items() if v.get()], "que_hace": self.hace.get().strip()}
        anterior = self.lista.selection()
        resto = [i for i in self.borrador["instrucciones"]
                 if i["codigo"] != codigo and (not anterior or str(i["codigo"]) != anterior[0])]
        self.borrador["instrucciones"] = resto + [nueva]
        self.pintar()
        self.lista.selection_set(str(codigo))
        self.avisar("Cambio sin guardar: pulsa Guardar sistema.json", AMBAR)

    def borrar(self):
        seleccion = self.lista.selection()
        if not seleccion:
            return
        self.borrador["instrucciones"] = [i for i in self.borrador["instrucciones"] if str(i["codigo"]) != seleccion[0]]
        self.pintar()
        self.avisar("Cambio sin guardar: pulsa Guardar sistema.json", AMBAR)

    def anadir_cable(self):
        nombre = self.nombre_cable.get().strip().upper().replace(" ", "_")
        if not nombre or any(c["nombre"] == nombre for c in self.borrador["cables"]):
            self.avisar("Pon un nombre de cable que no exista", ROJO)
            return
        self.borrador["cables"].append({"nombre": nombre, "que_hace": self.hace_cable.get().strip()})
        self.pintar()
        self.avisar(f"Cable {nombre} añadido. En el emulador no hará nada hasta que tenga circuito", AMBAR)

    def borrar_cable(self):
        nombre = self.nombre_cable.get().strip()
        en_uso = [i["texto"] for i in self.borrador["instrucciones"] if nombre in i["cables"]]
        if en_uso:
            self.avisar(f"{nombre} lo usan: {', '.join(en_uso)}", ROJO)
            return
        self.borrador["cables"] = [c for c in self.borrador["cables"] if c["nombre"] != nombre]
        self.pintar()

    def guardar(self):
        try:
            nuevo = cq.Sistema(copy.deepcopy(self.borrador))
        except ValueError as e:
            self.avisar(f"No se guarda: {e}", ROJO)
            return
        cq.guardar_sistema(nuevo)
        cq.SISTEMA = nuevo
        self.borrador = copy.deepcopy(nuevo.datos())
        self.pintar()
        chips = "1 chip" if nuevo.chips() == 1 else f"{nuevo.chips()} chips"
        self.avisar(f"Guardado. ROM de sistema: {chips} de 8 bits", VERDE)
        self.ide.sistema_cambiado()

    def descartar(self):
        self.borrador = copy.deepcopy(cq.SISTEMA.datos())
        self.pintar()
        self.avisar("Cambios descartados")

    def avisar(self, texto, color=GRIS):
        self.aviso.config(text=texto, fg=color)


class IDE:
    def __init__(self, raiz):
        self.raiz = raiz
        self.ruta = None
        self.sin_guardar = False
        self.pendiente = None

        self.programa = []
        self.nombres = {}
        self.linea_de = []
        self.valido = True
        self.maquina = cq.Croquetium([])
        self.inputs = {"M": {}, "N": {}, "reg": {}}

        self.corriendo = False
        self.fin = None
        self.ultimo = None
        self.cambiadas = set()
        self.regs_cambiados = set()

        self.montar_estilo()
        self.montar_menu()
        self.montar_ventana()
        self.montar_atajos()

        self.poner_texto(EJEMPLO)
        self.sin_guardar = False
        self.poner_titulo()
        self.estado("F10 paso  |  F5 correr/pausa  |  F6 reset  |  F1 datasheet  |  doble clic en un registro o casilla para cambiarlo", GRIS)
        raiz.protocol("WM_DELETE_WINDOW", self.salir)

    def montar_estilo(self):
        self.raiz.configure(bg=FONDO)
        self.raiz.geometry("1400x860")
        estilo = ttk.Style()
        estilo.theme_use("clam")
        estilo.configure("Treeview", background=FONDO, fieldbackground=FONDO, foreground=TEXTO,
                         font=FUENTE, rowheight=21, borderwidth=0)
        estilo.configure("Treeview.Heading", background=PANEL, foreground=GRIS, font=FUENTE, relief="flat")
        estilo.map("Treeview", background=[("selected", "#44484a")])
        estilo.configure("TPanedwindow", background=FONDO)
        estilo.configure("TNotebook", background=FONDO, borderwidth=0)
        estilo.configure("TNotebook.Tab", background=PANEL, foreground=GRIS, font=FUENTE, padding=(12, 4))
        estilo.map("TNotebook.Tab", background=[("selected", FONDO)], foreground=[("selected", AMBAR)])
        estilo.configure("Vertical.TScrollbar", background=PANEL, troughcolor=FONDO, borderwidth=0)

    def montar_menu(self):
        barra = tk.Menu(self.raiz)
        archivo = tk.Menu(barra, tearoff=0)
        archivo.add_command(label="Nuevo", command=self.nuevo)
        archivo.add_command(label="Abrir...  Ctrl+O", command=self.abrir)
        archivo.add_command(label="Guardar  Ctrl+S", command=self.guardar)
        archivo.add_command(label="Guardar como...", command=self.guardar_como)
        archivo.add_separator()
        archivo.add_command(label="Abrir y convertir de la sintaxis vieja...", command=self.abrir_viejo)
        archivo.add_separator()
        archivo.add_command(label="Exportar .bin y .hex del programa", command=self.exportar)
        archivo.add_command(label="Exportar rom_alu.hex y rom_sistema.hex", command=self.exportar_roms)
        archivo.add_command(label="Exportar DATASHEET.md", command=self.exportar_datasheet)
        archivo.add_separator()
        archivo.add_command(label="Salir", command=self.salir)
        barra.add_cascade(label="Archivo", menu=archivo)

        ejecutar = tk.Menu(barra, tearoff=0)
        ejecutar.add_command(label="Paso  F10", command=self.paso)
        ejecutar.add_command(label="Correr / pausa  F5", command=self.correr)
        ejecutar.add_command(label="Reset  F6", command=self.reset)
        barra.add_cascade(label="Ejecutar", menu=ejecutar)

        inputs = tk.Menu(barra, tearoff=0)
        inputs.add_command(label="Borrar inputs", command=self.borrar_inputs)
        barra.add_cascade(label="Inputs", menu=inputs)

        ayuda = tk.Menu(barra, tearoff=0)
        ayuda.add_command(label="Datasheet  F1", command=self.ver_datasheet)
        barra.add_cascade(label="Ayuda", menu=ayuda)
        self.raiz.config(menu=barra)

    def montar_ventana(self):
        herramientas = tk.Frame(self.raiz, bg=FONDO, pady=6, padx=6)
        herramientas.pack(fill="x")
        boton(herramientas, "Paso (F10)", self.paso).pack(side="left", padx=2)
        self.boton_correr = boton(herramientas, "Correr (F5)", self.correr)
        self.boton_correr.pack(side="left", padx=2)
        boton(herramientas, "Reset (F6)", self.reset).pack(side="left", padx=2)
        etiqueta(herramientas, "velocidad", bg=FONDO).pack(side="left", padx=(20, 4))
        self.velocidad = tk.IntVar(value=3)
        tk.Scale(herramientas, from_=0, to=len(VELOCIDADES) - 1, orient="horizontal", showvalue=False,
                 variable=self.velocidad, command=self.poner_velocidad, length=160,
                 bg=FONDO, troughcolor=PANEL, highlightthickness=0, sliderrelief="flat").pack(side="left")
        self.texto_velocidad = etiqueta(herramientas, "", TEXTO, bg=FONDO, width=12, anchor="w")
        self.texto_velocidad.pack(side="left", padx=4)
        self.poner_velocidad()

        self.barra_estado = tk.Label(self.raiz, font=FUENTE, bg=PANEL, fg=GRIS, anchor="w", padx=8, pady=3)
        self.barra_estado.pack(side="bottom", fill="x")

        paneles = ttk.PanedWindow(self.raiz, orient="horizontal")
        paneles.pack(fill="both", expand=True, padx=6, pady=(0, 6))
        izquierda = tk.Frame(paneles, bg=FONDO)
        derecha = tk.Frame(paneles, bg=FONDO)
        paneles.add(izquierda, weight=2)
        paneles.add(derecha, weight=3)

        self.montar_editor(izquierda)
        self.pestanas = ttk.Notebook(derecha)
        self.pestanas.pack(fill="both", expand=True)
        maquina = tk.Frame(self.pestanas, bg=FONDO)
        roms = tk.Frame(self.pestanas, bg=FONDO)
        sistema = tk.Frame(self.pestanas, bg=FONDO)
        hoja = tk.Frame(self.pestanas, bg=FONDO)
        self.pestanas.add(maquina, text="Máquina")
        self.pestanas.add(roms, text="ROMs")
        self.pestanas.add(sistema, text="Sistema")
        self.pestanas.add(hoja, text="Datasheet")
        self.pestanas.bind("<<NotebookTabChanged>>", lambda e: self.refrescar())
        self.pestana_roms = roms
        self.montar_maquina(maquina)
        self.montar_roms(roms)
        self.sistema = PestanaSistema(sistema, self)
        self.montar_datasheet(hoja)
        self.pestana_hoja = hoja

    def montar_editor(self, padre):
        comun = dict(font=FUENTE, bg=FONDO, wrap="none", relief="flat", borderwidth=0,
                     highlightthickness=0, padx=6, pady=6)
        self.margen = tk.Text(padre, width=11, fg=GRIS, cursor="arrow", takefocus=False, **comun)
        self.editor = tk.Text(padre, fg=TEXTO, insertbackground=AMBAR, undo=True,
                              selectbackground="#44484a", **comun)
        barra = tk.Scrollbar(padre, command=self.desplazar)
        self.editor.config(yscrollcommand=lambda a, b: (barra.set(a, b), self.margen.yview_moveto(a)))
        barra.pack(side="right", fill="y")
        self.margen.pack(side="left", fill="y")
        self.editor.pack(side="left", fill="both", expand=True)

        self.editor.tag_configure("comentario", foreground=GRIS)
        self.editor.tag_configure("etiqueta", foreground=AMBAR)
        self.editor.tag_configure("numero", foreground=AZUL)
        self.editor.tag_configure("destino", foreground=VERDE)
        self.editor.tag_configure("condicion", foreground=ROJO)
        self.editor.tag_configure("sistema", foreground=ROSA)
        self.editor.tag_configure("error", background="#4a2420")
        for texto in (self.editor, self.margen):
            texto.tag_configure("actual", background=LINEA_ACTUAL)
        self.margen.tag_configure("actual", foreground=AMBAR)

        self.editor.bind("<<Modified>>", self.al_modificar)
        self.editor.bind("<Tab>", lambda e: (self.editor.insert("insert", "    "), "break")[1])
        self.margen.bind("<MouseWheel>", lambda e: (self.editor.yview_scroll(-e.delta // 120, "units"), "break")[1])
        self.margen.bind("<Button-4>", lambda e: (self.editor.yview_scroll(-1, "units"), "break")[1])
        self.margen.bind("<Button-5>", lambda e: (self.editor.yview_scroll(1, "units"), "break")[1])

    def desplazar(self, *args):
        self.editor.yview(*args)
        self.margen.yview(*args)

    def montar_maquina(self, padre):
        arriba = tk.Frame(padre, bg=FONDO)
        arriba.pack(fill="x", pady=(6, 0))

        registros = tk.Frame(arriba, bg=PANEL, padx=10, pady=8)
        registros.pack(side="left", fill="y", padx=4, pady=(0, 6))
        self.valores_reg = {}
        for fila, nombre in enumerate(REGISTROS):
            tk.Label(registros, text=nombre, font=FUENTE_GRANDE, fg=ROJO, bg=PANEL, width=5, anchor="w").grid(row=fila, column=0)
            valor = tk.Label(registros, font=FUENTE_GRANDE, bg=PANEL, width=7, anchor="e", cursor="hand2")
            valor.grid(row=fila, column=1)
            hexa = etiqueta(registros, "", width=6, anchor="e")
            hexa.grid(row=fila, column=2)
            valor.bind("<Double-1>", lambda e, n=nombre: self.editar_registro(n))
            self.valores_reg[nombre] = (valor, hexa)

        self.info_ultima = {}
        for fila, nombre in enumerate(("banco", "R vuelve a", "ALU", "flag", "salto", "ciclos"), start=len(REGISTROS)):
            etiqueta(registros, nombre, anchor="w").grid(row=fila, column=0, sticky="w", pady=(6 if nombre == "banco" else 0, 0))
            valor = etiqueta(registros, "", TEXTO, anchor="e")
            valor.grid(row=fila, column=1, columnspan=2, sticky="e")
            self.info_ultima[nombre] = valor

        instruccion = tk.Frame(arriba, bg=PANEL, padx=10, pady=8)
        instruccion.pack(side="left", fill="both", expand=True, padx=4, pady=(0, 6))
        etiqueta(instruccion, "Siguiente instrucción").pack(anchor="w")
        self.texto_linea = tk.Label(instruccion, font=FUENTE_GRANDE, fg=TEXTO, bg=PANEL, anchor="w")
        self.texto_linea.pack(anchor="w", pady=(2, 6))
        self.bits = tk.Text(instruccion, height=3, font=("Consolas", 13), bg=PANEL, fg=TEXTO,
                            relief="flat", borderwidth=0, highlightthickness=0, cursor="arrow")
        self.bits.pack(fill="x")
        for campo, color in COLOR_CAMPO.items():
            self.bits.tag_configure(campo, foreground=color)
        self.bits.tag_configure("tenue", foreground=GRIS)
        self.texto_cables = etiqueta(instruccion, "", ROSA, anchor="w", justify="left", wraplength=520)
        self.texto_cables.pack(anchor="w", pady=(4, 0))

        memorias = tk.Frame(padre, bg=FONDO)
        memorias.pack(fill="both", expand=True)
        self.ram_m = PanelRAM(memorias, self, "M", "A")
        self.ram_n = PanelRAM(memorias, self, "N", "B")

    def montar_roms(self, padre):
        interior = ttk.Notebook(padre)
        interior.pack(fill="both", expand=True, padx=4, pady=6)
        self.roms_interior = interior

        hoja = tk.Frame(interior, bg=FONDO)
        interior.add(hoja, text="ROM de programa")
        marco, self.tabla_programa = nueva_tabla(
            hoja, ("dir", "hex", "bits", "instrucción", "línea del código"), (60, 60, 190, 160, 240), 30)
        marco.pack(fill="both", expand=True)

        hoja = tk.Frame(interior, bg=FONDO)
        interior.add(hoja, text="RAM de programas")
        etiqueta(hoja, "Casillas grabadas con GRABA (las demás valen 0 = NOP)", bg=FONDO).pack(anchor="w")
        marco, self.tabla_p = nueva_tabla(hoja, ("dir", "hex", "bits", "instrucción"), (60, 60, 190, 300), 30)
        marco.pack(fill="both", expand=True)

        hoja = tk.Frame(interior, bg=FONDO)
        interior.add(hoja, text="ROM de la ALU")
        marco, tabla = nueva_tabla(hoja, ("op", "OOOOO", "operación", "byte") + tuple(cq.SENALES_ALU),
                                   (40, 70, 90, 50) + (40,) * 8, 32)
        marco.pack(fill="both", expand=True)
        for op, plantilla, rom in cq.OPERACIONES:
            bits = [(rom >> (7 - i)) & 1 for i in range(8)]
            tabla.insert("", "end", values=(f"{op:02X}", f"{op:05b}", plantilla, f"{rom:02X}", *bits))

        self.hoja_sistema = tk.Frame(interior, bg=FONDO)
        interior.add(self.hoja_sistema, text="ROM de sistema")
        self.tabla_sistema = None
        self.pintar_rom_sistema()
        interior.bind("<<NotebookTabChanged>>", lambda e: self.refrescar())

    def pintar_rom_sistema(self):
        for hijo in self.hoja_sistema.winfo_children():
            hijo.destroy()
        sistema = cq.SISTEMA
        etiqueta(self.hoja_sistema, f"128 direcciones x {sistema.chips() * 8} bits. "
                 "Solo se ven las que tienen algo; el resto vale 0 (NOP).", bg=FONDO).pack(anchor="w")
        nombres = tuple(c["nombre"] for c in sistema.cables)
        marco, tabla = nueva_tabla(self.hoja_sistema, ("código", "X Y OOOOO", "se escribe", "byte") + nombres,
                                   (60, 90, 110, 60) + (95,) * len(nombres), 20)
        marco.pack(fill="both", expand=True)
        for ins in sistema.instrucciones:
            c = ins["codigo"]
            marcas = ["x" if n in ins["cables"] else "" for n in nombres]
            tabla.insert("", "end", values=(c, f"{c >> 6} {c >> 5 & 1} {c & 31:05b}", ins["texto"],
                                            f"{sistema.mascara(c):0{sistema.chips() * 2}X}", *marcas))

    def montar_datasheet(self, padre):
        botones = tk.Frame(padre, bg=FONDO)
        botones.pack(fill="x", padx=4, pady=6)
        boton(botones, "Exportar DATASHEET.md", self.exportar_datasheet).pack(side="left", padx=2)
        boton(botones, "Exportar ROMs (.hex)", self.exportar_roms).pack(side="left", padx=2)
        self.hoja = tk.Text(padre, font=FUENTE, bg=FONDO, fg=TEXTO, wrap="word", relief="flat",
                            highlightthickness=0, padx=10, pady=10)
        barra = tk.Scrollbar(padre, command=self.hoja.yview)
        self.hoja.config(yscrollcommand=barra.set)
        barra.pack(side="right", fill="y")
        self.hoja.pack(fill="both", expand=True)
        self.hoja.tag_configure("titulo", foreground=AMBAR, font=FUENTE_GRANDE)
        self.hoja.tag_configure("tabla", foreground=TEXTO)
        self.hoja.tag_configure("codigo", foreground=AZUL)
        self.hoja.tag_configure("cabecera", foreground=ROJO)
        self.pintar_datasheet()

    def pintar_datasheet(self):
        self.hoja.config(state="normal")
        self.hoja.delete("1.0", "end")
        en_bloque = False
        filas = []
        for linea in cq.datasheet().splitlines() + [""]:
            if linea.startswith("|"):
                if not linea.startswith("|---"):
                    celdas = [c.strip().replace("`", "").replace("\\|", "|")
                              for c in linea.strip()[1:-1].split(" | ")]
                    filas.append(celdas)
                continue
            if filas:
                self.pintar_tabla(filas)
                filas = []
            if linea.startswith("```"):
                en_bloque = not en_bloque
            elif linea.startswith("#"):
                self.hoja.insert("end", linea.lstrip("# ") + "\n", "titulo")
            elif en_bloque:
                self.hoja.insert("end", "  " + linea + "\n", "codigo")
            else:
                self.hoja.insert("end", linea.replace("`", "") + "\n", "tabla")
        self.hoja.config(state="disabled")

    def pintar_tabla(self, filas):
        anchos = [max(len(f[i]) if i < len(f) else 0 for f in filas) for i in range(len(filas[0]))]
        for n, fila in enumerate(filas):
            texto = "  ".join(c.ljust(a) for c, a in zip(fila, anchos))
            self.hoja.insert("end", "  " + texto.rstrip() + "\n", "cabecera" if n == 0 else "tabla")

    def montar_atajos(self):
        atajos = {
            "<F10>": self.paso, "<F5>": self.correr, "<F6>": self.reset, "<F1>": self.ver_datasheet,
            "<Control-s>": self.guardar, "<Control-o>": self.abrir,
        }
        for tecla, funcion in atajos.items():
            # En "all" para pisar el F10 de Windows (abre el menu) y en el editor
            # para que Ctrl+O no meta un salto de linea antes de abrir.
            self.raiz.bind_all(tecla, lambda e, f=funcion: (f(), "break")[1])
            self.editor.bind(tecla, lambda e, f=funcion: (f(), "break")[1])

    def poner_velocidad(self, _valor=None):
        v = VELOCIDADES[self.velocidad.get()]
        self.texto_velocidad.config(text="sin freno" if v == "max" else f"{v} instr/s")

    def estado(self, texto, color=GRIS):
        self.barra_estado.config(text=texto, fg=color)

    def poner_titulo(self):
        nombre = self.ruta.name if self.ruta else "sin título"
        marca = " *" if self.sin_guardar else ""
        self.raiz.title(f"Croquetium IDE - {nombre}{marca}")

    def poner_texto(self, texto):
        self.editor.delete("1.0", "end")
        self.editor.insert("1.0", texto)
        self.editor.edit_reset()
        self.editor.edit_modified(False)
        self.recargar()

    def al_modificar(self, _evento):
        if not self.editor.edit_modified():
            return
        self.editor.edit_modified(False)
        self.sin_guardar = True
        self.poner_titulo()
        if self.pendiente:
            self.raiz.after_cancel(self.pendiente)
        self.pendiente = self.raiz.after(350, self.recargar)

    def recargar(self):
        self.pendiente = None
        self.colorear()
        if self.ensamblar():
            self.reset()

    def sistema_cambiado(self):
        self.pintar_rom_sistema()
        self.pintar_datasheet()
        self.recargar()

    def colorear(self):
        for tag in ("comentario", "etiqueta", "numero", "destino", "condicion", "sistema"):
            self.editor.tag_remove(tag, "1.0", "end")
        for num, linea in enumerate(self.editor.get("1.0", "end-1c").splitlines(), 1):
            codigo, separador, _ = linea.partition("//")
            if separador:
                self.editor.tag_add("comentario", f"{num}.{len(codigo)}", f"{num}.end")
            limpio = codigo.strip()
            if not limpio:
                continue
            inicio = len(codigo) - len(codigo.lstrip())
            final = len(codigo.rstrip())
            if limpio.startswith("("):
                self.editor.tag_add("etiqueta", f"{num}.{inicio}", f"{num}.{final}")
            elif limpio.startswith("@"):
                self.editor.tag_add("numero", f"{num}.{inicio}", f"{num}.{final}")
            elif limpio.upper() == "NOP" or cq.SISTEMA.buscar(limpio):
                self.editor.tag_add("sistema", f"{num}.{inicio}", f"{num}.{final}")
            else:
                cond = RE_CONDICION.search(codigo)
                fin_destino = cond.start() if cond else final
                if cond:
                    self.editor.tag_add("condicion", f"{num}.{cond.start()}", f"{num}.{final}")
                if "=>" in codigo:
                    self.editor.tag_add("destino", f"{num}.{codigo.index('=>')}", f"{num}.{fin_destino}")

    def ensamblar(self):
        fuente = self.editor.get("1.0", "end-1c")
        self.editor.tag_remove("error", "1.0", "end")
        self.linea_de = mapa_lineas(fuente)
        try:
            programa, _, variables = cq.ensamblar(fuente)
        except cq.ErrorEnsamblado as e:
            self.valido = False
            self.parar()
            texto = str(e)
            if texto.startswith("línea "):
                num = texto.split(":")[0].split()[1]
                self.editor.tag_add("error", f"{num}.0", f"{num}.end")
            self.pintar_margen(con_hex=False)
            self.estado(f"Error: {texto}", ROJO)
            return False
        self.valido = True
        self.programa = programa
        self.nombres = {dir_: nombre for nombre, dir_ in variables.items()}
        self.pintar_margen(con_hex=True)
        self.pintar_rom_programa()
        return True

    def pintar_margen(self, con_hex):
        total = int(self.editor.index("end-1c").split(".")[0])
        filas = [""] * total
        for dir_, num in enumerate(self.linea_de):
            hexa = f"{self.programa[dir_][0]:04X}" if con_hex else "...."
            filas[num - 1] = f"{dir_:>4}  {hexa}"
        self.margen.config(state="normal")
        self.margen.delete("1.0", "end")
        self.margen.insert("1.0", "\n".join(filas))
        self.margen.config(state="disabled")
        self.margen.yview_moveto(self.editor.yview()[0])

    def pintar_rom_programa(self):
        tabla = self.tabla_programa
        tabla.delete(*tabla.get_children())
        for dir_, (palabra, original) in enumerate(self.programa):
            tabla.insert("", "end", iid=str(dir_), values=(
                dir_, f"{palabra:04X}", bits_agrupados(palabra), cq.desensamblar(palabra), original))

    def reset(self):
        if not self.valido:
            self.estado("Arregla el error antes de ejecutar", ROJO)
            return
        self.parar()
        self.maquina = cq.Croquetium(self.programa)
        for dir_, valor in self.inputs["M"].items():
            self.maquina.M[dir_] = valor
        for dir_, valor in self.inputs["N"].items():
            self.maquina.N[dir_] = valor
        for nombre, valor in self.inputs["reg"].items():
            setattr(self.maquina, nombre, valor)
        self.fin = None
        self.ultimo = None
        self.cambiadas.clear()
        self.regs_cambiados.clear()
        self.ram_m.vistazo = self.ram_n.vistazo = None
        self.estado(f"Listo: {len(self.programa)} instrucciones", GRIS)
        self.refrescar()

    def avanzar(self):
        m = self.maquina
        if self.fin or not self.valido:
            return
        if m.fuera_del_programa():
            self.fin = "se acabo el programa"
            return
        antes = {n: getattr(m, n) for n in REGISTROS}
        ins = m.instruccion_actual()
        r = m.paso()
        self.ultimo = r
        if not ins & 0x8000:
            d = (ins >> 3) & 0x1F
            if d & 0b01000:
                self.cambiadas.add(("M", antes["A"]))
            if d & 0b10000:
                self.cambiadas.add(("N", antes["B"]))
        for nombre, valor in antes.items():
            if getattr(m, nombre) != valor:
                self.regs_cambiados.add(nombre)
        if m.parado:
            self.fin = f"PARA en {r['pc']}"
            return
        if r["salta"] and m.bucle_final():
            self.fin = f"bucle final en {m.PC}"
        if m.fuera_del_programa():
            self.fin = "se acabo el programa"

    def paso(self):
        if self.corriendo:
            self.parar()
        if not self.valido:
            self.estado("Arregla el error antes de ejecutar", ROJO)
            return
        self.cambiadas.clear()
        self.regs_cambiados.clear()
        self.ram_m.vistazo = self.ram_n.vistazo = None
        self.avanzar()
        self.refrescar()

    def correr(self):
        if self.corriendo:
            self.parar()
            self.refrescar()
            return
        if self.fin or not self.valido:
            return
        self.corriendo = True
        self.boton_correr.config(text="Pausa (F5)", fg=AMBAR)
        self.tic()

    def parar(self):
        self.corriendo = False
        self.boton_correr.config(text="Correr (F5)", fg=TEXTO)

    def tic(self):
        if not self.corriendo:
            return
        v = VELOCIDADES[self.velocidad.get()]
        if v == "max":
            pasos, espera = 20000, 1
        elif v <= 50:
            pasos, espera = 1, 1000 // v
        else:
            pasos, espera = v // 50, 20
        self.cambiadas.clear()
        self.regs_cambiados.clear()
        self.ram_m.vistazo = self.ram_n.vistazo = None
        for _ in range(pasos):
            self.avanzar()
            if self.fin:
                break
        if self.fin:
            self.parar()
        self.refrescar()
        if self.corriendo:
            self.raiz.after(espera, self.tic)

    def refrescar(self):
        m = self.maquina
        for nombre, (valor, hexa) in self.valores_reg.items():
            v = getattr(m, nombre)
            if nombre in self.regs_cambiados:
                color = AMBAR
            elif nombre in self.inputs["reg"]:
                color = AZUL
            else:
                color = TEXTO
            valor.config(text=str(v if nombre in ("PC", "R") else cq.con_signo(v)), fg=color)
            hexa.config(text=f"{v:04X}")

        r = self.ultimo
        info = self.info_ultima
        info["banco"].config(text="RAM programas" if m.banco else "ROM", fg=ROSA if m.banco else TEXTO)
        info["R vuelve a"].config(text=f"{'RAM' if m.R_banco else 'ROM'} {m.R}")
        info["ALU"].config(text=str(cq.con_signo(r["salida"])) if r and r["salida"] is not None else "-")
        info["flag"].config(text=(r["flags"] or "-") if r else "-")
        info["salto"].config(text=("sí" if r["salta"] else "no") if r else "-")
        info["ciclos"].config(text=str(m.ciclos))

        for texto in (self.editor, self.margen):
            texto.tag_remove("actual", "1.0", "end")
        if not m.banco and m.PC < len(m.rom) and m.PC < len(self.linea_de):
            num = self.linea_de[m.PC]
            for texto in (self.editor, self.margen):
                texto.tag_add("actual", f"{num}.0", f"{num + 1}.0")
            if self.corriendo or self.ultimo:
                self.editor.see(f"{num}.0")
        if m.fuera_del_programa():
            self.texto_linea.config(text="(fuera del programa)")
            self.pintar_bits(None)
            self.texto_cables.config(text="")
        else:
            ins = m.instruccion_actual()
            sitio = "P " if m.banco else ""
            self.texto_linea.config(text=f"{sitio}{m.PC}:  {m.texto_actual()}")
            self.pintar_bits(ins)
            if es_sistema(ins):
                mascara = cq.SISTEMA.mascara((ins >> 8) & 0x7F)
                cables = [c["nombre"] for c in cq.SISTEMA.cables if mascara >> cq.SISTEMA.bit_cable[c["nombre"]] & 1]
                self.texto_cables.config(text="cables: " + (", ".join(cables) or "ninguno (NOP)"))
            else:
                self.texto_cables.config(text="")

        self.ram_m.refrescar()
        self.ram_n.refrescar()
        if self.pestanas.select() == str(self.pestana_roms):
            self.refrescar_roms()
        if self.fin:
            self.estado(f"Fin: {self.fin}  ({m.ciclos} ciclos)", AMBAR)

    def refrescar_roms(self):
        m = self.maquina
        tabla = self.tabla_programa
        tabla.selection_remove(*tabla.selection())
        for fila in tabla.tag_has("actual"):
            tabla.item(fila, tags=())
        if not m.banco and tabla.exists(str(m.PC)):
            tabla.item(str(m.PC), tags=("actual",))
            if self.corriendo or self.ultimo:
                tabla.see(str(m.PC))
        p = self.tabla_p
        p.delete(*p.get_children())
        direcciones = sorted(m.usadas_p | ({m.PC} if m.banco else set()))
        for dir_ in direcciones:
            palabra = m.P[dir_]
            marcas = ("actual",) if m.banco and dir_ == m.PC else ()
            p.insert("", "end", tags=marcas, values=(dir_, f"{palabra:04X}", bits_agrupados(palabra),
                                                     cq.desensamblar(palabra)))

    def pintar_bits(self, ins):
        self.bits.config(state="normal")
        self.bits.delete("1.0", "end")
        if ins is not None:
            lista = campos(ins)
            anchos = [max(len(c), len(b), len(s)) + 2 for c, b, s in lista]
            for fila in range(3):
                for (campo, bits, sentido), ancho in zip(lista, anchos):
                    texto = (bits, campo, sentido)[fila]
                    self.bits.insert("end", texto.ljust(ancho), "tenue" if fila == 1 else campo)
                if fila < 2:
                    self.bits.insert("end", "\n")
        self.bits.config(state="disabled")

    def pedir_valor(self, nombre, actual):
        texto = simpledialog.askstring("Cambiar valor", f"{nombre} =  (decimal, 0x.. o 0b..)",
                                       initialvalue=str(cq.con_signo(actual)), parent=self.raiz)
        if texto is None:
            return None
        valor = cq.leer_numero(texto.strip())
        if valor is None or not -0x8000 <= valor <= 0xFFFF:
            messagebox.showerror("Valor no válido", f"'{texto}' no cabe en 16 bits", parent=self.raiz)
            return None
        return valor & cq.MASCARA

    def editar_registro(self, nombre):
        valor = self.pedir_valor(nombre, getattr(self.maquina, nombre))
        if valor is None:
            return
        setattr(self.maquina, nombre, valor)
        self.inputs["reg"][nombre] = valor
        self.maquina.vistos.clear()
        self.fin = None
        self.refrescar()

    def borrar_inputs(self):
        self.inputs = {"M": {}, "N": {}, "reg": {}}
        self.reset()

    def ver_datasheet(self):
        self.pestanas.select(self.pestana_hoja)

    def seguir_sin_guardar(self):
        if not self.sin_guardar:
            return True
        respuesta = messagebox.askyesnocancel("Sin guardar", "Hay cambios sin guardar. ¿Guardar antes?", parent=self.raiz)
        if respuesta is None:
            return False
        return self.guardar() if respuesta else True

    def nuevo(self):
        if not self.seguir_sin_guardar():
            return
        self.ruta = None
        self.poner_texto("")
        self.sin_guardar = False
        self.poner_titulo()

    def abrir(self):
        if not self.seguir_sin_guardar():
            return
        ruta = filedialog.askopenfilename(parent=self.raiz, filetypes=[("Croquetium", "*.cro"), ("Todos", "*.*")])
        if ruta:
            self.abrir_ruta(Path(ruta))

    def abrir_ruta(self, ruta):
        self.ruta = ruta
        self.poner_texto(ruta.read_text(encoding="utf-8"))
        self.sin_guardar = False
        self.poner_titulo()

    def abrir_viejo(self):
        if not self.seguir_sin_guardar():
            return
        ruta = filedialog.askopenfilename(parent=self.raiz, filetypes=[("Croquetium", "*.cro"), ("Todos", "*.*")])
        if not ruta:
            return
        try:
            nuevo = cq.convertir(Path(ruta).read_text(encoding="utf-8"))
        except cq.ErrorEnsamblado as e:
            messagebox.showerror("No se puede convertir", str(e), parent=self.raiz)
            return
        self.ruta = None
        self.poner_texto(nuevo)
        self.sin_guardar = True
        self.poner_titulo()
        self.estado("Convertido a la sintaxis nueva. Guárdalo con otro nombre para no pisar el viejo", VERDE)

    def guardar(self):
        if not self.ruta:
            return self.guardar_como()
        self.ruta.write_text(self.editor.get("1.0", "end-1c"), encoding="utf-8")
        self.sin_guardar = False
        self.poner_titulo()
        self.estado(f"Guardado en {self.ruta}", VERDE)
        return True

    def guardar_como(self):
        ruta = filedialog.asksaveasfilename(parent=self.raiz, defaultextension=".cro",
                                            filetypes=[("Croquetium", "*.cro"), ("Todos", "*.*")])
        if not ruta:
            return False
        self.ruta = Path(ruta)
        return self.guardar()

    def exportar(self):
        if not self.valido:
            self.estado("Arregla el error antes de exportar", ROJO)
            return
        if not self.ruta and not self.guardar_como():
            return
        cq.guardar_binarios(self.programa, self.ruta)
        self.estado(f"Exportado {self.ruta.with_suffix('.bin').name} y {self.ruta.with_suffix('.hex').name}", VERDE)

    def exportar_roms(self):
        carpeta = filedialog.askdirectory(parent=self.raiz, title="Carpeta para rom_alu.hex y rom_sistema.hex")
        if not carpeta:
            return
        cq.guardar_rom_alu(Path(carpeta) / "rom_alu.hex")
        cq.guardar_rom_sistema(Path(carpeta) / "rom_sistema.hex")
        self.estado(f"Exportadas rom_alu.hex y rom_sistema.hex en {carpeta}", VERDE)

    def exportar_datasheet(self):
        ruta = filedialog.asksaveasfilename(parent=self.raiz, initialfile="DATASHEET.md", defaultextension=".md",
                                            filetypes=[("Markdown", "*.md")])
        if ruta:
            Path(ruta).write_text(cq.datasheet(), encoding="utf-8")
            self.estado(f"Datasheet guardada en {ruta}", VERDE)

    def salir(self):
        if self.seguir_sin_guardar():
            self.raiz.destroy()


def main():
    raiz = tk.Tk()
    ide = IDE(raiz)
    if len(sys.argv) > 1:
        ide.abrir_ruta(Path(sys.argv[1]))
    raiz.mainloop()


if __name__ == "__main__":
    main()
