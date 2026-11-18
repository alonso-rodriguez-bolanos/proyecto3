"""Ventana para administrar los juegos de Supabase sin usar la terminal. A la izquierda la lista de juegos y a la derecha dos pestañas: Juegos (botones y formulario) y Ejecutar (procesos, hilos, límites por sitio y el botón para correr el scraper). Abajo, el registro de lo que va pasando. Se abre con: python gestor.py"""

import json
import logging
import os
import queue
import signal
import subprocess
import sys
import tempfile
import threading
import tkinter as tk
import webbrowser
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from herramientas import enlaces, tabla
from scraper import config

CAMPOS_TEXTO = [("nombre", "Nombre"), ("fecha_lanzamiento", "Fecha"), ("precio_sugerido", "Precio"), ("imagen_url", "Imagen")]
CAMPOS_ENLACE = [("url_steam", "Steam"), ("url_psstore", "PS Store"), ("url_metacritic", "Metacritic"), ("url_hltb", "HLTB")]

# Ajustes de la pestaña Ejecutar: nombre en el .env, texto y valor por defecto (el mismo que usa scraper/config.py)
AJUSTES_PARALELISMO = [("WORKERS_JUEGOS", "Procesos (nivel 1)", os.cpu_count() or 4),
                       ("WORKERS_FUENTES", "Hilos por juego (nivel 2)", 3),
                       ("WORKERS_TIENDAS", "Hilos de tiendas (nivel 3)", 2)]
SITIOS = [("STEAM", "Steam", 4, 0.3), ("PSSTORE", "PS Store", 3, 0.5), ("METACRITIC", "Metacritic", 3, 0.5), ("HLTB", "HLTB", 1, 1.0)]
AJUSTES_REINTENTOS = [("INTENTOS", "Intentos por página", 3), ("INTENTOS_HLTB", "Intentos en HLTB", 4),
                      ("TIMEOUT_LECTURA_S", "Espera máxima (s)", 20)]
DECIMALES = ("PAUSA_", "TIMEOUT_")  # ajustes que aceptan decimales
PUERTO_PÁGINA = 8000


class ManejadorCola(logging.Handler):
    """Manda los avisos de las descargas al registro de la ventana, sin la dirección de la página."""

    def __init__(self, cola: queue.Queue):
        super().__init__(logging.WARNING)
        self.cola = cola

    def emit(self, registro: logging.LogRecord) -> None:
        mensaje = registro.getMessage()
        sitio = mensaje.split()[0]
        if "reintento" in mensaje:
            mensaje = f"{sitio} no respondió, reintentando"
        elif "sin respuesta" in mensaje:
            mensaje = f"{sitio} no respondió"
        self.cola.put(("log", None, "\t" + mensaje.split(": http")[0]))


