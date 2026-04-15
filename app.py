import json
import os
import sqlite3
from dataclasses import dataclass
from pathlib import Path
import tkinter as tk
from tkinter import ttk, messagebox

APP_NAME = "JuridicoMP - Controle de Processos"
CONFIG_FILE = Path("config.json")
DEFAULT_NETWORK_DB = r"\\SERVIDOR\juridico\juridico_mp.db"


@dataclass
class ProcessoResumo:
    numero: str
    vara: str
    autor: str
    reu: str
    status_diligencia: str
    proximo_prazo: str


class Database:
    def __init__(self, db_path: str) -> None:
        self.db_path = db_path
        self.conn = self._connect()
        self._create_schema()

    def _connect(self) -> sqlite3.Connection:
        db_dir = os.path.dirname(self.db_path)
        if db_dir and not os.path.exists(db_dir):
            os.makedirs(db_dir, exist_ok=True)

        conn = sqlite3.connect(self.db_path)
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA foreign_keys=ON;")
        return conn

    def _create_schema(self) -> None:
        self.conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS processos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                numero TEXT NOT NULL UNIQUE,
                vara TEXT,
                juiz TEXT,
                autor TEXT,
                reu TEXT,
                representado TEXT,
                substituido TEXT,
                status_diligencia TEXT DEFAULT 'Em andamento',
                proximo_prazo TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS movimentacoes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                processo_id INTEGER NOT NULL,
                data_movimentacao TEXT,
                descricao TEXT,
                FOREIGN KEY(processo_id) REFERENCES processos(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS diligencias (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                processo_id INTEGER NOT NULL,
                descricao TEXT,
                setor_responsavel TEXT,
                prazo TEXT,
                status TEXT DEFAULT 'Em andamento',
                FOREIGN KEY(processo_id) REFERENCES processos(id) ON DELETE CASCADE
            );
            """
        )
        self.conn.commit()

    def seed_if_empty(self) -> None:
        count = self.conn.execute("SELECT COUNT(*) FROM processos").fetchone()[0]
        if count:
            return

        dados = [
            ("0001234-56.2026.8.26.0100", "1ª Vara Cível", "Maria Lima", "João Souza", "Em andamento", "2026-04-20"),
            ("0007890-12.2025.8.26.0100", "2ª Vara Criminal", "MP", "Carlos Dias", "Atrasado", "2026-04-10"),
            ("0011223-44.2024.8.26.0100", "3ª Vara de Fazenda", "Estado", "Ana Costa", "Risco de atraso", "2026-04-16"),
        ]
        self.conn.executemany(
            """
            INSERT INTO processos (numero, vara, autor, reu, status_diligencia, proximo_prazo)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            dados,
        )
        self.conn.commit()

    def buscar_processos(self, termo: str = "") -> list[ProcessoResumo]:
        termo = termo.strip().lower()
        if not termo:
            query = """
                SELECT numero, vara, autor, reu, status_diligencia, COALESCE(proximo_prazo, '-')
                FROM processos
                ORDER BY numero DESC
                LIMIT 100
            """
            rows = self.conn.execute(query).fetchall()
        else:
            wildcard = f"%{termo}%"
            query = """
                SELECT numero, vara, autor, reu, status_diligencia, COALESCE(proximo_prazo, '-')
                FROM processos
                WHERE lower(numero) LIKE ?
                   OR lower(vara) LIKE ?
                   OR lower(autor) LIKE ?
                   OR lower(reu) LIKE ?
                   OR lower(status_diligencia) LIKE ?
                ORDER BY numero DESC
                LIMIT 100
            """
            rows = self.conn.execute(
                query, [wildcard, wildcard, wildcard, wildcard, wildcard]
            ).fetchall()

        return [ProcessoResumo(*row) for row in rows]

    def processos_atrasados(self) -> list[str]:
        query = """
            SELECT numero || ' • ' || COALESCE(proximo_prazo, '-')
            FROM processos
            WHERE lower(status_diligencia) = 'atrasado'
            ORDER BY proximo_prazo
            LIMIT 10
        """
        return [row[0] for row in self.conn.execute(query).fetchall()]

    def processos_risco_atraso(self) -> list[str]:
        query = """
            SELECT numero || ' • ' || COALESCE(proximo_prazo, '-')
            FROM processos
            WHERE lower(status_diligencia) = 'risco de atraso'
            ORDER BY proximo_prazo
            LIMIT 10
        """
        return [row[0] for row in self.conn.execute(query).fetchall()]


def load_config() -> dict:
    if not CONFIG_FILE.exists():
        config = {"database_path": DEFAULT_NETWORK_DB}
        CONFIG_FILE.write_text(json.dumps(config, indent=2, ensure_ascii=False), encoding="utf-8")
        return config

    return json.loads(CONFIG_FILE.read_text(encoding="utf-8"))


