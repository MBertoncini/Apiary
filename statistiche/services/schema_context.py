def get_schema_context() -> str:
    return """
TABELLE PRINCIPALI (database MySQL, nomi reali Django: nomeapp_nomemodello):

--- APIARI E ARNIE ---
core_apiario: id, nome, posizione, latitudine (DECIMAL), longitudine (DECIMAL),
  proprietario_id (FK auth_user.id), gruppo_id (FK core_gruppo.id, nullable)

core_arnia: id, numero (INT), apiario_id (FK core_apiario.id),
  attiva (TINYINT 0/1), colore (VARCHAR), data_installazione (DATE), note

--- CONTROLLI ARNIE ---
core_controlloarnia: id, arnia_id (FK core_arnia.id), utente_id (FK auth_user.id),
  data (DATE), telaini_scorte (INT), telaini_covata (INT),
  presenza_regina (TINYINT 0/1), sciamatura (TINYINT 0/1),
  problemi_sanitari (TINYINT 0/1), note (TEXT),
  regina_vista (TINYINT 0/1), uova_fresche (TINYINT 0/1),
  celle_reali (TINYINT 0/1), numero_celle_reali (INT),
  data_creazione (DATETIME)

--- REGINE ---
core_regina: id, arnia_id (FK core_arnia.id, UNIQUE),
  data_nascita (DATE nullable), data_introduzione (DATE),
  origine (VARCHAR: acquistata/allevata/sciamatura/emergenza/sconosciuta),
  razza (VARCHAR: ligustica/carnica/buckfast/caucasica/sicula/ibrida/altro),
  marcata (TINYINT 0/1), fecondata (TINYINT 0/1), selezionata (TINYINT 0/1),
  docilita (INT 1-5, nullable), produttivita (INT 1-5, nullable),
  resistenza_malattie (INT 1-5, nullable), tendenza_sciamatura (INT 1-5, nullable),
  codice_marcatura (VARCHAR nullable), note (TEXT nullable)

core_storiaregine: id, arnia_id (FK core_arnia.id), regina_id (FK core_regina.id),
  data_inizio (DATE), data_fine (DATE nullable), motivo_fine (VARCHAR nullable)

--- SMIELATURE (PRODUZIONE MIELE) ---
core_smielatura: id, apiario_id (FK core_apiario.id), data (DATE),
  tipo_miele (VARCHAR), quantita_miele (DECIMAL 7,2), utente_id (FK auth_user.id), note

--- VENDITE ---
core_vendita: id, data (DATE), utente_id (FK auth_user.id),
  canale (VARCHAR: mercatino/negozio/privato/online/altro),
  pagamento (VARCHAR: contanti/bonifico/carta/altro), note

core_dettagliovendita: id, vendita_id (FK core_vendita.id),
  categoria (VARCHAR: miele/propoli/cera/polline/pappa_reale/nucleo/regina/altro),
  tipo_miele (VARCHAR nullable), quantita (INT), prezzo_unitario (DECIMAL 6,2)

--- ECONOMIA ---
core_spesaattrezzatura: id, utente_id (FK auth_user.id), importo (DECIMAL 10,2),
  data (DATE), tipo (VARCHAR), descrizione (VARCHAR),
  attrezzatura_id (FK nullable), gruppo_id (FK core_gruppo.id nullable)

core_pagamento: id, utente_id (FK auth_user.id), importo (DECIMAL 10,2),
  data (DATE), descrizione (VARCHAR), gruppo_id (FK core_gruppo.id nullable)

core_quotautente: id, utente_id (FK auth_user.id), percentuale (DECIMAL 5,2),
  gruppo_id (FK core_gruppo.id nullable)

--- FIORITURE ---
core_fioritura: id, pianta (VARCHAR), data_inizio (DATE), data_fine (DATE nullable),
  latitudine (DECIMAL 12,8), longitudine (DECIMAL 12,8),
  raggio (INT, meters, default 500), creatore_id (FK auth_user.id nullable),
  pubblica (TINYINT 0/1), intensita (INT 1-5 nullable),
  apiario_id (FK core_apiario.id nullable)

--- ATTREZZATURA ---
core_attrezzatura: id, nome (VARCHAR), categoria_id (FK core_categoriaartrezzatura.id nullable),
  proprietario_id (FK auth_user.id), prezzo_acquisto (DECIMAL nullable),
  data_acquisto (DATE nullable), stato (VARCHAR), condizione (VARCHAR), quantita (INT)

core_categoriaartrezzatura: id, nome (VARCHAR), descrizione, icona

--- TRATTAMENTI SANITARI ---
core_trattamentosanitario: id, apiario_id (FK core_apiario.id), utente_id (FK auth_user.id),
  tipo_trattamento_id (FK core_tipotrattamento.id),
  data_inizio (DATE), data_fine (DATE nullable),
  stato (VARCHAR: programmato/in_corso/completato/annullato)

core_tipotrattamento: id, nome (VARCHAR), principio_attivo (VARCHAR)

--- GRUPPI ---
core_gruppo: id, nome (VARCHAR), descrizione (TEXT nullable), creatore_id (FK auth_user.id)

core_membrogruppo: id, utente_id (FK auth_user.id), gruppo_id (FK core_gruppo.id),
  ruolo (VARCHAR: admin/editor/viewer), data_aggiunta (DATETIME)

--- UTENTI ---
auth_user: id, username, first_name, last_name, email, is_active

REGOLE DI FILTRO PER UTENTE (IMPORTANTE - usare sempre):
- Per apiari: WHERE core_apiario.proprietario_id = {user_id}
- Per arnie dell'utente: JOIN core_apiario ON core_arnia.apiario_id = core_apiario.id
  WHERE core_apiario.proprietario_id = {user_id}
- Per controlli: WHERE core_controlloarnia.utente_id = {user_id}
  oppure tramite JOIN su arnia/apiario
- Per smielature: WHERE core_smielatura.utente_id = {user_id}
- Per vendite: WHERE core_vendita.utente_id = {user_id}
- Per spese: WHERE core_spesaattrezzatura.utente_id = {user_id}
- Per attrezzatura: WHERE core_attrezzatura.proprietario_id = {user_id}
- Non usare MAI auth_user senza filtro specifico per ID
"""
