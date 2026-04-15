# JuridicoMP - Controle de Processos

Aplicativo desktop inicial (Windows) para controle de processos e diligências externas do Ministério Público.

## O que esta versão entrega

- Tela inicial com:
  - Campo de pesquisa inteligente de processos (busca por número, vara, autor, réu e status).
  - Quadro de notificações de **processos atrasados**.
  - Quadro de notificações de **processos que irão atrasar**.
- Banco de dados SQLite gravado em caminho configurável (inclusive pasta de rede/UNC).
- Sem necessidade de instalar servidor de banco de dados.

## Requisitos

- Python 3.11+ (com Tkinter, já incluso na maioria das instalações padrão no Windows).

## Como executar

```bash
python app.py
```

Na primeira execução, o app cria `config.json` com o caminho do banco.

## Configuração do banco em pasta de rede

Edite `config.json` para apontar para um compartilhamento de rede acessível por todos os usuários, por exemplo:

```json
{
  "database_path": "\\\\SERVIDOR\\juridico\\juridico_mp.db"
}
```

> Observação: o app não é portátil por padrão; a ideia é cada usuário ter o executável/script no próprio computador apontando para o mesmo arquivo de banco na rede.

## Próximos passos sugeridos

- Cadastro completo de processo (juiz, representado, substituído, histórico, pendências etc.).
- CRUD de diligências, movimentações e prazos.
- Regras de alerta (lógica de atraso) e trilha de auditoria.
- Empacotamento para Windows com instalador simples (ex.: Inno Setup + binário gerado por PyInstaller).