class HomeScreen(ttk.Frame):
    def __init__(self, master: tk.Tk, db: Database) -> None:
        super().__init__(master, padding=16)
        self.db = db
        self.pack(fill="both", expand=True)

        self.columnconfigure(0, weight=3)
        self.columnconfigure(1, weight=2)
        self.rowconfigure(1, weight=1)

        self.search_var = tk.StringVar()
        self.search_var.trace_add("write", self._refresh_processos)

        self._build_header()
        self._build_main_grid()
        self._refresh_processos()
        self._refresh_notifications()

    def _build_header(self) -> None:
        header = ttk.Frame(self)
        header.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 12))
        header.columnconfigure(1, weight=1)

        title = ttk.Label(header, text="Painel Inicial", font=("Segoe UI", 16, "bold"))
        title.grid(row=0, column=0, sticky="w", padx=(0, 12))

        search = ttk.Entry(header, textvariable=self.search_var)
        search.grid(row=0, column=1, sticky="ew")
        search.insert(0, "")
        search.focus()

    def _build_main_grid(self) -> None:
        table_card = ttk.LabelFrame(self, text="Pesquisa inteligente de processos")
        table_card.grid(row=1, column=0, sticky="nsew", padx=(0, 12))
        table_card.columnconfigure(0, weight=1)
        table_card.rowconfigure(0, weight=1)

        cols = ("numero", "vara", "autor", "reu", "status", "prazo")
        self.table = ttk.Treeview(table_card, columns=cols, show="headings", height=16)

        headers = {
            "numero": "Número",
            "vara": "Vara",
            "autor": "Autor",
            "reu": "Réu",
            "status": "Diligência",
            "prazo": "Próximo prazo",
        }
        widths = {"numero": 180, "vara": 150, "autor": 120, "reu": 120, "status": 120, "prazo": 100}

        for col in cols:
            self.table.heading(col, text=headers[col])
            self.table.column(col, width=widths[col], anchor="w")

        self.table.grid(row=0, column=0, sticky="nsew")

        scrollbar = ttk.Scrollbar(table_card, orient="vertical", command=self.table.yview)
        self.table.configure(yscrollcommand=scrollbar.set)
        scrollbar.grid(row=0, column=1, sticky="ns")

        right_col = ttk.Frame(self)
        right_col.grid(row=1, column=1, sticky="nsew")
        right_col.rowconfigure(0, weight=1)
        right_col.rowconfigure(1, weight=1)
        right_col.columnconfigure(0, weight=1)

        self.atrasados_list = self._build_notification_card(right_col, 0, "Processos atrasados")
        self.risco_list = self._build_notification_card(right_col, 1, "Processos que irão atrasar")

    def _build_notification_card(self, parent: ttk.Frame, row: int, title: str) -> tk.Listbox:
        card = ttk.LabelFrame(parent, text=title)
        card.grid(row=row, column=0, sticky="nsew", pady=(0 if row == 0 else 12, 0))
        card.rowconfigure(0, weight=1)
        card.columnconfigure(0, weight=1)

        box = tk.Listbox(card, height=8)
        box.grid(row=0, column=0, sticky="nsew", padx=6, pady=6)
        return box

    def _refresh_processos(self, *_args: object) -> None:
        termo = self.search_var.get()
        processos = self.db.buscar_processos(termo)

        for row in self.table.get_children():
            self.table.delete(row)

        for proc in processos:
            self.table.insert(
                "",
                "end",
                values=(
                    proc.numero,
                    proc.vara,
                    proc.autor,
                    proc.reu,
                    proc.status_diligencia,
                    proc.proximo_prazo,
                ),
            )

    def _refresh_notifications(self) -> None:
        self._set_listbox(self.atrasados_list, self.db.processos_atrasados())
        self._set_listbox(self.risco_list, self.db.processos_risco_atraso())

    @staticmethod
    def _set_listbox(box: tk.Listbox, items: list[str]) -> None:
        box.delete(0, tk.END)
        if not items:
            box.insert(tk.END, "Nenhum processo nesta categoria.")
            return

        for item in items:
            box.insert(tk.END, item)


def main() -> None:
    config = load_config()
    db_path = config.get("database_path", DEFAULT_NETWORK_DB)

    try:
        db = Database(db_path)
    except OSError as exc:
        messagebox.showerror(
            "Erro ao abrir banco de dados",
            f"Não foi possível acessar o caminho configurado:\n{db_path}\n\nDetalhes: {exc}",
        )
        return

    db.seed_if_empty()

    root = tk.Tk()
    root.title(APP_NAME)
    root.geometry("1260x700")
    root.minsize(1024, 640)

    style = ttk.Style()
    if "vista" in style.theme_names():
        style.theme_use("vista")

    HomeScreen(root, db)
    root.mainloop()


if __name__ == "__main__":
    main()
