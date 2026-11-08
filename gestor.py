"""Ventana para administrar los juegos de Supabase sin usar la terminal. A la izquierda la lista de juegos y a la derecha los botones, el formulario y el registro de lo que va pasando. Se abre con: python gestor.py"""

import logging
import queue
import threading
import tkinter as tk
import webbrowser
from tkinter import filedialog, messagebox, ttk

from herramientas import enlaces, tabla

CAMPOS_TEXTO = [("nombre", "Nombre"), ("fecha_lanzamiento", "Fecha"), ("precio_sugerido", "Precio"), ("imagen_url", "Imagen")]
CAMPOS_ENLACE = [("url_steam", "Steam"), ("url_psstore", "PS Store"), ("url_metacritic", "Metacritic"), ("url_hltb", "HLTB")]


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

        self._lista(izquierda)
        self._botones_generales(derecha)
        self._formulario(derecha)
        self._registro(derecha)
        raíz.after(50, lambda: panel.sashpos(0, 700))  # ancho inicial de la lista

        logging.getLogger().addHandler(ManejadorCola(self.cola))
        raíz.after(100, self._revisar_cola)
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


if __name__ == "__main__":
    ventana = tk.Tk()
    Gestor(ventana)
    ventana.mainloop()
