import os
import requests
from .schema_context import get_schema_context
from .sql_validator import validate_sql

GROQ_API_URL = 'https://api.groq.com/openai/v1/chat/completions'
GROQ_API_KEY = os.environ.get('GROQ_API_KEY', '')
MODEL = 'llama-3.3-70b-versatile'

SYSTEM_PROMPT = """Sei un assistente SQL esperto per un database MySQL di gestione apiaria.
Ricevi domande in italiano e devi rispondere SOLO con una query SQL valida.

REGOLE ASSOLUTE:
1. Genera SOLO query SELECT. Mai INSERT, UPDATE, DELETE, DROP, CREATE, ALTER.
2. Filtra SEMPRE per l'utente usando: proprietario_id = {user_id} O utente_id = {user_id} O creatore_id = {user_id} a seconda della tabella.
3. Aggiungi sempre LIMIT 500 alla fine se non specificato.
4. Rispondi SOLO con la query SQL, nessun testo aggiuntivo, nessun markdown.
5. Usa i nomi esatti delle tabelle forniti nello schema (formato: nomeapp_nomemodello).
6. I booleani in MySQL sono 0/1, non TRUE/FALSE.

SCHEMA DEL DATABASE:
{schema}
"""


def text_to_sql(domanda: str, user_id: int) -> dict:
    """Chiama Groq API per trasformare una domanda in SQL."""
    if not GROQ_API_KEY:
        raise ValueError('GROQ_API_KEY non configurata. Aggiungila nelle variabili di ambiente.')

    schema = get_schema_context()
    system = SYSTEM_PROMPT.format(user_id=user_id, schema=schema)

    try:
        response = requests.post(
            GROQ_API_URL,
            headers={
                'Authorization': f'Bearer {GROQ_API_KEY}',
                'Content-Type': 'application/json',
            },
            json={
                'model': MODEL,
                'messages': [
                    {'role': 'system', 'content': system},
                    {'role': 'user', 'content': domanda},
                ],
                'temperature': 0.1,
                'max_tokens': 500,
            },
            timeout=30,
        )
        response.raise_for_status()
    except requests.Timeout:
        raise TimeoutError('Il server AI ha impiegato troppo tempo a rispondere.')
    except requests.HTTPError as e:
        if e.response.status_code == 429:
            raise Exception('Limite di richieste AI raggiunto. Riprova tra qualche minuto.')
        raise Exception(f'Errore API Groq: {e.response.status_code}')

    data = response.json()
    sql_raw = data['choices'][0]['message']['content'].strip()

    # Rimuovi eventuali backtick markdown
    sql = sql_raw.replace('```sql', '').replace('```', '').strip()

    return {'sql': sql, 'raw': sql_raw}
