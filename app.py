import json
import os
import re
import sqlite3
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
import tkinter as tk
from tkinter import messagebox, simpledialog, ttk

APP_NAME = "JuridicoMP - Controle de Processos"
CONFIG_FILE = Path("config.json")
DEFAULT_NETWORK_DB = r"\\SERVIDOR\juridico\juridico_mp.db"
CNJ_PATTERN = re.compile(r"^\d{7}-\d{2}\.\d{4}\.\d\.\d{2}\.\d{4}$")

ASSUNTOS_PADRAO = [
    "Saúde",
    "Cível",
    "Alvará",
    "Mandado de segurança",
    "Tutela de urgência",
    "Execução",
    "Cumprimento de sentença",
    "Ação de conhecimento",
]
TIPOS_SAUDE = ["Terapias", "Medicamentos", "Cirurgias", "Materiais"]
FASES_PROCESSO = ["Cumprimento de sentença", "Arquivado", "Suspenso", "Recurso", "Conhecimento", "Execução"]


@dataclass
class ProcessoResumo:
    id: int
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
        self._run_migrations()
        self._seed_catalogos()

    def _connect(self) -> sqlite3.Connection:
        db_dir = os.path.dirname(self.db_path)
        if db_dir and not os.path.exists(db_dir):
            os.makedirs(db_dir, exist_ok=True)

        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
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
                autor TEXT NOT NULL,
                autor_representado INTEGER DEFAULT 0,
                representado_substituido TEXT,
                representante_genitor TEXT,
                materia TEXT,
                assunto TEXT,
                observacoes_gerais TEXT,
                status_diligencia TEXT DEFAULT 'Em andamento',
                proximo_prazo TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS processo_partes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                processo_id INTEGER NOT NULL,
                tipo TEXT NOT NULL CHECK(tipo IN ('reu', 'terceiro')),
                nome TEXT NOT NULL,
                ordem INTEGER DEFAULT 1,
                FOREIGN KEY(processo_id) REFERENCES processos(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS processo_saude_itens (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                processo_id INTEGER NOT NULL,
                tipo TEXT NOT NULL,
                item_nome TEXT NOT NULL,
                quantidade_prescrita TEXT,
                necessario INTEGER DEFAULT 1,
                local_tratamento TEXT,
                FOREIGN KEY(processo_id) REFERENCES processos(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS itens_catalogo (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tipo TEXT NOT NULL,
                nome TEXT NOT NULL,
                UNIQUE(tipo, nome)
            );

            CREATE TABLE IF NOT EXISTS verificacoes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                processo_id INTEGER NOT NULL,
                data_registro TEXT DEFAULT CURRENT_TIMESTAMP,
                fase_atual TEXT,
                diligencia_texto TEXT,
                data_verificacao TEXT,
                data_atraso TEXT,
                observacoes TEXT,
                FOREIGN KEY(processo_id) REFERENCES processos(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS verificacao_saude_snapshot (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                verificacao_id INTEGER NOT NULL,
                tipo TEXT,
                item_nome TEXT,
                quantidade_prescrita TEXT,
                necessario INTEGER DEFAULT 1,
                local_tratamento TEXT,
                FOREIGN KEY(verificacao_id) REFERENCES verificacoes(id) ON DELETE CASCADE
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

    def _run_migrations(self) -> None:
        self._add_column_if_missing("processos", "observacoes_gerais", "TEXT")
        self._add_column_if_missing("processo_saude_itens", "necessario", "INTEGER DEFAULT 1")
        self._add_column_if_missing("processo_saude_itens", "local_tratamento", "TEXT")

    def _add_column_if_missing(self, table: str, column: str, ddl_type: str) -> None:
        cols = {row["name"] for row in self.conn.execute(f"PRAGMA table_info({table})").fetchall()}
        if column not in cols:
            self.conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {ddl_type}")
            self.conn.commit()

    def _seed_catalogos(self) -> None:
        padroes = {
            "Terapias": ["Fisioterapia", "Fonoaudiologia", "Terapia Ocupacional", "Psicoterapia", "ABA"],
            "Medicamentos": ["Canabidiol", "Risperidona", "Insulina", "Enoxaparina"],
            "Cirurgias": ["Cirurgia ortopédica", "Cirurgia cardíaca", "Neurocirurgia"],
            "Materiais": ["Fralda geriátrica", "Sonda", "Órtese", "Prótese"],
        }
        for tipo, nomes in padroes.items():
            for nome in nomes:
                self.conn.execute("INSERT OR IGNORE INTO itens_catalogo (tipo, nome) VALUES (?, ?)", (tipo, nome))
        self.conn.commit()

    def seed_if_empty(self) -> None:
        count = self.conn.execute("SELECT COUNT(*) FROM processos").fetchone()[0]
        if count:
            return

        processo_id = self.conn.execute(
            """
            INSERT INTO processos (numero, vara, autor, materia, assunto, status_diligencia, proximo_prazo)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            ("0001234-56.2026.8.26.0100", "1ª Vara Cível", "Maria Lima", "Direito Público", "Saúde", "Em andamento", "2026-04-20"),
        ).lastrowid
        self.conn.execute(
            "INSERT INTO processo_partes (processo_id, tipo, nome, ordem) VALUES (?, 'reu', ?, 1)",
            (processo_id, "Município de Exemplo"),
        )
        self.conn.execute(
            """
            INSERT INTO processo_saude_itens (processo_id, tipo, item_nome, quantidade_prescrita, necessario, local_tratamento)
            VALUES (?, 'Terapias', 'Fisioterapia', '20 sessões', 1, 'Clínica credenciada')
            """,
            (processo_id,),
        )
        self.conn.commit()

    def buscar_processos(self, termo: str = "") -> list[ProcessoResumo]:
        termo = termo.strip().lower()
        if not termo:
            rows = self.conn.execute(
                """
                SELECT p.id,
                       p.numero,
                       COALESCE(p.vara, '-'),
                       p.autor,
                       COALESCE((SELECT group_concat(pp.nome, '; ')
                                FROM processo_partes pp
                                WHERE pp.processo_id = p.id AND pp.tipo = 'reu'), '-'),
                       p.status_diligencia,
                       COALESCE(p.proximo_prazo, '-')
                FROM processos p
                ORDER BY p.id DESC
                LIMIT 100
                """
            ).fetchall()
        else:
            wildcard = f"%{termo}%"
            rows = self.conn.execute(
                """
                SELECT p.id,
                       p.numero,
                       COALESCE(p.vara, '-'),
                       p.autor,
                       COALESCE((SELECT group_concat(pp.nome, '; ')
                                FROM processo_partes pp
                                WHERE pp.processo_id = p.id AND pp.tipo = 'reu'), '-'),
                       p.status_diligencia,
                       COALESCE(p.proximo_prazo, '-')
                FROM processos p
                WHERE lower(p.numero) LIKE ?
                   OR lower(COALESCE(p.vara, '')) LIKE ?
                   OR lower(p.autor) LIKE ?
                   OR lower(COALESCE(p.materia, '')) LIKE ?
                   OR lower(COALESCE(p.assunto, '')) LIKE ?
                   OR EXISTS(
                        SELECT 1 FROM processo_partes pp
                        WHERE pp.processo_id = p.id AND lower(pp.nome) LIKE ?
                   )
                ORDER BY p.id DESC
                LIMIT 100
                """,
                [wildcard] * 6,
            ).fetchall()
        return [ProcessoResumo(*row) for row in rows]

    def processos_atrasados(self) -> list[str]:
        rows = self.conn.execute(
            """
            SELECT numero || ' • ' || COALESCE(proximo_prazo, '-')
            FROM processos
            WHERE lower(status_diligencia) = 'atrasado'
            ORDER BY proximo_prazo
            LIMIT 10
            """
        ).fetchall()
        return [r[0] for r in rows]

    def processos_risco_atraso(self) -> list[str]:
        rows = self.conn.execute(
            """
            SELECT numero || ' • ' || COALESCE(proximo_prazo, '-')
            FROM processos
            WHERE lower(status_diligencia) = 'risco de atraso'
            ORDER BY proximo_prazo
            LIMIT 10
            """
        ).fetchall()
        return [r[0] for r in rows]

    def itens_catalogo(self, tipo: str) -> list[str]:
        rows = self.conn.execute("SELECT nome FROM itens_catalogo WHERE tipo = ? ORDER BY nome", (tipo,)).fetchall()
        return [r[0] for r in rows]

    def registrar_item_catalogo(self, tipo: str, nome: str) -> None:
        nome = nome.strip()
        if not nome:
            return
        self.conn.execute("INSERT OR IGNORE INTO itens_catalogo (tipo, nome) VALUES (?, ?)", (tipo, nome))
        self.conn.commit()

    def criar_processo(self, payload: dict) -> None:
        cur = self.conn.cursor()
        processo_id = cur.execute(
            """
            INSERT INTO processos (
                numero, vara, juiz, autor, autor_representado,
                representado_substituido, representante_genitor, materia, assunto, observacoes_gerais
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                payload["numero"],
                payload.get("vara"),
                payload.get("juiz"),
                payload["autor"],
                1 if payload.get("autor_representado") else 0,
                payload.get("representado_substituido"),
                payload.get("representante_genitor"),
                payload.get("materia"),
                payload.get("assunto"),
                payload.get("observacoes_gerais"),
            ),
        ).lastrowid

        for idx, nome in enumerate(payload.get("reus", []), start=1):
            cur.execute("INSERT INTO processo_partes (processo_id, tipo, nome, ordem) VALUES (?, 'reu', ?, ?)", (processo_id, nome, idx))

        for idx, nome in enumerate(payload.get("terceiros", []), start=1):
            cur.execute(
                "INSERT INTO processo_partes (processo_id, tipo, nome, ordem) VALUES (?, 'terceiro', ?, ?)",
                (processo_id, nome, idx),
            )

        for item in payload.get("saude_itens", []):
            cur.execute(
                """
                INSERT INTO processo_saude_itens (processo_id, tipo, item_nome, quantidade_prescrita, necessario, local_tratamento)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    processo_id,
                    item["tipo"],
                    item["nome"],
                    item.get("quantidade"),
                    1 if item.get("necessario", True) else 0,
                    item.get("local", ""),
                ),
            )
            self.registrar_item_catalogo(item["tipo"], item["nome"])

        self.conn.commit()

    def obter_processo(self, processo_id: int) -> sqlite3.Row:
        row = self.conn.execute("SELECT * FROM processos WHERE id = ?", (processo_id,)).fetchone()
        if row is None:
            raise ValueError("Processo não encontrado")
        return row

    def listar_partes(self, processo_id: int, tipo: str) -> list[str]:
        rows = self.conn.execute(
            "SELECT nome FROM processo_partes WHERE processo_id = ? AND tipo = ? ORDER BY ordem",
            (processo_id, tipo),
        ).fetchall()
        return [r[0] for r in rows]

    def listar_saude_itens(self, processo_id: int) -> list[dict]:
        rows = self.conn.execute(
            """
            SELECT id, tipo, item_nome, COALESCE(quantidade_prescrita,''),
                   COALESCE(necessario, 1), COALESCE(local_tratamento,'')
            FROM processo_saude_itens
            WHERE processo_id = ?
            ORDER BY tipo, item_nome
            """,
            (processo_id,),
        ).fetchall()
        return [
            {
                "id": r[0],
                "tipo": r[1],
                "nome": r[2],
                "quantidade": r[3],
                "necessario": bool(r[4]),
                "local": r[5],
            }
            for r in rows
        ]

    def salvar_verificacao(self, processo_id: int, payload: dict, saude_itens: list[dict]) -> None:
        cur = self.conn.cursor()

        status, proximo_prazo = self._status_from_datas(payload["diligencia_texto"], payload["data_verificacao"], payload["data_atraso"])

        cur.execute(
            """
            UPDATE processos
               SET observacoes_gerais = ?,
                   status_diligencia = ?,
                   proximo_prazo = ?
             WHERE id = ?
            """,
            (payload.get("observacoes", ""), status, proximo_prazo, processo_id),
        )

        verificacao_id = cur.execute(
            """
            INSERT INTO verificacoes (processo_id, fase_atual, diligencia_texto, data_verificacao, data_atraso, observacoes)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                processo_id,
                payload.get("fase_atual", ""),
                payload.get("diligencia_texto", ""),
                payload.get("data_verificacao", ""),
                payload.get("data_atraso", ""),
                payload.get("observacoes", ""),
            ),
        ).lastrowid

        cur.execute("DELETE FROM processo_saude_itens WHERE processo_id = ?", (processo_id,))
        for item in saude_itens:
            cur.execute(
                """
                INSERT INTO processo_saude_itens (processo_id, tipo, item_nome, quantidade_prescrita, necessario, local_tratamento)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    processo_id,
                    item["tipo"],
                    item["nome"],
                    item.get("quantidade", ""),
                    1 if item.get("necessario", True) else 0,
                    item.get("local", ""),
                ),
            )
            self.registrar_item_catalogo(item["tipo"], item["nome"])

            cur.execute(
                """
                INSERT INTO verificacao_saude_snapshot
                    (verificacao_id, tipo, item_nome, quantidade_prescrita, necessario, local_tratamento)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    verificacao_id,
                    item["tipo"],
                    item["nome"],
                    item.get("quantidade", ""),
                    1 if item.get("necessario", True) else 0,
                    item.get("local", ""),
                ),
            )

        self.conn.commit()

    @staticmethod
    def _status_from_datas(diligencia: str, data_verificacao: str, data_atraso: str) -> tuple[str, str | None]:
        if not diligencia.strip():
            return "Em andamento", None

        hoje = date.today()
        dt_verif = datetime.strptime(data_verificacao, "%Y-%m-%d").date() if data_verificacao else hoje + timedelta(days=7)
        dt_atraso = datetime.strptime(data_atraso, "%Y-%m-%d").date() if data_atraso else next_monday(hoje + timedelta(days=14))

        if hoje > dt_atraso:
            return "Atrasado", dt_verif.isoformat()
        return "Risco de atraso", dt_verif.isoformat()

    def historico_verificacoes(self, processo_id: int) -> list[sqlite3.Row]:
        return self.conn.execute(
            """
            SELECT id, data_registro, fase_atual, diligencia_texto, data_verificacao, data_atraso, observacoes
            FROM verificacoes
            WHERE processo_id = ?
            ORDER BY id DESC
            """,
            (processo_id,),
        ).fetchall()


def load_config() -> dict:
    if not CONFIG_FILE.exists():
        config = {"database_path": DEFAULT_NETWORK_DB}
        CONFIG_FILE.write_text(json.dumps(config, indent=2, ensure_ascii=False), encoding="utf-8")
        return config
    return json.loads(CONFIG_FILE.read_text(encoding="utf-8"))


def next_monday(base_day: date) -> date:
    days_until_monday = (7 - base_day.weekday()) % 7
    if days_until_monday == 0:
        days_until_monday = 7
    return base_day + timedelta(days=days_until_monday)


class CadastroProcessoDialog(tk.Toplevel):
    def __init__(self, master: tk.Tk, db: Database, on_save: callable) -> None:
        super().__init__(master)
        self.db = db
        self.on_save = on_save
        self.title("Cadastro de Processo")
        self.geometry("960x760")
        self.transient(master)
        self.grab_set()

        self.vars: dict[str, tk.Variable] = {
            "numero": tk.StringVar(),
            "vara": tk.StringVar(),
            "juiz": tk.StringVar(),
            "autor": tk.StringVar(),
            "autor_representado": tk.BooleanVar(value=False),
            "representado_substituido": tk.StringVar(),
            "representante_genitor": tk.StringVar(),
            "materia": tk.StringVar(),
            "assunto": tk.StringVar(value=ASSUNTOS_PADRAO[0]),
            "tem_terceiros": tk.BooleanVar(value=False),
            "tipo_saude": tk.StringVar(value=TIPOS_SAUDE[0]),
            "observacoes_gerais": tk.StringVar(),
        }
        self.reus: list[str] = ["Réu 01"]
        self.terceiros: list[str] = []
        self.saude_itens: list[dict] = []

        self._build_ui()
        self._toggle_representado()
        self._toggle_terceiros()
        self._toggle_bloco_saude()

    def _build_ui(self) -> None:
        container = ttk.Frame(self, padding=12)
        container.pack(fill="both", expand=True)
        container.columnconfigure(0, weight=1)
        container.rowconfigure(1, weight=1)

        ttk.Label(container, text="Novo cadastro de processo", font=("Segoe UI", 14, "bold")).grid(row=0, column=0, sticky="w")
        notebook = ttk.Notebook(container)
        notebook.grid(row=1, column=0, sticky="nsew", pady=(8, 0))

        abas = {name: ttk.Frame(notebook, padding=10) for name in ["Dados básicos", "Partes", "Saúde"]}
        for name, frame in abas.items():
            notebook.add(frame, text=name)

        self._build_aba_basica(abas["Dados básicos"])
        self._build_aba_partes(abas["Partes"])
        self._build_aba_saude(abas["Saúde"])

        actions = ttk.Frame(container)
        actions.grid(row=2, column=0, sticky="e", pady=(10, 0))
        ttk.Button(actions, text="Cancelar", command=self.destroy).pack(side="right", padx=(6, 0))
        ttk.Button(actions, text="Salvar cadastro", command=self._salvar).pack(side="right")

    def _build_aba_basica(self, parent: ttk.Frame) -> None:
        parent.columnconfigure(0, weight=1)
        parent.columnconfigure(1, weight=1)

        ttk.Label(parent, text="Número CNJ*").grid(row=0, column=0, sticky="w")
        ttk.Entry(parent, textvariable=self.vars["numero"]).grid(row=1, column=0, sticky="ew", padx=(0, 8), pady=(0, 8))

        ttk.Label(parent, text="Vara").grid(row=0, column=1, sticky="w")
        ttk.Entry(parent, textvariable=self.vars["vara"]).grid(row=1, column=1, sticky="ew", pady=(0, 8))

        ttk.Label(parent, text="Juiz").grid(row=2, column=0, sticky="w")
        ttk.Entry(parent, textvariable=self.vars["juiz"]).grid(row=3, column=0, sticky="ew", padx=(0, 8), pady=(0, 8))

        ttk.Label(parent, text="Matéria").grid(row=2, column=1, sticky="w")
        ttk.Entry(parent, textvariable=self.vars["materia"]).grid(row=3, column=1, sticky="ew", pady=(0, 8))

        ttk.Label(parent, text="Assunto").grid(row=4, column=0, sticky="w")
        ttk.Combobox(parent, textvariable=self.vars["assunto"], values=ASSUNTOS_PADRAO).grid(
            row=5, column=0, sticky="ew", padx=(0, 8), pady=(0, 8)
        )

        ttk.Label(parent, text="Autor*").grid(row=4, column=1, sticky="w")
        ttk.Entry(parent, textvariable=self.vars["autor"]).grid(row=5, column=1, sticky="ew", pady=(0, 8))

        ttk.Checkbutton(
            parent,
            text="Autor representado/substituído",
            variable=self.vars["autor_representado"],
            command=self._toggle_representado,
        ).grid(row=6, column=0, columnspan=2, sticky="w", pady=(0, 8))

        self.rep_frame = ttk.Frame(parent)
        self.rep_frame.grid(row=7, column=0, columnspan=2, sticky="ew")
        self.rep_frame.columnconfigure(0, weight=1)
        self.rep_frame.columnconfigure(1, weight=1)

        ttk.Label(self.rep_frame, text="Representado/substituído").grid(row=0, column=0, sticky="w")
        ttk.Entry(self.rep_frame, textvariable=self.vars["representado_substituido"]).grid(row=1, column=0, sticky="ew", padx=(0, 8))
        ttk.Label(self.rep_frame, text="Representante/genitor").grid(row=0, column=1, sticky="w")
        ttk.Entry(self.rep_frame, textvariable=self.vars["representante_genitor"]).grid(row=1, column=1, sticky="ew")

        ttk.Label(parent, text="Observações gerais").grid(row=8, column=0, sticky="w", pady=(10, 0))
        ttk.Entry(parent, textvariable=self.vars["observacoes_gerais"]).grid(row=9, column=0, columnspan=2, sticky="ew")

    def _build_aba_partes(self, parent: ttk.Frame) -> None:
        parent.columnconfigure(0, weight=1)
        parent.columnconfigure(1, weight=1)

        reu_card = ttk.LabelFrame(parent, text="Réus")
        reu_card.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        reu_card.columnconfigure(0, weight=1)
        self.reus_list = tk.Listbox(reu_card, height=10)
        self.reus_list.grid(row=0, column=0, sticky="nsew", padx=6, pady=6)
        self._refresh_reus()

        row_actions = ttk.Frame(reu_card)
        row_actions.grid(row=1, column=0, sticky="e", padx=6, pady=(0, 6))
        ttk.Button(row_actions, text="Adicionar", command=self._add_reu).pack(side="left")
        ttk.Button(row_actions, text="Remover", command=self._remove_reu).pack(side="left", padx=(6, 0))

        ter_card = ttk.LabelFrame(parent, text="Terceiros")
        ter_card.grid(row=0, column=1, sticky="nsew")
        ter_card.columnconfigure(0, weight=1)

        ttk.Checkbutton(
            ter_card,
            text="Habilitar terceiros",
            variable=self.vars["tem_terceiros"],
            command=self._toggle_terceiros,
        ).grid(row=0, column=0, sticky="w", padx=6, pady=(6, 2))

        self.ter_list = tk.Listbox(ter_card, height=10)
        self.ter_list.grid(row=1, column=0, sticky="nsew", padx=6, pady=6)
        self.ter_actions = ttk.Frame(ter_card)
        self.ter_actions.grid(row=2, column=0, sticky="e", padx=6, pady=(0, 6))
        ttk.Button(self.ter_actions, text="Adicionar", command=self._add_ter).pack(side="left")
        ttk.Button(self.ter_actions, text="Remover", command=self._remove_ter).pack(side="left", padx=(6, 0))

    def _build_aba_saude(self, parent: ttk.Frame) -> None:
        parent.columnconfigure(1, weight=1)
        ttk.Label(parent, text="Detalhamento para assunto Saúde").grid(row=0, column=0, columnspan=4, sticky="w", pady=(0, 8))

        self.saude_frame = ttk.Frame(parent)
        self.saude_frame.grid(row=1, column=0, columnspan=4, sticky="nsew")

        ttk.Label(self.saude_frame, text="Tipo").grid(row=0, column=0, sticky="w")
        ttk.Combobox(self.saude_frame, textvariable=self.vars["tipo_saude"], values=TIPOS_SAUDE, state="readonly").grid(row=1, column=0, sticky="ew", padx=(0, 8))

        ttk.Label(self.saude_frame, text="Item").grid(row=0, column=1, sticky="w")
        self.item_combo = ttk.Combobox(self.saude_frame)
        self.item_combo.grid(row=1, column=1, sticky="ew", padx=(0, 8))

        ttk.Label(self.saude_frame, text="Qtd prescrita").grid(row=0, column=2, sticky="w")
        self.qtd_entry = ttk.Entry(self.saude_frame)
        self.qtd_entry.grid(row=1, column=2, sticky="ew", padx=(0, 8))

        ttk.Label(self.saude_frame, text="Local").grid(row=0, column=3, sticky="w")
        self.local_entry = ttk.Entry(self.saude_frame)
        self.local_entry.grid(row=1, column=3, sticky="ew", padx=(0, 8))

        self.necessario_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(self.saude_frame, text="Necessário", variable=self.necessario_var).grid(row=1, column=4, sticky="w", padx=(0, 8))
        ttk.Button(self.saude_frame, text="Novo item", command=self._novo_item_catalogo).grid(row=1, column=5, padx=(0, 8))
        ttk.Button(self.saude_frame, text="Adicionar", command=self._add_saude_item).grid(row=1, column=6)

        self.saude_list = tk.Listbox(parent, height=10)
        self.saude_list.grid(row=2, column=0, columnspan=4, sticky="nsew", pady=(8, 6))
        ttk.Button(parent, text="Remover item", command=self._remove_saude_item).grid(row=3, column=3, sticky="e")

        self.vars["tipo_saude"].trace_add("write", lambda *_: self._refresh_catalogo())
        self.vars["assunto"].trace_add("write", lambda *_: self._toggle_bloco_saude())
        self._refresh_catalogo()

    def _toggle_representado(self) -> None:
        state = "normal" if self.vars["autor_representado"].get() else "disabled"
        for child in self.rep_frame.winfo_children():
            if isinstance(child, ttk.Entry):
                child.configure(state=state)

    def _toggle_terceiros(self) -> None:
        state = "normal" if self.vars["tem_terceiros"].get() else "disabled"
        self.ter_list.configure(state=state)
        for c in self.ter_actions.winfo_children():
            c.configure(state=state)
        if state == "disabled":
            self.terceiros.clear()
            self._refresh_ter()

    def _toggle_bloco_saude(self) -> None:
        assunto = self.vars["assunto"].get().strip().lower()
        state = "normal" if assunto == "saúde" else "disabled"
        for c in self.saude_frame.winfo_children():
            try:
                c.configure(state=state)
            except tk.TclError:
                pass
        self.saude_list.configure(state=state)

    def _refresh_catalogo(self) -> None:
        self.item_combo["values"] = self.db.itens_catalogo(self.vars["tipo_saude"].get())

    def _refresh_reus(self) -> None:
        self.reus_list.delete(0, tk.END)
        for nome in self.reus:
            self.reus_list.insert(tk.END, nome)

    def _refresh_ter(self) -> None:
        self.ter_list.delete(0, tk.END)
        for nome in self.terceiros:
            self.ter_list.insert(tk.END, nome)

    def _refresh_saude(self) -> None:
        self.saude_list.delete(0, tk.END)
        for item in self.saude_itens:
            self.saude_list.insert(
                tk.END,
                f"{item['tipo']} - {item['nome']} | Qtd: {item['quantidade'] or '-'} | Local: {item['local'] or '-'} | Necessário: {'Sim' if item['necessario'] else 'Não'}",
            )

    def _add_reu(self) -> None:
        nome = simpledialog.askstring("Réu", "Nome do réu:", parent=self)
        if nome and nome.strip():
            self.reus.append(nome.strip())
            self._refresh_reus()

    def _remove_reu(self) -> None:
        sel = self.reus_list.curselection()
        if not sel:
            return
        if len(self.reus) == 1:
            messagebox.showwarning("Validação", "Ao menos 1 réu é obrigatório.", parent=self)
            return
        self.reus.pop(sel[0])
        self._refresh_reus()

    def _add_ter(self) -> None:
        nome = simpledialog.askstring("Terceiro", "Nome do terceiro:", parent=self)
        if nome and nome.strip():
            self.terceiros.append(nome.strip())
            self._refresh_ter()

    def _remove_ter(self) -> None:
        sel = self.ter_list.curselection()
        if not sel:
            return
        self.terceiros.pop(sel[0])
        self._refresh_ter()

    def _novo_item_catalogo(self) -> None:
        tipo = self.vars["tipo_saude"].get()
        nome = simpledialog.askstring("Novo item", f"Item de {tipo}:", parent=self)
        if nome and nome.strip():
            self.db.registrar_item_catalogo(tipo, nome.strip())
            self._refresh_catalogo()
            self.item_combo.set(nome.strip())

    def _add_saude_item(self) -> None:
        nome = self.item_combo.get().strip()
        if not nome:
            messagebox.showwarning("Validação", "Informe o item de saúde.", parent=self)
            return
        item = {
            "tipo": self.vars["tipo_saude"].get(),
            "nome": nome,
            "quantidade": self.qtd_entry.get().strip(),
            "local": self.local_entry.get().strip(),
            "necessario": self.necessario_var.get(),
        }
        self.saude_itens.append(item)
        self.db.registrar_item_catalogo(item["tipo"], item["nome"])
        self._refresh_catalogo()
        self._refresh_saude()
        self.item_combo.set("")
        self.qtd_entry.delete(0, tk.END)
        self.local_entry.delete(0, tk.END)
        self.necessario_var.set(True)

    def _remove_saude_item(self) -> None:
        sel = self.saude_list.curselection()
        if not sel:
            return
        self.saude_itens.pop(sel[0])
        self._refresh_saude()

    def _validate(self) -> tuple[bool, str]:
        if not CNJ_PATTERN.match(self.vars["numero"].get().strip()):
            return False, "Número CNJ inválido. Use NNNNNNN-DD.AAAA.J.TR.OOOO"
        if not self.vars["autor"].get().strip():
            return False, "Autor é obrigatório."
        if not self.reus:
            return False, "Ao menos 1 réu é obrigatório."
        if self.vars["autor_representado"].get() and not self.vars["representado_substituido"].get().strip():
            return False, "Informe o representado/substituído."
        return True, ""

    def _salvar(self) -> None:
        ok, msg = self._validate()
        if not ok:
            messagebox.showerror("Erro", msg, parent=self)
            return
        payload = {
            "numero": self.vars["numero"].get().strip(),
            "vara": self.vars["vara"].get().strip(),
            "juiz": self.vars["juiz"].get().strip(),
            "autor": self.vars["autor"].get().strip(),
            "autor_representado": self.vars["autor_representado"].get(),
            "representado_substituido": self.vars["representado_substituido"].get().strip(),
            "representante_genitor": self.vars["representante_genitor"].get().strip(),
            "materia": self.vars["materia"].get().strip(),
            "assunto": self.vars["assunto"].get().strip(),
            "observacoes_gerais": self.vars["observacoes_gerais"].get().strip(),
            "reus": self.reus,
            "terceiros": self.terceiros,
            "saude_itens": self.saude_itens,
        }
        try:
            self.db.criar_processo(payload)
        except sqlite3.IntegrityError:
            messagebox.showerror("Erro", "Já existe processo com este número.", parent=self)
            return
        self.on_save()
        self.destroy()


class ProcessoDetalheWindow(tk.Toplevel):
    def __init__(self, master: tk.Tk, db: Database, processo_id: int, on_save: callable) -> None:
        super().__init__(master)
        self.db = db
        self.processo_id = processo_id
        self.on_save = on_save
        self.title("Verificações do Processo")
        self.geometry("1180x720")

        self.processo = db.obter_processo(processo_id)
        self.saude_itens = db.listar_saude_itens(processo_id)

        self.fase_var = tk.StringVar(value=FASES_PROCESSO[0])
        self.data_verif_var = tk.StringVar()
        self.data_atraso_var = tk.StringVar()

        self._build_ui()
        self._fill_data()

    def _build_ui(self) -> None:
        root = ttk.Frame(self, padding=10)
        root.pack(fill="both", expand=True)
        root.columnconfigure(1, weight=1)
        root.rowconfigure(0, weight=1)

        left = ttk.LabelFrame(root, text="Informações do processo")
        left.grid(row=0, column=0, sticky="ns", padx=(0, 10))

        self.info_frame = ttk.Frame(left)
        self.info_frame.pack(fill="y", padx=8, pady=8)

        notebook = ttk.Notebook(root)
        notebook.grid(row=0, column=1, sticky="nsew")

        self.tab_ver = ttk.Frame(notebook, padding=10)
        self.tab_hist = ttk.Frame(notebook, padding=10)
        notebook.add(self.tab_ver, text="Verificações")
        notebook.add(self.tab_hist, text="Histórico")

        self._build_tab_verificacoes(self.tab_ver)
        self._build_tab_historico(self.tab_hist)

    def _fill_data(self) -> None:
        infos = {
            "Número": self.processo["numero"],
            "Vara": self.processo["vara"] or "-",
            "Juiz": self.processo["juiz"] or "-",
            "Autor": self.processo["autor"],
            "Representado": self.processo["representado_substituido"] or "-",
            "Representante": self.processo["representante_genitor"] or "-",
            "Réu(s)": "; ".join(self.db.listar_partes(self.processo_id, "reu")) or "-",
            "Terceiros": "; ".join(self.db.listar_partes(self.processo_id, "terceiro")) or "-",
            "Matéria": self.processo["materia"] or "-",
            "Assunto": self.processo["assunto"] or "-",
            "Status": self.processo["status_diligencia"] or "-",
        }
        for i, (k, v) in enumerate(infos.items()):
            ttk.Label(self.info_frame, text=f"{k}", font=("Segoe UI", 9, "bold")).grid(row=i * 2, column=0, sticky="w", pady=(0, 2))
            ttk.Label(self.info_frame, text=v, wraplength=260).grid(row=i * 2 + 1, column=0, sticky="w", pady=(0, 6))

        self.obs_text.delete("1.0", tk.END)
        self.obs_text.insert("1.0", self.processo["observacoes_gerais"] or "")

        self._refresh_saude_grid()
        self._refresh_historico()

    def _build_tab_verificacoes(self, tab: ttk.Frame) -> None:
        tab.columnconfigure(1, weight=1)

        ttk.Label(tab, text="Fase atual").grid(row=0, column=0, sticky="w")
        ttk.Combobox(tab, textvariable=self.fase_var, values=FASES_PROCESSO).grid(row=0, column=1, sticky="ew", pady=(0, 8))

        ttk.Label(tab, text="Diligências realizadas / pendentes").grid(row=1, column=0, columnspan=2, sticky="w")
        self.dilig_text = tk.Text(tab, height=5)
        self.dilig_text.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(0, 8))
        self.dilig_text.bind("<KeyRelease>", lambda _e: self._calcular_prazos())

        dates = ttk.Frame(tab)
        dates.grid(row=3, column=0, columnspan=2, sticky="ew", pady=(0, 8))
        ttk.Label(dates, text="Data de verificação (AAAA-MM-DD)").grid(row=0, column=0, sticky="w")
        ttk.Entry(dates, textvariable=self.data_verif_var).grid(row=1, column=0, sticky="ew", padx=(0, 8))
        ttk.Label(dates, text="Data de atraso (segunda subsequente)").grid(row=0, column=1, sticky="w")
        ttk.Entry(dates, textvariable=self.data_atraso_var).grid(row=1, column=1, sticky="ew")
        dates.columnconfigure(0, weight=1)
        dates.columnconfigure(1, weight=1)

        ttk.Label(tab, text="Observações (persistente)").grid(row=4, column=0, columnspan=2, sticky="w")
        self.obs_text = tk.Text(tab, height=4)
        self.obs_text.grid(row=5, column=0, columnspan=2, sticky="ew", pady=(0, 8))

        ttk.Label(tab, text="Tratamentos / Medicamentos").grid(row=6, column=0, columnspan=2, sticky="w")
        self.saude_tree = ttk.Treeview(
            tab,
            columns=("tipo", "nome", "qtd", "nec", "local"),
            show="headings",
            height=8,
        )
        for col, label, w in [
            ("tipo", "Tipo", 110),
            ("nome", "Item", 200),
            ("qtd", "Quantidade", 120),
            ("nec", "Necessário", 90),
            ("local", "Local", 220),
        ]:
            self.saude_tree.heading(col, text=label)
            self.saude_tree.column(col, width=w, anchor="w")
        self.saude_tree.grid(row=7, column=0, columnspan=2, sticky="nsew")
        self.saude_tree.bind("<Double-1>", self._editar_item_saude)

        ttk.Label(
            tab,
            text="Duplo clique em um item para alterar quantidade, necessidade e local.",
            foreground="#666",
        ).grid(row=8, column=0, columnspan=2, sticky="w", pady=(4, 8))

        btns = ttk.Frame(tab)
        btns.grid(row=9, column=0, columnspan=2, sticky="e")
        ttk.Button(btns, text="Salvar verificação", command=self._salvar_verificacao).pack(side="right")

    def _build_tab_historico(self, tab: ttk.Frame) -> None:
        tab.columnconfigure(0, weight=1)
        tab.rowconfigure(0, weight=1)

        self.hist_tree = ttk.Treeview(
            tab,
            columns=("data", "fase", "verificacao", "atraso", "diligencia", "observacoes"),
            show="headings",
        )
        for col, label, w in [
            ("data", "Registro", 150),
            ("fase", "Fase", 170),
            ("verificacao", "Data verificação", 130),
            ("atraso", "Data atraso", 130),
            ("diligencia", "Diligência", 280),
            ("observacoes", "Observações", 260),
        ]:
            self.hist_tree.heading(col, text=label)
            self.hist_tree.column(col, width=w, anchor="w")
        self.hist_tree.grid(row=0, column=0, sticky="nsew")

    def _refresh_saude_grid(self) -> None:
        for row in self.saude_tree.get_children():
            self.saude_tree.delete(row)
        for idx, item in enumerate(self.saude_itens):
            self.saude_tree.insert(
                "",
                "end",
                iid=str(idx),
                values=(
                    item["tipo"],
                    item["nome"],
                    item.get("quantidade", ""),
                    "Sim" if item.get("necessario", True) else "Não",
                    item.get("local", ""),
                ),
            )

    def _refresh_historico(self) -> None:
        for row in self.hist_tree.get_children():
            self.hist_tree.delete(row)
        for row in self.db.historico_verificacoes(self.processo_id):
            self.hist_tree.insert(
                "",
                "end",
                values=(
                    row["data_registro"],
                    row["fase_atual"] or "-",
                    row["data_verificacao"] or "-",
                    row["data_atraso"] or "-",
                    (row["diligencia_texto"] or "")[:120],
                    (row["observacoes"] or "")[:120],
                ),
            )

    def _calcular_prazos(self) -> None:
        texto = self.dilig_text.get("1.0", tk.END).strip()
        if not texto:
            return
        hoje = date.today()
        if not self.data_verif_var.get().strip():
            self.data_verif_var.set((hoje + timedelta(days=7)).isoformat())
        if not self.data_atraso_var.get().strip():
            self.data_atraso_var.set(next_monday(hoje + timedelta(days=14)).isoformat())

    def _editar_item_saude(self, _event: tk.Event) -> None:
        sel = self.saude_tree.selection()
        if not sel:
            return
        idx = int(sel[0])
        item = self.saude_itens[idx]

        qtd = simpledialog.askstring("Quantidade", "Nova quantidade prescrita:", initialvalue=item.get("quantidade", ""), parent=self)
        if qtd is None:
            return
        local = simpledialog.askstring("Local", "Local do tratamento:", initialvalue=item.get("local", ""), parent=self)
        if local is None:
            return
        necessario = messagebox.askyesno("Necessário", "Este item continua necessário?", parent=self)

        item["quantidade"] = qtd.strip()
        item["local"] = local.strip()
        item["necessario"] = necessario
        self._refresh_saude_grid()

    def _salvar_verificacao(self) -> None:
        data_ver = self.data_verif_var.get().strip()
        data_atr = self.data_atraso_var.get().strip()
        for label, value in [("data_verificação", data_ver), ("data_atraso", data_atr)]:
            if value:
                try:
                    datetime.strptime(value, "%Y-%m-%d")
                except ValueError:
                    messagebox.showerror("Formato inválido", f"{label} deve estar em AAAA-MM-DD.", parent=self)
                    return

        payload = {
            "fase_atual": self.fase_var.get().strip(),
            "diligencia_texto": self.dilig_text.get("1.0", tk.END).strip(),
            "data_verificacao": data_ver,
            "data_atraso": data_atr,
            "observacoes": self.obs_text.get("1.0", tk.END).strip(),
        }

        self.db.salvar_verificacao(self.processo_id, payload, self.saude_itens)
        self.on_save()
        self.processo = self.db.obter_processo(self.processo_id)
        self._refresh_historico()
        messagebox.showinfo("Sucesso", "Verificação registrada no histórico.", parent=self)


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

        ttk.Label(header, text="Painel Inicial", font=("Segoe UI", 16, "bold")).grid(row=0, column=0, sticky="w", padx=(0, 12))
        ttk.Entry(header, textvariable=self.search_var).grid(row=0, column=1, sticky="ew", padx=(0, 8))
        ttk.Button(header, text="Cadastrar processo", command=self._open_cadastro).grid(row=0, column=2, sticky="e")

    def _build_main_grid(self) -> None:
        table_card = ttk.LabelFrame(self, text="Pesquisa inteligente de processos")
        table_card.grid(row=1, column=0, sticky="nsew", padx=(0, 12))
        table_card.columnconfigure(0, weight=1)
        table_card.rowconfigure(0, weight=1)

        cols = ("numero", "vara", "autor", "reu", "status", "prazo")
        self.table = ttk.Treeview(table_card, columns=cols, show="headings", height=16)
        for col, title in {
            "numero": "Número",
            "vara": "Vara",
            "autor": "Autor",
            "reu": "Réu(s)",
            "status": "Diligência",
            "prazo": "Próximo prazo",
        }.items():
            self.table.heading(col, text=title)
            self.table.column(col, anchor="w", width=130 if col != "numero" else 190)
        self.table.grid(row=0, column=0, sticky="nsew")
        self.table.bind("<Double-1>", self._open_processo_selecionado)

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

    def _open_cadastro(self) -> None:
        CadastroProcessoDialog(self.winfo_toplevel(), self.db, self._after_data_change)

    def _open_processo_selecionado(self, _event: tk.Event) -> None:
        sel = self.table.selection()
        if not sel:
            return
        processo_id = int(sel[0])
        ProcessoDetalheWindow(self.winfo_toplevel(), self.db, processo_id, self._after_data_change)

    def _after_data_change(self) -> None:
        self._refresh_processos()
        self._refresh_notifications()

    def _refresh_processos(self, *_args: object) -> None:
        processos = self.db.buscar_processos(self.search_var.get())
        for row in self.table.get_children():
            self.table.delete(row)

        for proc in processos:
            self.table.insert(
                "",
                "end",
                iid=str(proc.id),
                values=(proc.numero, proc.vara, proc.autor, proc.reu, proc.status_diligencia, proc.proximo_prazo),
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
    root.geometry("1280x760")
    root.minsize(1120, 700)

    style = ttk.Style()
    if "vista" in style.theme_names():
        style.theme_use("vista")

    HomeScreen(root, db)
    root.mainloop()


if __name__ == "__main__":
    main()
