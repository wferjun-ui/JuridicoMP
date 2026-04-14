# JuridicoMP - Controle de Processos

Aplicativo desktop (Windows) para controle de processos e diligências externas do Ministério Público.

## O que esta versão entrega

- Tela inicial com:
  - Pesquisa inteligente de processos.
  - Notificações de processos atrasados e em risco de atraso.
  - Botão **Cadastrar processo**.
- Cadastro de processo com:
  - Validação de número no padrão **CNJ** (`NNNNNNN-DD.AAAA.J.TR.OOOO`).
  - Autor com opção de representado/substituído e representante/genitor.
  - Réus (1 obrigatório por padrão, com múltiplos) e terceiros opcionais.
  - Matéria, assunto e detalhamento de saúde.
- Janela de **Verificações** ao dar duplo clique em um processo:
  - Coluna esquerda com informações do processo em formato vertical.
  - Aba **Verificações** para fase atual, diligências, datas automáticas de verificação/atraso e observações persistentes.
  - Edição de tratamentos/medicamentos (quantidade, necessidade e local).
  - Regra automática: se houver texto de diligência e nenhuma data informada, define verificação para +7 dias e atraso após +14 dias na segunda-feira subsequente.
- Aba **Histórico** com registro das verificações salvas.
- Banco SQLite em caminho configurável (inclusive pasta de rede/UNC), sem servidor de banco.

## Requisitos

- Python 3.11+ (Tkinter incluso em instalações padrão no Windows).

## Como executar

```bash
python app.py
```

Na primeira execução, o app cria `config.json` com o caminho do banco.

## Configuração do banco em pasta de rede

Edite `config.json` para um compartilhamento de rede acessível por todos os usuários:

```json
{
  "database_path": "\\\\SERVIDOR\\juridico\\juridico_mp.db"
}
```
