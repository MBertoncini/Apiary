# core/urls.py
from django.urls import path
from . import views

urlpatterns = [
    # Dashboard
    path('dashboard/', views.dashboard, name='dashboard'),
    
    # Apiari
    path('apiario/nuovo/', views.ApiarioCreateView.as_view(), name='crea_apiario'),
    path('apiario/<int:apiario_id>/', views.visualizza_apiario, name='visualizza_apiario'),
    path('apiario/<int:apiario_id>/condividi/', views.condividi_apiario, name='condividi_apiario'),
    path('apiario/<int:apiario_id>/gruppo/', views.gestione_apiario_gruppo, name='gestione_apiario_gruppo'),
    
    # Arnie
    path('arnia/nuova/', views.ArniaCreateView.as_view(), name='crea_arnia'),
    path('arnia/<int:pk>/modifica/', views.ArniaUpdateView.as_view(), name='modifica_arnia'),
    path('arnia/<int:arnia_id>/controllo/', views.nuovo_controllo, name='nuovo_controllo'),
    path('controllo/<int:controllo_id>/copia/', views.copia_controllo, name='copia_controllo'),
    path('controllo/<int:controllo_id>/modifica/', views.modifica_controllo, name='modifica_controllo'),
    path('controllo/<int:pk>/elimina/', views.elimina_controllo, name='elimina_controllo'),

    # Queen management URLs
    path('arnia/<int:arnia_id>/regina/', views.visualizza_regina, name='visualizza_regina'),
    path('arnia/<int:arnia_id>/regina/aggiungi/', views.aggiungi_regina, name='aggiungi_regina'),
    path('regina/<int:regina_id>/modifica/', views.modifica_regina, name='modifica_regina'),
    path('arnia/<int:arnia_id>/regina/sostituisci/', views.sostituisci_regina, name='sostituisci_regina'),
    path('regina/<int:regina_id>/genealogia/', views.albero_genealogico, name='albero_genealogico'),
    path('controllo/<int:controllo_id>/regina/', views.aggiorna_presenza_regina, name='aggiorna_presenza_regina'),

    # Gestione Melari e Smielatura
    path('apiario/<int:apiario_id>/melari/', views.gestione_melari, name='gestione_melari'),
    path('arnia/<int:arnia_id>/melario/aggiungi/', views.aggiungi_melario, name='aggiungi_melario'),
    path('melario/<int:melario_id>/rimuovi/', views.rimuovi_melario, name='rimuovi_melario'),
    path('melario/<int:melario_id>/smielatura/', views.invia_in_smielatura, name='invia_in_smielatura'),
    path('apiario/<int:apiario_id>/smielatura/registra/', views.registra_smielatura, name='registra_smielatura'),
    path('smielatura/<int:smielatura_id>/', views.dettaglio_smielatura, name='dettaglio_smielatura'),

    # Fioriture
    path('fioriture/', views.gestione_fioriture, name='gestione_fioriture'),
    path('fioritura/<int:pk>/modifica/', views.FiorituraUpdateView.as_view(), name='modifica_fioritura'),
    path('fioritura/<int:pk>/elimina/', views.fioritura_delete, name='elimina_fioritura'),

    # Pagamenti
    path('pagamenti/', views.gestione_pagamenti, name='gestione_pagamenti'),
    path('pagamento/<int:pk>/modifica/', views.pagamento_update, name='modifica_pagamento'),
    path('pagamento/<int:pk>/elimina/', views.pagamento_delete, name='elimina_pagamento'),
    path('quota/<int:pk>/modifica/', views.quota_update, name='modifica_quota'),
    path('quota/<int:pk>/elimina/', views.quota_delete, name='elimina_quota'),    

    # Quote
    path('quote/', views.gestione_quote, name='gestione_quote'),

    # Trattamenti Sanitari
    path('trattamenti/', views.gestione_trattamenti, name='gestione_trattamenti'),
    path('trattamento/nuovo/', views.nuovo_trattamento, name='nuovo_trattamento'),
    path('apiario/<int:apiario_id>/trattamento/nuovo/', views.nuovo_trattamento, name='nuovo_trattamento_apiario'),  # URL specifica per apiario
    path('trattamento/<int:pk>/modifica/', views.modifica_trattamento, name='modifica_trattamento'),
    path('trattamento/<int:pk>/elimina/', views.elimina_trattamento, name='elimina_trattamento'),
    path('trattamento/<int:pk>/stato/<str:nuovo_stato>/', views.cambio_stato_trattamento, name='cambio_stato_trattamento'),

    # Tipi di Trattamento
    path('trattamenti/tipi/', views.tipi_trattamento, name='tipi_trattamento'),
    path('trattamenti/tipo/<int:pk>/modifica/', views.modifica_tipo_trattamento, name='modifica_tipo_trattamento'),
    path('trattamenti/tipo/<int:pk>/elimina/', views.elimina_tipo_trattamento, name='elimina_tipo_trattamento'),

    # Calendario Apiario
    path('calendario/', views.calendario_apiario, name='calendario_apiario'),
    path('calendario/<int:apiario_id>/', views.calendario_apiario, name='calendario_apiario'),
    path('calendario/eventi/', views.calendario_eventi_json, name='calendario_eventi_json'),

    # Mappe
    path('mappa/', views.mappa_apiari, name='mappa_apiari'),
    path('mappa/seleziona-posizione/', views.seleziona_posizione, name='seleziona_posizione'),
    
    # Gestione Gruppi
    path('gruppi/', views.gestione_gruppi, name='gestione_gruppi'),
    path('gruppi/<int:gruppo_id>/', views.dettaglio_gruppo, name='dettaglio_gruppo'),
    path('gruppi/<int:gruppo_id>/elimina/', views.elimina_gruppo, name='elimina_gruppo'),
    path('gruppi/membro/<int:membro_id>/ruolo/', views.modifica_ruolo_membro, name='modifica_ruolo_membro'),
    path('gruppi/membro/<int:membro_id>/rimuovi/', views.rimuovi_membro, name='rimuovi_membro'),
    path('gruppi/inviti/<int:invito_id>/<str:azione>/', views.gestisci_invito, name='gestisci_invito'),
    path('gruppi/inviti/<int:invito_id>/annulla/', views.annulla_invito, name='annulla_invito'),
    path('gruppi/inviti/attiva/<uuid:token>/', views.attiva_invito, name='attiva_invito'),

    # Ricerca
    path('ricerca/', views.ricerca, name='ricerca'),
    path('invita-utente/<int:user_id>/', views.invita_utente, name='invita_utente'),

    # Profilo
    path('profilo/modifica/', views.modifica_profilo, name='modifica_profilo'),  # Metti questo prima
    path('profilo/', views.profilo, name='profilo'),
    path('profilo/<str:username>/', views.profilo, name='profilo_utente'),
    path('gruppi/<int:gruppo_id>/modifica-immagine/', views.modifica_immagine_gruppo, name='modifica_immagine_gruppo'),

    # Meteo
    path('apiario/<int:apiario_id>/meteo/', views.visualizza_meteo_apiario, name='visualizza_meteo_apiario'),
    path('apiario/<int:apiario_id>/meteo/grafici/', views.grafici_meteo_apiario, name='grafici_meteo_apiario'),
    path('mappa/meteo/', views.mappa_meteo, name='mappa_meteo'),
]