class Gestor:
    """La ventana completa. Las tareas lentas corren en un hilo aparte para que la ventana no se congele."""

    def __init__(self, raíz: tk.Tk):
        self.raíz = raíz
        self.juegos: list[dict] = []
        self.id_actual = None  # id del juego del formulario, None si es nuevo
        self.cola = queue.Queue()
        self.ocupado = False
        self.botones: list[ttk.Button] = []

        raíz.title("Juegos del proyecto")
        raíz.geometry("1320x800")

        panel = ttk.PanedWindow(raíz, orient="horizontal")
        panel.pack(fill="both", expand=True, padx=10, pady=10)
        izquierda = ttk.Frame(panel)
        derecha = ttk.Frame(panel, padding=(14, 0, 0, 0))
        panel.add(izquierda, weight=3)
        panel.add(derecha, weight=2)

        self.proceso = None  # scraper corriendo desde la pestaña Ejecutar
        self.servidor = None  # servidor local de la página (botón Ver página)
        self._lista(izquierda)
        pestañas = ttk.Notebook(derecha)
        pestañas.pack(fill="x")
        juegos = ttk.Frame(pestañas, padding=(0, 12, 0, 0))
        ejecutar = ttk.Frame(pestañas, padding=(0, 12, 0, 0))
        pestañas.add(juegos, text="Juegos")
        pestañas.add(ejecutar, text="Ejecutar")
        self._botones_generales(juegos)
        self._formulario(juegos)
        self._ejecutar(ejecutar)
        self._registro(derecha)
        raíz.after(50, lambda: panel.sashpos(0, 700))  # ancho inicial de la lista

        logging.getLogger().addHandler(ManejadorCola(self.cola))
        raíz.after(100, self._revisar_cola)
        raíz.protocol("WM_DELETE_WINDOW", self._cerrar)
        self.recargar()

    # ---------- construcción ----------

    def _lista(self, marco: ttk.Frame) -> None:
        """Lista de juegos."""
        columnas = ("id", "nombre", "plataformas", "precio", "steam", "ps", "mc", "activo")
        títulos = ("ID", "Nombre", "Plataformas", "Precio", "Steam", "PS", "MC", "Activo")
        anchos = (40, 270, 110, 70, 50, 40, 40, 55)

        self.tabla = ttk.Treeview(marco, columns=columnas, show="headings", selectmode="browse")
        for columna, título, ancho in zip(columnas, títulos, anchos):
            self.tabla.heading(columna, text=título)
            self.tabla.column(columna, width=ancho, anchor="w" if columna == "nombre" else "center")
        self.tabla.tag_configure("inactivo", foreground="gray")
        self.tabla.bind("<<TreeviewSelect>>", self._al_seleccionar)

        barra = ttk.Scrollbar(marco, orient="vertical", command=self.tabla.yview)
        self.tabla.configure(yscrollcommand=barra.set)
        self.tabla.pack(side="left", fill="both", expand=True)
        barra.pack(side="right", fill="y")

    def _botones_generales(self, marco: ttk.Frame) -> None:
        """Botones de toda la lista y buscador."""
        fila = ttk.Frame(marco)
        fila.pack(fill="x")
        for texto, acción in (("Recargar", self.recargar), ("Nuevo", self.nuevo),
                              ("Completar todos", self.completar_todos), ("Importar CSV", self.importar_csv)):
            botón = ttk.Button(fila, text=texto, command=acción)
            botón.pack(side="left", padx=(0, 6))
            self.botones.append(botón)

        búsqueda = ttk.Frame(marco)
        búsqueda.pack(fill="x", pady=(10, 0))
        ttk.Label(búsqueda, text="Buscar", width=10).pack(side="left")
        self.filtro = tk.StringVar()
        self.filtro.trace_add("write", lambda *_: self._llenar_lista())
        ttk.Entry(búsqueda, textvariable=self.filtro).pack(side="left", fill="x", expand=True)

        ttk.Separator(marco).pack(fill="x", pady=12)

    def _formulario(self, marco: ttk.Frame) -> None:
        """Datos del juego elegido."""
        self.título = ttk.Label(marco, text="Nuevo juego", font=("TkDefaultFont", 15, "bold"))
        self.título.pack(anchor="w", pady=(0, 6))

        formulario = ttk.Frame(marco)
        formulario.pack(fill="x")
        formulario.columnconfigure(1, weight=1)
        self.vars = {}
        fila = 0

        for clave, texto in CAMPOS_TEXTO:
            ttk.Label(formulario, text=texto, width=11).grid(row=fila, column=0, sticky="w", pady=3)
            self.vars[clave] = tk.StringVar()
            ttk.Entry(formulario, textvariable=self.vars[clave]).grid(row=fila, column=1, columnspan=2, sticky="we")
            fila += 1

        ttk.Label(formulario, text="Plataformas", width=11).grid(row=fila, column=0, sticky="w", pady=3)
        casillas = ttk.Frame(formulario)
        casillas.grid(row=fila, column=1, columnspan=2, sticky="w")
        self.plataformas = {}
        for plataforma in tabla.PLATAFORMAS:
            self.plataformas[plataforma] = tk.BooleanVar()
            ttk.Checkbutton(casillas, text=plataforma, variable=self.plataformas[plataforma]).pack(side="left", padx=(0, 8))
        fila += 1

        for clave, texto in CAMPOS_ENLACE:
            ttk.Label(formulario, text=texto, width=11).grid(row=fila, column=0, sticky="w", pady=3)
            self.vars[clave] = tk.StringVar()
            ttk.Entry(formulario, textvariable=self.vars[clave]).grid(row=fila, column=1, sticky="we")
            ttk.Button(formulario, text="Abrir", width=6, command=lambda c=clave: self._abrir(c)).grid(row=fila, column=2, padx=(4, 0))
            fila += 1

        self.activo = tk.BooleanVar(value=True)
        ttk.Checkbutton(formulario, text="Activo", variable=self.activo).grid(row=fila, column=1, sticky="w", pady=6)

        acciones = ttk.Frame(marco)
        acciones.pack(fill="x", pady=(6, 0))
        for texto, acción in (("Buscar enlaces", self.buscar_enlaces), ("Guardar", self.guardar)):
            botón = ttk.Button(acciones, text=texto, command=acción)
            botón.pack(side="left", padx=(0, 6))
            self.botones.append(botón)

    def _ejecutar(self, marco: ttk.Frame) -> None:
        """Pestaña para cambiar procesos, hilos y límites, guardarlos en el .env y correr el scraper."""
        self.ajustes: dict[str, tk.StringVar] = {}
        rejilla = ttk.Frame(marco)
        rejilla.pack(fill="x")
        fila = 0

        def título(texto: str) -> None:
            nonlocal fila
            ttk.Label(rejilla, text=texto, font=("TkDefaultFont", 13, "bold")).grid(row=fila, column=0, columnspan=4, sticky="w", pady=(8 if fila else 0, 4))
            fila += 1

        def campo(nombre: str, texto: str, columna: int = 0, ancho: int = 6) -> None:
            self.ajustes[nombre] = tk.StringVar(value=os.environ.get(nombre, ""))
            if texto:
                ttk.Label(rejilla, text=texto).grid(row=fila, column=columna, sticky="w", pady=2, padx=(0, 8))
            ttk.Spinbox(rejilla, textvariable=self.ajustes[nombre], from_=0, to=64, increment=0.1 if nombre.startswith(DECIMALES) else 1,
                        width=ancho).grid(row=fila, column=columna + 1, sticky="w", pady=2, padx=(0, 16))

        título("Paralelismo")
        for nombre, texto, _ in AJUSTES_PARALELISMO:
            campo(nombre, texto)
            fila += 1

        título("Límite por sitio")
        ttk.Label(rejilla, text="A la vez").grid(row=fila, column=1, sticky="w")
        ttk.Label(rejilla, text="Pausa (s)").grid(row=fila, column=2, sticky="w")
        fila += 1
        for clave, texto, _, _ in SITIOS:
            ttk.Label(rejilla, text=texto).grid(row=fila, column=0, sticky="w", pady=2)
            for columna, prefijo in ((1, "LIM_"), (2, "PAUSA_")):
                nombre = prefijo + clave
                self.ajustes[nombre] = tk.StringVar(value=os.environ.get(nombre, ""))
                ttk.Spinbox(rejilla, textvariable=self.ajustes[nombre], from_=0, to=20, increment=1 if prefijo == "LIM_" else 0.1,
                            width=6).grid(row=fila, column=columna, sticky="w", pady=2)
            fila += 1

        título("Reintentos")
        for nombre, texto, _ in AJUSTES_REINTENTOS:
            campo(nombre, texto)
            fila += 1

        título("Corrida")
        self.límite = tk.StringVar(value="0")
        ttk.Label(rejilla, text="Juegos (0 = todos)").grid(row=fila, column=0, sticky="w", pady=2)
        ttk.Spinbox(rejilla, textvariable=self.límite, from_=0, to=1000, width=6).grid(row=fila, column=1, sticky="w")
        fila += 1
        self.secuencial = tk.BooleanVar(value=False)
        self.a_la_página = tk.BooleanVar(value=False)
        ttk.Checkbutton(rejilla, text="Versión secuencial", variable=self.secuencial).grid(row=fila, column=0, columnspan=3, sticky="w")
        fila += 1
        ttk.Checkbutton(rejilla, text="Guardar en web/data.json", variable=self.a_la_página).grid(row=fila, column=0, columnspan=3, sticky="w")

        self._cargar_ajustes()
        acciones = ttk.Frame(marco)
        acciones.pack(fill="x", pady=(12, 0))
        ttk.Button(acciones, text="Guardar ajustes", command=self.guardar_ajustes).pack(side="left", padx=(0, 6))
        ttk.Button(acciones, text="Por defecto", command=self.ajustes_por_defecto).pack(side="left", padx=(0, 6))
        acciones = ttk.Frame(marco)
        acciones.pack(fill="x", pady=(6, 0))
        self.botón_correr = ttk.Button(acciones, text="Ejecutar scraper", command=self.correr_scraper)
        self.botón_correr.pack(side="left", padx=(0, 6))
        self.botón_detener = ttk.Button(acciones, text="Detener", command=self.detener_scraper, state="disabled")
        self.botón_detener.pack(side="left", padx=(0, 6))
        ttk.Button(acciones, text="Ver página", command=self.ver_página).pack(side="left")

    def _registro(self, marco: ttk.Frame) -> None:
        """Registro de lo que va pasando, solo lectura."""
        ttk.Label(marco, text="Registro").pack(anchor="w", pady=(16, 4))
        self.consola = tk.Text(marco, height=12, bg="#1e1e1e", fg="#e0e0e0", font=("Menlo", 13), wrap="word",
                               padx=12, pady=10, spacing1=3, spacing3=3, tabs=("28",), relief="flat", state="disabled")
        self.consola.pack(fill="both", expand=True)

    # ---------- utilidades ----------

    def escribir(self, texto: str) -> None:
        """Agrega una línea al registro. Un tab al inicio indica que es parte de la tarea anterior."""
        self.consola.configure(state="normal")
        self.consola.insert("end", texto + "\n")
        self.consola.see("end")
        self.consola.configure(state="disabled")

    def _en_hilo(self, mensaje: str, tarea, al_terminar=None) -> None:
        """Corre una tarea lenta en otro hilo y al terminar llama a al_terminar con el resultado."""
        if self.ocupado:
            return
        self.ocupado = True
        for botón in self.botones:
            botón.state(["disabled"])
        self.escribir(mensaje)

        def correr():
            try:
                self.cola.put(("hecho", al_terminar, tarea()))
            except Exception as error:
                self.cola.put(("error", None, str(error)))

        threading.Thread(target=correr, daemon=True).start()

    def _revisar_cola(self) -> None:
        """Cada 100 ms atiende los mensajes de los hilos. Solo aquí se toca la ventana."""
        while not self.cola.empty():
            tipo, al_terminar, dato = self.cola.get()
            if tipo == "log":
                self.escribir(dato)
                continue
            if tipo == "fin_scraper":
                self._scraper_terminó()
                continue

            self.ocupado = False
            for botón in self.botones:
                botón.state(["!disabled"])
            if tipo == "error":
                self.escribir(f"\tError: {dato}")
                messagebox.showerror("Error", dato)
            elif al_terminar:
                al_terminar(dato)
        self.raíz.after(100, self._revisar_cola)

    def _llenar_lista(self) -> None:
        """Muestra los juegos que coinciden con el buscador."""
        self.tabla.delete(*self.tabla.get_children())
        texto = self.filtro.get().lower()
        for juego in self.juegos:
            if texto and texto not in juego["nombre"].lower():
                continue
            activo = juego.get("activo", True)
            self.tabla.insert("", "end", iid=str(juego["id"]), tags=() if activo else ("inactivo",), values=(
                juego["id"], juego["nombre"], ", ".join(juego.get("plataformas") or []),
                f"${float(juego['precio_sugerido']):.2f}",
                "✓" if juego.get("url_steam") else "", "✓" if juego.get("url_psstore") else "",
                "✓" if juego.get("url_metacritic") else "", "sí" if activo else "no"))

    def _leer_formulario(self) -> dict:
        """Junta lo escrito en el formulario."""
        juego = {clave: variable.get() for clave, variable in self.vars.items()}
        juego["plataformas"] = [p for p, variable in self.plataformas.items() if variable.get()]
        juego["activo"] = self.activo.get()
        if self.id_actual:
            juego["id"] = self.id_actual
        return tabla.corregir(juego)

    def _mostrar(self, juego: dict) -> None:
        """Pone un juego en el formulario."""
        self.id_actual = juego.get("id")
        self.título.configure(text=juego.get("nombre") or "Nuevo juego")
        for clave, variable in self.vars.items():
            valor = juego.get(clave)
            variable.set("" if valor is None else str(valor))
        for plataforma, variable in self.plataformas.items():
            variable.set(plataforma in (juego.get("plataformas") or []))
        self.activo.set(juego.get("activo", True))

    def _abrir(self, clave: str) -> None:
        """Abre un enlace en el navegador."""
        url = self.vars[clave].get().strip()
        if url.startswith("http"):
            webbrowser.open(url)

    def _al_seleccionar(self, _evento) -> None:
        """Al hacer clic en un juego lo pasa al formulario."""
        selección = self.tabla.selection()
        if selección:
            self._mostrar(next(j for j in self.juegos if str(j["id"]) == selección[0]))

    # ---------- acciones ----------

    def recargar(self) -> None:
        """Trae los juegos de Supabase y guarda un respaldo en datos/juegos.csv."""
        def tarea():
            juegos = tabla.leer_todos()
            tabla.escribir_csv(juegos)
            return juegos

        def listo(juegos):
            self.juegos = juegos
            self._llenar_lista()
            activos = sum(1 for j in juegos if j.get("activo", True))
            self.escribir(f"\t{len(juegos)} juegos, {activos} activos")

        self._en_hilo("Leyendo juegos", tarea, listo)

    def nuevo(self) -> None:
        """Deja el formulario vacío para agregar un juego."""
        self.tabla.selection_remove(self.tabla.selection())
        self._mostrar({"activo": True})

    def buscar_enlaces(self) -> None:
        """Busca los enlaces que faltan del juego del formulario. No guarda."""
        juego = self._leer_formulario()
        if not juego.get("nombre"):
            messagebox.showwarning("Falta el nombre", "Escribe el nombre del juego.")
            return

        def listo(resultados):
            self._mostrar(juego)
            for sitio, estado, _ in resultados:
                self.escribir(f"\t{sitio}: {'listo' if estado == 'OK' else 'no encontrado'}")

        self._en_hilo(f"Buscando enlaces de {juego['nombre']}", lambda: enlaces.completar(juego), listo)

    def guardar(self) -> None:
        """Revisa el formulario y guarda el juego en Supabase."""
        juego = self._leer_formulario()
        errores = tabla.problemas(juego)
        if errores:
            messagebox.showwarning("No se puede guardar", "\n".join(errores))
            return

        def listo(guardado):
            self.juegos = sorted([j for j in self.juegos if j["id"] != guardado["id"]] + [guardado], key=lambda j: j["id"])
            self._llenar_lista()
            self._mostrar(guardado)
            self.tabla.selection_set(str(guardado["id"]))
            self.tabla.see(str(guardado["id"]))
            self.escribir("\tGuardado")

        self._en_hilo(f"Guardando {juego['nombre']}", lambda: tabla.guardar_juego(juego), listo)

    def completar_todos(self) -> None:
        """Busca los enlaces vacíos de todos los juegos y guarda los que cambiaron."""
        pendientes = [j for j in self.juegos if not (j.get("url_psstore") and j.get("url_metacritic") and j.get("imagen_url"))]
        if not pendientes:
            self.escribir("Todos los juegos están completos")
            return
        if not messagebox.askyesno("Completar todos", f"{len(pendientes)} juegos tienen enlaces vacíos. ¿Buscarlos?"):
            return

        def tarea():
            cambiados = 0
            for original in pendientes:
                juego = dict(original)
                faltan = [sitio for sitio, estado, _ in enlaces.completar(juego) if estado != "OK"]
                self.cola.put(("log", None, f"\t{juego['nombre']}: " + ("listo" if not faltan else "falta " + ", ".join(faltan))))
                if juego != original and not tabla.problemas(juego):
                    tabla.guardar_juego(juego)
                    cambiados += 1
            return cambiados

        def listo(cambiados):
            self.escribir(f"\t{cambiados} juegos actualizados")
            self.recargar()

        self._en_hilo(f"Completando {len(pendientes)} juegos", tarea, listo)

    def importar_csv(self) -> None:
        """Sube los juegos válidos de un CSV. Si un nombre ya existe lo actualiza."""
        ruta = filedialog.askopenfilename(title="Elegir CSV de juegos", filetypes=[("CSV", "*.csv")])
        if not ruta:
            return
        juegos = tabla.leer_csv(ruta)
        válidos = [j for j in juegos if not tabla.problemas(j)]
        if not messagebox.askyesno("Importar", f"Se pueden subir {len(válidos)} de {len(juegos)} juegos. ¿Subirlos?"):
            return

        def listo(cantidad):
            self.escribir(f"\t{cantidad} juegos subidos")
            for juego in juegos:
                if juego not in válidos:
                    self.escribir(f"\t{juego.get('nombre')} no se subió: {tabla.problemas(juego)[0]}")
            self.recargar()

        self._en_hilo("Importando CSV", lambda: tabla.subir_varios(válidos), listo)


    # ---------- pestaña Ejecutar ----------

    def _valores_por_defecto(self) -> dict[str, str]:
        """Los mismos valores que usa scraper/config.py si el .env no dice nada."""
        valores = {nombre: str(valor) for nombre, _, valor in AJUSTES_PARALELISMO + AJUSTES_REINTENTOS}
        for clave, _, a_la_vez, pausa in SITIOS:
            valores["LIM_" + clave], valores["PAUSA_" + clave] = str(a_la_vez), str(pausa)
        return valores

    def _cargar_ajustes(self) -> None:
        """Llena los campos con lo que dice el .env, o con el valor por defecto si no está."""
        for nombre, valor in self._valores_por_defecto().items():
            if not self.ajustes[nombre].get():
                self.ajustes[nombre].set(valor)

    def ajustes_por_defecto(self) -> None:
        for nombre, valor in self._valores_por_defecto().items():
            self.ajustes[nombre].set(valor)
        self.escribir("Ajustes por defecto (todavía sin guardar)")

    def _leer_ajustes(self) -> dict[str, str] | None:
        """Devuelve los ajustes como texto. Si alguno no es un número positivo avisa y devuelve None."""
        valores = {}
        for nombre, variable in self.ajustes.items():
            texto = variable.get().strip().replace(",", ".")
            try:
                número = float(texto)
            except ValueError:
                número = -1
            entero = not nombre.startswith(DECIMALES)
            if número < 0 or (entero and (número != int(número) or número < 1)):
                messagebox.showerror("Ajuste inválido", f"{nombre} tiene que ser {'un entero mayor que 0' if entero else 'un número mayor o igual a 0'}")
                return None
            valores[nombre] = str(int(número)) if entero else str(número)
        return valores

    def guardar_ajustes(self) -> None:
        """Escribe los ajustes en el .env. Cambia solo esas líneas y deja las llaves y lo demás igual."""
        valores = self._leer_ajustes()
        if valores is None:
            return
        ruta = config.RAIZ / ".env"
        líneas = ruta.read_text(encoding="utf-8").splitlines() if ruta.exists() else []
        pendientes = dict(valores)
        for i, línea in enumerate(líneas):
            nombre = línea.split("=", 1)[0].strip()
            if nombre in pendientes:
                líneas[i] = f"{nombre}={pendientes.pop(nombre)}"
        if pendientes:
            if "# Ajustes del scraper (los cambia el gestor)" not in líneas:
                líneas += ["", "# Ajustes del scraper (los cambia el gestor)"]
            líneas += [f"{nombre}={valor}" for nombre, valor in pendientes.items()]
        ruta.write_text("\n".join(líneas) + "\n", encoding="utf-8")
        os.environ.update(valores)
        self.escribir("Ajustes guardados en .env")

    def correr_scraper(self) -> None:
        """Corre ejecutar.py en otro proceso con los ajustes de la pestaña y muestra su avance en el registro."""
        if self.proceso:
            return
        valores = self._leer_ajustes()
        if valores is None:
            return
        try:
            límite = int(self.límite.get() or 0)
        except ValueError:
            límite = 0
        página = config.RAIZ / "web" / "data.json"
        temporal = Path(tempfile.gettempdir()) / "gestor_corrida.json"
        temporal.unlink(missing_ok=True)  # sin datos de una corrida anterior
        # Corrida completa: ejecutar.py guarda directo en la página. Con pocos juegos se guarda aparte y después
        # se mezcla, así la página no se queda solo con esos juegos.
        salida = página if self.a_la_página.get() and not límite else temporal
        mezclar = self.a_la_página.get() and bool(límite)
        comando = [sys.executable, "ejecutar.py", "--workers", valores["WORKERS_JUEGOS"], "--salida", str(salida)]
        if límite:
            comando += ["--limite", str(límite)]
        if self.secuencial.get():
            comando.append("--secuencial")
        entorno = {**os.environ, **valores, "PYTHONUNBUFFERED": "1"}  # el entorno le gana al .env

        en_grupo = {"start_new_session": True} if os.name != "nt" else {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP}
        self.proceso = subprocess.Popen(comando, cwd=config.RAIZ, env=entorno, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                        text=True, encoding="utf-8", errors="replace", **en_grupo)
        self.botón_correr.state(["disabled"])
        self.botón_detener.state(["!disabled"])
        modo = "secuencial" if self.secuencial.get() else f"{valores['WORKERS_JUEGOS']} procesos, {valores['WORKERS_FUENTES']} y {valores['WORKERS_TIENDAS']} hilos"
        self.escribir(f"Ejecutando scraper ({modo}, {'todos los juegos' if not límite else f'{límite} juegos'})")
        self.escribir("\tSe guarda en la página" if self.a_la_página.get() else "\tPrueba: no cambia la página")
        threading.Thread(target=self._leer_salida, args=(self.proceso, temporal if mezclar else None), daemon=True).start()

    def _leer_salida(self, proceso: subprocess.Popen, mezclar: Path | None) -> None:
        """Pasa cada línea del scraper al registro, sin la hora ni el nivel, que ya se ven en la terminal. Al final mezcla con la página si hace falta."""
        resumen = ""
        for línea in proceso.stdout:
            texto = línea.rstrip().split(" | ")[-1]
            if texto.startswith("listo:"):
                resumen = texto.removeprefix("listo:").strip()
            if texto:
                self.cola.put(("log", None, "\t" + texto))
        código = proceso.wait()
        if código != 0:
            self.cola.put(("log", None, f"Scraper detenido (código {código})"))
        else:
            self.cola.put(("log", None, "Scraper terminado: " + resumen if resumen else "Scraper terminado"))
            if mezclar:
                try:
                    self.cola.put(("log", None, "\t" + self._mezclar_con_página(mezclar)))
                except Exception as error:
                    self.cola.put(("log", None, f"\tNo se pudo actualizar la página: {error}"))
        self.cola.put(("fin_scraper", None, None))  # la ventana solo se toca desde _revisar_cola

    def _scraper_terminó(self) -> None:
        self.proceso = None
        self.botón_correr.state(["!disabled"])
        self.botón_detener.state(["disabled"])

    @staticmethod
    def _mezclar_con_página(temporal: Path) -> str:
        """Reemplaza en web/data.json solo los juegos de esta corrida y deja los demás como estaban."""
        from scraper import guardar

        nuevos = json.loads(temporal.read_text(encoding="utf-8"))
        ruta = config.RAIZ / "web" / "data.json"
        actuales = json.loads(ruta.read_text(encoding="utf-8")) if ruta.exists() else []
        por_id = {juego["id"]: juego for juego in actuales}
        combinados, _ = guardar.combinar(nuevos, por_id)  # si una fuente falló se conserva su dato bueno anterior
        por_id.update({juego["id"]: juego for juego in combinados})
        guardar.escribir_atomico(sorted(por_id.values(), key=lambda juego: juego["id"]), ruta)
        guardar.actualizar_historial(nuevos, ruta.with_name("historial.json"))
        return f"{len(nuevos)} juegos actualizados en la página ({len(por_id)} en total)"

    def ver_página(self) -> None:
        """Abre la página de web/ en el navegador con un servidor local. Recargar la página muestra el último data.json."""
        if not self.servidor or self.servidor.poll() is not None:
            self.servidor = subprocess.Popen([sys.executable, "-m", "http.server", str(PUERTO_PÁGINA), "--bind", "127.0.0.1",
                                              "--directory", str(config.RAIZ / "web")],
                                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            self.escribir(f"Página local en http://localhost:{PUERTO_PÁGINA}")
        self.raíz.after(600, lambda: webbrowser.open(f"http://localhost:{PUERTO_PÁGINA}/"))

    def _cerrar(self) -> None:
        """Si el scraper sigue corriendo lo detiene antes de cerrar la ventana."""
        if self.proceso:
            self.detener_scraper()
        if self.servidor:
            self.servidor.terminate()
        self.raíz.destroy()

    def detener_scraper(self) -> None:
        """Detiene el scraper y sus procesos hijos."""
        if not self.proceso:
            return
        if os.name != "nt":
            os.killpg(self.proceso.pid, signal.SIGTERM)
        else:
            self.proceso.send_signal(signal.CTRL_BREAK_EVENT)
        self.escribir("Deteniendo scraper")


if __name__ == "__main__":
    ventana = tk.Tk()
    Gestor(ventana)
    ventana.mainloop()
