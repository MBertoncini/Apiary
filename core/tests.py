"""Test di regressione sui flussi segnalati dagli utenti dell'app.

Coprono cinque aree:

1. Melari e smielatura — il ciclo posiziona → rimuovi → registra smielatura,
   con la verifica che il melario finisca in stato 'smielato' e non resti
   contato fra i "da smielare".
2. Alimentazioni — creazione singola e multipla via API, e il controllo di
   accesso sulla colonia in scrittura.
3. Colonie e contenitori — niente colonie attive orfane o duplicate quando si
   elimina, sposta o riusa un'arnia, e il conteggio delle regine attive che ne
   dipende.
4. Spese attrezzatura — la spesa di acquisto automatica segue il prezzo
   dell'attrezzatura, così azzerarlo la toglie dal bilancio.
5. Storico regine — aperto alla creazione, chiuso alla sostituzione o alla
   chiusura della colonia, e mai cancellato insieme alla regina.

Eseguire con:  python manage.py test core
"""

from datetime import date
from decimal import Decimal
from io import StringIO

from django.contrib.auth.models import User
from django.core.cache import cache
from django.core.management import call_command
from django.test import TestCase
from rest_framework.test import APIClient

from .models import (
    Alimentazione,
    Apiario,
    Arnia,
    Attrezzatura,
    Colonia,
    Melario,
    Pagamento,
    Regina,
    Smielatura,
    SpesaAttrezzatura,
    StoriaRegine,
)


def _crea_apiario(username, nome='Apiario test'):
    user = User.objects.create_user(username=username, password='x-test-pw-123')
    apiario = Apiario.objects.create(nome=nome, proprietario=user)
    return user, apiario


def _crea_colonia(apiario, numero):
    arnia = Arnia.objects.create(
        apiario=apiario,
        numero=numero,
        colore='giallo',
        colore_hex='#F5A623',
        data_installazione=date(2026, 3, 1),
    )
    return Colonia.objects.create(
        apiario=apiario,
        arnia=arnia,
        utente=apiario.proprietario,
        data_inizio=date(2026, 3, 1),
    )


class MelarioSmielaturaFlowTests(TestCase):
    """Il ciclo di vita del melario dal posizionamento alla smielatura."""

    def setUp(self):
        self.user, self.apiario = _crea_apiario('apicoltore')
        self.colonia = _crea_colonia(self.apiario, numero=1)
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    def _crea_melario(self, posizione=1):
        return Melario.objects.create(
            colonia=self.colonia,
            posizione=posizione,
            data_posizionamento=date(2026, 5, 1),
            stato='posizionato',
        )

    def test_melario_esposto_con_arnia_e_apiario(self):
        """La lista melari deve portare arnia_id/apiario_id.

        Il form smielatura filtra i melari per apiario proprio su questi
        campi: se mancano, i melari rimossi diventano inselezionabili.
        """
        melario = self._crea_melario()
        resp = self.client.get('/api/v1/melari/')
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        riga = next(m for m in data['results'] if m['id'] == melario.id)
        self.assertEqual(riga['arnia_id'], self.colonia.arnia_id)
        self.assertEqual(riga['apiario_id'], self.apiario.id)
        self.assertEqual(riga['stato'], 'posizionato')

    def test_rimozione_conserva_la_colonia(self):
        """PATCH stato='rimosso' non deve staccare il melario dalla colonia."""
        melario = self._crea_melario()
        resp = self.client.patch(
            f'/api/v1/melari/{melario.id}/',
            {'stato': 'rimosso', 'data_rimozione': '2026-07-20'},
            format='json',
        )
        self.assertEqual(resp.status_code, 200)
        melario.refresh_from_db()
        self.assertEqual(melario.stato, 'rimosso')
        self.assertEqual(melario.colonia_id, self.colonia.id)
        # Senza colonia il serializer non saprebbe più risalire all'apiario.
        self.assertEqual(resp.json()['apiario_id'], self.apiario.id)

    def test_smielatura_azzera_i_melari_da_smielare(self):
        """Il caso segnalato: posiziona, rimuovi, smiela → nessun residuo."""
        melari = [self._crea_melario(posizione=i) for i in (1, 2)]
        for m in melari:
            self.client.patch(
                f'/api/v1/melari/{m.id}/',
                {'stato': 'rimosso', 'data_rimozione': '2026-07-20'},
                format='json',
            )

        da_smielare = Melario.objects.filter(
            colonia__apiario=self.apiario,
            stato__in=['rimosso', 'in_smielatura'],
        ).count()
        self.assertEqual(da_smielare, 2)

        resp = self.client.post(
            '/api/v1/smielature/',
            {
                'data': '2026-07-21',
                'apiario': self.apiario.id,
                'melari': [m.id for m in melari],
                'quantita_miele': '18.50',
                'tipo_miele': 'millefiori',
            },
            format='json',
        )
        self.assertEqual(resp.status_code, 201, resp.content)

        for m in melari:
            m.refresh_from_db()
            self.assertEqual(m.stato, 'smielato')

        residui = Melario.objects.filter(
            colonia__apiario=self.apiario,
            stato__in=['rimosso', 'in_smielatura'],
        ).count()
        self.assertEqual(residui, 0)

    def test_smielatura_espone_gli_id_dei_melari(self):
        """`melari` sulla produzione è la fonte del contatore lato app.

        L'app incrocia gli id qui elencati con i melari in stato rimosso per
        azzerare il contatore anche prima che il refresh porti lo stato a
        'smielato'.
        """
        melario = self._crea_melario()
        self.client.patch(
            f'/api/v1/melari/{melario.id}/',
            {'stato': 'rimosso'},
            format='json',
        )
        self.client.post(
            '/api/v1/smielature/',
            {
                'data': '2026-07-21',
                'apiario': self.apiario.id,
                'melari': [melario.id],
                'quantita_miele': '9.00',
                'tipo_miele': 'acacia',
            },
            format='json',
        )
        resp = self.client.get('/api/v1/smielature/')
        riga = resp.json()['results'][0]
        self.assertIn(melario.id, riga['melari'])
        self.assertEqual(riga['melari_count'], 1)

    def test_delete_smielatura_ripristina_lo_stato_originale(self):
        """Annullare la smielatura riporta il melario a 'rimosso', non oltre."""
        melario = self._crea_melario()
        self.client.patch(
            f'/api/v1/melari/{melario.id}/', {'stato': 'rimosso'}, format='json'
        )
        resp = self.client.post(
            '/api/v1/smielature/',
            {
                'data': '2026-07-21',
                'apiario': self.apiario.id,
                'melari': [melario.id],
                'quantita_miele': '9.00',
                'tipo_miele': 'acacia',
            },
            format='json',
        )
        smielatura_id = resp.json()['id']
        self.client.delete(f'/api/v1/smielature/{smielatura_id}/')

        melario.refresh_from_db()
        self.assertEqual(melario.stato, 'rimosso')
        self.assertFalse(Smielatura.objects.filter(pk=smielatura_id).exists())


class AlimentazioneApiTests(TestCase):
    """CRUD alimentazioni e inserimento multiplo dall'app."""

    def setUp(self):
        self.user, self.apiario = _crea_apiario('nutritore')
        self.colonie = [_crea_colonia(self.apiario, n) for n in (1, 2, 3)]
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    def _payload(self, colonia, **over):
        base = {
            'colonia': colonia.id,
            'data': '2026-09-01',
            'tipo': 'sciroppo_2_1',
            'scopo': 'invernale',
            'quantita_kg': '2.50',
            'note': 'Prima somministrazione autunnale',
        }
        base.update(over)
        return base

    def test_creazione_e_note_restituite(self):
        """Le note salvate devono tornare nella risposta e nella lista.

        L'utente segnalava di non rivedere più il testo delle note dopo
        l'inserimento.
        """
        resp = self.client.post(
            '/api/v1/alimentazioni/', self._payload(self.colonie[0]), format='json'
        )
        self.assertEqual(resp.status_code, 201, resp.content)
        self.assertEqual(resp.json()['note'], 'Prima somministrazione autunnale')

        lista = self.client.get('/api/v1/alimentazioni/').json()['results']
        self.assertEqual(lista[0]['note'], 'Prima somministrazione autunnale')

    def test_lista_espone_colonia_e_apiario(self):
        """Servono per etichettare le righe e per le aggregazioni per apiario."""
        self.client.post(
            '/api/v1/alimentazioni/', self._payload(self.colonie[0]), format='json'
        )
        riga = self.client.get('/api/v1/alimentazioni/').json()['results'][0]
        self.assertEqual(riga['colonia_display'], 'Arnia 1')
        self.assertEqual(riga['apiario'], self.apiario.id)
        self.assertEqual(riga['apiario_nome'], self.apiario.nome)
        self.assertEqual(riga['tipo_display'], 'Sciroppo 2:1 (invernale)')
        self.assertEqual(riga['scopo_display'], 'Riserve invernali')

    def test_inserimento_multiplo_una_riga_per_colonia(self):
        """L'app cicla sulle colonie selezionate: una POST per ciascuna."""
        for colonia in self.colonie:
            resp = self.client.post(
                '/api/v1/alimentazioni/', self._payload(colonia), format='json'
            )
            self.assertEqual(resp.status_code, 201, resp.content)

        self.assertEqual(Alimentazione.objects.count(), 3)
        colonie_servite = set(
            Alimentazione.objects.values_list('colonia_id', flat=True)
        )
        self.assertEqual(colonie_servite, {c.id for c in self.colonie})

    def test_modifica_via_patch(self):
        """La modifica deve poter cambiare quantità, tipo e note."""
        creata = self.client.post(
            '/api/v1/alimentazioni/', self._payload(self.colonie[0]), format='json'
        ).json()
        resp = self.client.patch(
            f"/api/v1/alimentazioni/{creata['id']}/",
            {'quantita_kg': '4.00', 'tipo': 'candito', 'note': 'Corretto'},
            format='json',
        )
        self.assertEqual(resp.status_code, 200, resp.content)
        body = resp.json()
        self.assertEqual(body['quantita_kg'], '4.00')
        self.assertEqual(body['tipo'], 'candito')
        self.assertEqual(body['note'], 'Corretto')
        # La colonia non deve cambiare per effetto di una PATCH parziale.
        self.assertEqual(body['colonia'], self.colonie[0].id)

    def test_scopo_vuoto_accettato(self):
        """L'app invia scopo='' quando l'utente non lo seleziona."""
        resp = self.client.post(
            '/api/v1/alimentazioni/',
            self._payload(self.colonie[0], scopo=''),
            format='json',
        )
        self.assertEqual(resp.status_code, 201, resp.content)
        self.assertEqual(resp.json()['scopo'], '')

    def test_filtro_per_colonia(self):
        """Il pre-filtro dal dettaglio colonia usa ?colonia=<id>."""
        self.client.post(
            '/api/v1/alimentazioni/', self._payload(self.colonie[0]), format='json'
        )
        self.client.post(
            '/api/v1/alimentazioni/', self._payload(self.colonie[1]), format='json'
        )
        resp = self.client.get(f'/api/v1/alimentazioni/?colonia={self.colonie[0].id}')
        righe = resp.json()['results']
        self.assertEqual(len(righe), 1)
        self.assertEqual(righe[0]['colonia'], self.colonie[0].id)


class AlimentazioneAccessoTests(TestCase):
    """Isolamento fra utenti sulle scritture del dataset ML."""

    def setUp(self):
        _, self.apiario_a = _crea_apiario('alice', 'Apiario Alice')
        self.colonia_a = _crea_colonia(self.apiario_a, 1)
        self.bob, self.apiario_b = _crea_apiario('bob', 'Apiario Bob')
        self.client = APIClient()
        self.client.force_authenticate(self.bob)

    def test_non_si_puo_alimentare_la_colonia_altrui(self):
        resp = self.client.post(
            '/api/v1/alimentazioni/',
            {
                'colonia': self.colonia_a.id,
                'data': '2026-09-01',
                'tipo': 'candito',
                'quantita_kg': '1.00',
            },
            format='json',
        )
        self.assertEqual(resp.status_code, 400, resp.content)
        self.assertEqual(Alimentazione.objects.count(), 0)

    def test_la_lista_non_mostra_le_alimentazioni_altrui(self):
        Alimentazione.objects.create(
            colonia=self.colonia_a,
            data=date(2026, 9, 1),
            tipo='candito',
            quantita_kg=1,
            utente=self.apiario_a.proprietario,
        )
        resp = self.client.get('/api/v1/alimentazioni/')
        self.assertEqual(resp.json()['results'], [])


class ColoniaContenitoreTests(TestCase):
    """Una colonia attiva per box, sempre nell'apiario del suo box."""

    def setUp(self):
        cache.clear()
        self.user, self.apiario = _crea_apiario('coloniauser')
        self.altro_apiario = Apiario.objects.create(nome='Altro', proprietario=self.user)
        self.colonia = _crea_colonia(self.apiario, numero=1)
        self.arnia = self.colonia.arnia
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    def _attive(self):
        return self.client.get('/api/v1/colonie/').json()['results']

    def test_eliminare_arnia_chiude_la_colonia(self):
        self.client.delete(f'/api/v1/arnie/{self.arnia.id}/')
        self.colonia.refresh_from_db()
        self.assertEqual(self.colonia.stato, 'eliminata')
        self.assertIsNotNone(self.colonia.data_fine)
        self.assertFalse(any(c['is_attiva'] for c in self._attive()))

    def test_spostare_arnia_di_apiario_sposta_la_colonia(self):
        self.arnia.apiario = self.altro_apiario
        self.arnia.save()
        self.colonia.refresh_from_db()
        self.assertEqual(self.colonia.apiario_id, self.altro_apiario.id)

    def test_seconda_colonia_nella_stessa_arnia_rifiutata(self):
        resp = self.client.post('/api/v1/colonie/', {
            'arnia': self.arnia.id, 'data_inizio': '2026-05-01',
        }, format='json')
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(Colonia.objects.filter(arnia=self.arnia).count(), 1)

    def test_nuova_colonia_dopo_chiusura_ammessa(self):
        self.colonia.stato = 'morta'
        self.colonia.data_fine = date(2026, 4, 1)
        self.colonia.save()
        resp = self.client.post('/api/v1/colonie/', {
            'arnia': self.arnia.id, 'data_inizio': '2026-05-01',
        }, format='json')
        self.assertEqual(resp.status_code, 201, resp.content)

    def test_sposta_contenitore_segue_apiario_e_rifiuta_box_occupato(self):
        occupante = _crea_colonia(self.altro_apiario, numero=2)
        resp = self.client.post(
            f'/api/v1/colonie/{self.colonia.id}/sposta_contenitore/',
            {'arnia': occupante.arnia_id}, format='json',
        )
        self.assertEqual(resp.status_code, 400)

        libera = Arnia.objects.create(
            apiario=self.altro_apiario, numero=3, data_installazione=date(2026, 3, 1),
        )
        resp = self.client.post(
            f'/api/v1/colonie/{self.colonia.id}/sposta_contenitore/',
            {'arnia': libera.id}, format='json',
        )
        self.assertEqual(resp.status_code, 200, resp.content)
        self.colonia.refresh_from_db()
        self.assertEqual(self.colonia.arnia_id, libera.id)
        self.assertEqual(self.colonia.apiario_id, self.altro_apiario.id)


class RegineAttiveStatsTests(TestCase):
    """Il widget conta solo le regine delle colonie vive e ancora in un box."""

    def setUp(self):
        cache.clear()
        self.user, self.apiario = _crea_apiario('regineuser')
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    def _regina(self, colonia):
        return Regina.objects.create(colonia=colonia, data_introduzione=date(2026, 3, 1))

    def test_conta_solo_regine_di_colonie_attive(self):
        viva = _crea_colonia(self.apiario, numero=1)
        morta = _crea_colonia(self.apiario, numero=2)
        orfana = _crea_colonia(self.apiario, numero=3)
        for c in (viva, morta, orfana):
            self._regina(c)
        morta.stato = 'morta'
        morta.data_fine = date(2026, 6, 1)
        morta.save()
        # Stato lasciato dai vecchi delete: colonia attiva senza box.
        Colonia.objects.filter(pk=orfana.pk).update(arnia=None)

        resp = self.client.get('/api/stats/widgets/regine_statistiche/')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()['regine_attive'], 1)

    def test_query_builder_regine(self):
        self._regina(_crea_colonia(self.apiario, numero=1))
        resp = self.client.post('/api/stats/query-builder/', {
            'entita': 'regine', 'aggregazione': 'none',
        }, format='json')
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertEqual(resp.json()['totale_righe'], 1)


class PulisciColonieCommandTests(TestCase):
    """Il comando ripara i dati lasciati incoerenti dalle versioni precedenti."""

    def setUp(self):
        self.user, self.apiario = _crea_apiario('pulizia')
        self.altro_apiario = Apiario.objects.create(nome='Altro', proprietario=self.user)

    def _run(self, *args):
        call_command('pulisci_colonie', *args, stdout=StringIO())

    def test_dry_run_non_scrive_e_apply_ripara(self):
        orfana = _crea_colonia(self.apiario, numero=1)
        Colonia.objects.filter(pk=orfana.pk).update(arnia=None)

        fuori_posto = _crea_colonia(self.apiario, numero=2)
        Arnia.objects.filter(pk=fuori_posto.arnia_id).update(apiario=self.altro_apiario)

        vecchia = _crea_colonia(self.apiario, numero=3)
        doppione = Colonia.objects.create(
            apiario=self.apiario, arnia=vecchia.arnia, utente=self.user,
            data_inizio=date(2026, 5, 1),
        )

        self._run()
        self.assertEqual(Colonia.objects.filter(stato='attiva').count(), 4)

        self._run('--apply')
        orfana.refresh_from_db()
        fuori_posto.refresh_from_db()
        vecchia.refresh_from_db()
        doppione.refresh_from_db()
        self.assertEqual(orfana.stato, 'eliminata')
        self.assertEqual(fuori_posto.apiario_id, self.altro_apiario.id)
        # Resta quella più recente, cioè quella che l'app mostra già.
        self.assertEqual(doppione.stato, 'attiva')
        self.assertEqual(vecchia.stato, 'eliminata')


    def test_a_parita_di_data_tiene_la_colonia_con_regina(self):
        con_regina = _crea_colonia(self.apiario, numero=1)
        Regina.objects.create(colonia=con_regina, data_introduzione=date(2026, 3, 1))
        # Doppio invio: stessa data, id più alto, nessuna storia.
        vuota = Colonia.objects.create(
            apiario=self.apiario, arnia=con_regina.arnia, utente=self.user,
            data_inizio=con_regina.data_inizio,
        )

        self._run('--apply')
        con_regina.refresh_from_db()
        vuota.refresh_from_db()
        self.assertEqual(con_regina.stato, 'attiva')
        self.assertEqual(vuota.stato, 'eliminata')


class SpesaAcquistoAttrezzaturaTests(TestCase):
    """La spesa di acquisto automatica segue il prezzo dell'attrezzatura."""

    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user(username='attrezzi', password='x-test-pw-123')
        self.client = APIClient()
        self.client.force_authenticate(self.user)
        resp = self.client.post('/api/v1/attrezzature/', {
            'nome': 'Dadant-Blatt #6', 'prezzo_acquisto': '60.00',
            'data_acquisto': '2026-07-17',
        }, format='json')
        self.assertEqual(resp.status_code, 201, resp.content)
        self.attrezzatura = Attrezzatura.objects.get(pk=resp.json()['id'])

    def _uscite(self):
        cache.clear()
        resp = self.client.get('/api/stats/widgets/bilancio_economico/?anno=2026')
        return sum(resp.json()['uscite'])

    def test_azzerare_il_prezzo_toglie_la_spesa_dal_bilancio(self):
        self.assertEqual(self._uscite(), 60)
        self.client.patch(f'/api/v1/attrezzature/{self.attrezzatura.id}/',
                          {'prezzo_acquisto': '0.00'}, format='json')
        self.assertFalse(SpesaAttrezzatura.objects.filter(attrezzatura=self.attrezzatura).exists())
        self.assertFalse(Pagamento.objects.filter(utente=self.user).exists())
        self.assertEqual(self._uscite(), 0)

    def test_cambiare_il_prezzo_aggiorna_spesa_e_pagamento(self):
        self.client.patch(f'/api/v1/attrezzature/{self.attrezzatura.id}/',
                          {'prezzo_acquisto': '75.00'}, format='json')
        spesa = SpesaAttrezzatura.objects.get(attrezzatura=self.attrezzatura)
        self.assertEqual(spesa.importo, Decimal('75.00'))
        self.assertEqual(Pagamento.objects.get(spesa_attrezzatura=spesa).importo, Decimal('75.00'))
        self.assertEqual(self._uscite(), 75)

    def test_spese_manuali_non_toccate(self):
        manuale = SpesaAttrezzatura.objects.create(
            attrezzatura=self.attrezzatura, tipo='altro', descrizione='pulizia',
            importo=Decimal('60.00'), data=date(2026, 7, 17), utente=self.user,
        )
        self.client.patch(f'/api/v1/attrezzature/{self.attrezzatura.id}/',
                          {'prezzo_acquisto': '0.00'}, format='json')
        self.assertTrue(SpesaAttrezzatura.objects.filter(pk=manuale.pk).exists())

    def test_comando_riallinea_i_dati_esistenti(self):
        # Stato lasciato dalle versioni precedenti: prezzo azzerato senza signal.
        Attrezzatura.objects.filter(pk=self.attrezzatura.pk).update(prezzo_acquisto=Decimal('0'))
        call_command('pulisci_pagamenti_attrezzature', stdout=StringIO())
        self.assertTrue(SpesaAttrezzatura.objects.filter(attrezzatura=self.attrezzatura).exists())
        call_command('pulisci_pagamenti_attrezzature', '--apply', stdout=StringIO())
        self.assertFalse(SpesaAttrezzatura.objects.filter(attrezzatura=self.attrezzatura).exists())
        self.assertEqual(self._uscite(), 0)


class StoriaRegineTests(TestCase):
    """Lo storico regine si apre, si chiude e sopravvive alla sostituzione."""

    def setUp(self):
        cache.clear()
        self.user, self.apiario = _crea_apiario('storiaregine')
        self.colonia = _crea_colonia(self.apiario, numero=1)
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    def _crea_regina(self):
        resp = self.client.post('/api/v1/regine/', {
            'colonia': self.colonia.id, 'data_introduzione': '2026-04-01',
        }, format='json')
        self.assertEqual(resp.status_code, 201, resp.content)
        return Regina.objects.get(pk=resp.json()['id'])

    def test_creare_una_regina_apre_lo_storico(self):
        regina = self._crea_regina()
        storia = StoriaRegine.objects.get(regina=regina)
        self.assertEqual(storia.colonia_id, self.colonia.id)
        self.assertEqual(storia.data_inizio, date(2026, 4, 1))
        self.assertIsNone(storia.data_fine)

    def test_sostituire_conserva_regina_e_storico(self):
        regina = self._crea_regina()
        resp = self.client.post(f'/api/v1/regine/{regina.id}/sostituisci/', {
            'motivo_fine': 'morta', 'data_fine': '2026-07-01',
        }, format='json')
        self.assertEqual(resp.status_code, 200, resp.content)

        regina.refresh_from_db()
        self.assertIsNone(regina.colonia_id)
        storia = StoriaRegine.objects.get(regina=regina)
        self.assertEqual(storia.data_fine, date(2026, 7, 1))
        self.assertEqual(storia.motivo_fine, 'morta')

        # Sparisce dagli elenchi e dal conteggio, resta nelle statistiche.
        self.assertEqual(self.client.get('/api/v1/regine/').json()['count'], 0)
        stats = self.client.get('/api/stats/widgets/regine_statistiche/?anno=2026').json()
        self.assertEqual(stats['regine_attive'], 0)
        self.assertEqual(stats['per_motivo'], [{'motivo': 'morta', 'count': 1}])
        self.assertEqual(stats['durata_media_mesi'], 3.0)

        # La colonia può ricevere la nuova regina.
        self._crea_regina()
        self.assertEqual(StoriaRegine.objects.filter(colonia=self.colonia).count(), 2)

    def test_chiudere_la_colonia_chiude_lo_storico(self):
        regina = self._crea_regina()
        resp = self.client.post(f'/api/v1/colonie/{self.colonia.id}/chiudi/', {
            'stato': 'morta', 'data_fine': '2026-08-01',
        }, format='json')
        self.assertEqual(resp.status_code, 200, resp.content)
        storia = StoriaRegine.objects.get(regina=regina)
        self.assertEqual(storia.data_fine, date(2026, 8, 1))

    def test_comando_ricostruisce_lo_storico_mancante(self):
        attiva = Regina.objects.create(colonia=self.colonia, data_introduzione=date(2026, 4, 1))
        chiusa_col = _crea_colonia(self.apiario, numero=2)
        vecchia = Regina.objects.create(colonia=chiusa_col, data_introduzione=date(2026, 3, 1))
        Colonia.objects.filter(pk=chiusa_col.pk).update(
            stato='morta', data_fine=date(2026, 6, 1), arnia=None)

        call_command('ricostruisci_storia_regine', stdout=StringIO())
        self.assertFalse(StoriaRegine.objects.exists())

        call_command('ricostruisci_storia_regine', '--apply', stdout=StringIO())
        self.assertIsNone(StoriaRegine.objects.get(regina=attiva).data_fine)
        self.assertEqual(StoriaRegine.objects.get(regina=vecchia).data_fine, date(2026, 6, 1))

        # Idempotente: una seconda esecuzione non aggiunge righe.
        call_command('ricostruisci_storia_regine', '--apply', stdout=StringIO())
        self.assertEqual(StoriaRegine.objects.count(), 2)

    def test_regine_sostituite_non_sono_orfane(self):
        from core.management.commands.link_orphan_regine import Command as LinkOrphan
        regina = self._crea_regina()
        self.client.post(f'/api/v1/regine/{regina.id}/sostituisci/',
                         {'motivo_fine': 'morta'}, format='json')
        orfana = Regina.objects.create(colonia=None, data_introduzione=date(2026, 4, 1))
        self.assertEqual(list(LinkOrphan()._orphans()), [orfana])


# ---------------------------------------------------------------------------
# 6. Login Google della dashboard web
# ---------------------------------------------------------------------------

from unittest import mock  # noqa: E402

from django.test import Client, override_settings  # noqa: E402
from django.urls import reverse  # noqa: E402


@override_settings(ALLOWED_HOSTS=['testserver'])
class GoogleLoginWebTests(TestCase):
    """Issue #1: dopo il popup Google la dashboard non si apriva mai."""

    ID_INFO = {
        'email': 'gtest@example.com',
        'email_verified': True,
        'given_name': 'G',
        'family_name': 'Test',
    }

    def _post(self, client, next_url=''):
        with mock.patch('google.oauth2.id_token.verify_oauth2_token',
                        return_value=self.ID_INFO):
            return client.post(
                reverse('google_login_web'),
                data={'credential': 'token', 'next': next_url},
                content_type='application/json',
            )

    def test_coop_consente_il_popup_google(self):
        # Con 'same-origin' (default Django) il popup non restituisce la
        # credenziale alla pagina di login.
        response = Client().get(reverse('login'), follow=True)
        self.assertEqual(response.headers.get('Cross-Origin-Opener-Policy'),
                         'same-origin-allow-popups')
        # Pulsante ufficiale (popup), non One Tap che Google puo' sopprimere.
        self.assertContains(response, 'google.accounts.id.renderButton')
        self.assertNotContains(response, 'google.accounts.id.prompt()')

    def test_login_crea_la_sessione(self):
        client = Client()
        response = self._post(client)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['redirect'], '/app/dashboard/')
        self.assertEqual(int(client.session['_auth_user_id']),
                         User.objects.get(email='gtest@example.com').pk)

    def test_redirect_su_next_interno(self):
        response = self._post(Client(), '/app/apiari/')
        self.assertEqual(response.json()['redirect'], '/app/apiari/')

    def test_next_esterno_ignorato(self):
        response = self._post(Client(), 'https://evil.example/x')
        self.assertEqual(response.json()['redirect'], '/app/dashboard/')


# ---------------------------------------------------------------------------
# 7. Quota AI: conteggio lato server, chiave personale, statistiche, reset
# ---------------------------------------------------------------------------

from datetime import timedelta  # noqa: E402

from django.utils import timezone  # noqa: E402

from .models import ActivationCode, Profilo  # noqa: E402

RISPOSTA_FINALE = {'candidates': [{'content': {'parts': [{'text': 'ciao'}]}}]}
RISPOSTA_TOOL = {'candidates': [{'content': {'parts': [
    {'functionCall': {'name': 'lista_arnie', 'args': {}}}]}}]}


class AiQuotaProxyTests(TestCase):
    """Il proxy Gemini conta la quota lato server: il client non puo'
    aggirarla saltando la telemetria."""

    def setUp(self):
        self.user = User.objects.create_user('quota', password='x')
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    def _profilo(self):
        return Profilo.objects.get(utente=self.user)

    def _proxy(self, risposta=RISPOSTA_FINALE, feature='chat', **extra):
        with mock.patch('core.ai_views.gemini_service.generate_raw',
                        return_value=(True, risposta, 200, 'gemini-3.8-flash')) as gen:
            resp = self.client.post(
                '/api/v1/ai/gemini-proxy/',
                {'feature': feature, 'payload': {'contents': []}, **extra},
                format='json',
            )
        return resp, gen

    def test_il_proxy_conta_senza_telemetria(self):
        for _ in range(10):
            resp, _gen = self._proxy()
            self.assertEqual(resp.status_code, 200)
        self.assertEqual(self._profilo().ai_chat_today, 10)
        # Undicesima chat del piano Base: rifiutata senza chiamare Gemini.
        resp, gen = self._proxy()
        self.assertEqual(resp.status_code, 429)
        self.assertTrue(resp.json()['quota_exceeded'])
        gen.assert_not_called()

    def test_la_telemetria_non_conta_due_volte(self):
        self._proxy()
        resp = self.client.post('/api/v1/ai/chat/', {'record_only': True}, format='json')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()['chat_today'], 1)
        self._proxy(feature='voice')
        resp = self.client.post('/api/v1/ai/record-voice-call/', {}, format='json')
        self.assertEqual(resp.json()['voice_today'], 1)
        p = self._profilo()
        self.assertEqual((p.ai_chat_today, p.ai_voice_today, p.ai_requests_today), (1, 1, 2))

    def test_i_giri_di_function_calling_non_consumano_la_chat(self):
        for _ in range(3):
            self._proxy(risposta=RISPOSTA_TOOL)
        self._proxy()
        p = self._profilo()
        self.assertEqual(p.ai_chat_today, 1)
        self.assertEqual(p.ai_proxy_calls_today, 4)

    def test_tetto_alle_chiamate_grezze(self):
        # Base: total 15 * 5 = 75 chiamate grezze al giorno.
        Profilo.objects.filter(utente=self.user).update(
            ai_proxy_calls_today=75,
            ai_requests_reset_at=timezone.now() + timedelta(hours=1))
        resp, gen = self._proxy(risposta=RISPOSTA_TOOL)
        self.assertEqual(resp.status_code, 429)
        gen.assert_not_called()

    def test_modelli_fuori_lista_ignorati(self):
        _resp, gen = self._proxy(models=['gemini-9-ultra-pro', 'gemini-3.6-flash'])
        self.assertEqual(gen.call_args.kwargs['models'], ['gemini-3.6-flash'])
        _resp, gen = self._proxy(models=['gemini-9-ultra-pro'])
        self.assertIsNone(gen.call_args.kwargs['models'])

    def test_chiave_personale_niente_limite_e_niente_conteggio(self):
        Profilo.objects.filter(utente=self.user).update(
            gemini_api_key='chiave-utente', ai_chat_today=10, ai_requests_today=15,
            ai_requests_reset_at=timezone.now() + timedelta(hours=1))
        self.client.force_authenticate(User.objects.get(pk=self.user.pk))
        resp, gen = self._proxy()
        self.assertEqual(resp.status_code, 200)
        # Usa la chiave dell'utente, mai quella di sistema.
        self.assertEqual(gen.call_args.kwargs['api_key'], 'chiave-utente')
        self.assertEqual(self._profilo().ai_chat_today, 10)

    def test_contatori_scaduti_valgono_zero(self):
        Profilo.objects.filter(utente=self.user).update(
            ai_chat_today=10, ai_requests_today=15, ai_stats_today=10,
            ai_proxy_calls_today=75,
            ai_requests_reset_at=timezone.now() - timedelta(minutes=1))
        quota = self.client.get('/api/v1/ai/quota/').json()
        self.assertEqual(quota['usage'], {
            'chat_today': 0, 'voice_today': 0, 'total_today': 0, 'stats_today': 0})
        resp, _gen = self._proxy()
        self.assertEqual(resp.status_code, 200)
        p = self._profilo()
        self.assertEqual((p.ai_chat_today, p.ai_requests_today, p.ai_stats_today,
                          p.ai_proxy_calls_today), (1, 1, 0, 1))
        self.assertGreater(p.ai_requests_reset_at, timezone.now())

    def test_salvare_l_utente_non_riscrive_i_contatori(self):
        user = User.objects.get(pk=self.user.pk)
        user.profilo  # carica il profilo in cache sull'istanza
        Profilo.objects.filter(utente=self.user).update(ai_chat_today=7)
        user.save()
        self.assertEqual(self._profilo().ai_chat_today, 7)


class AiQuotaStatsTests(TestCase):
    """Le domande AI nelle statistiche hanno una quota per utente."""

    def setUp(self):
        self.user = User.objects.create_user('stats', password='x')
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    def _chiedi(self, **extra):
        with mock.patch('statistiche.views.nl_query.text_to_sql',
                        return_value={'sql': 'SELECT 1 AS uno', 'raw': ''}) as t2s:
            resp = self.client.post('/api/stats/nl-query/',
                                    {'domanda': 'quante arnie ho?', **extra}, format='json')
        return resp, t2s

    def test_conta_e_blocca_al_limite(self):
        resp, _ = self._chiedi()
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()['stats_today'], 1)
        Profilo.objects.filter(utente=self.user).update(ai_stats_today=10)
        resp, t2s = self._chiedi()
        self.assertEqual(resp.status_code, 429)
        self.assertTrue(resp.json()['quota_exceeded'])
        t2s.assert_not_called()

    def test_chiave_groq_personale_usata_e_non_contata(self):
        Profilo.objects.filter(utente=self.user).update(
            ai_stats_today=10, ai_requests_reset_at=timezone.now() + timedelta(hours=1))
        resp, t2s = self._chiedi(groq_api_key='gsk_utente')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(t2s.call_args.kwargs['api_key'], 'gsk_utente')
        self.assertNotIn('stats_today', resp.json())
        self.assertEqual(Profilo.objects.get(utente=self.user).ai_stats_today, 10)


class ActivationCodeTests(TestCase):
    def test_codice_esaurito_rifiutato(self):
        ActivationCode.objects.create(code='PROMO', target_tier='apicoltore', max_uses=1)
        esiti = []
        for nome in ('uno', 'due'):
            client = APIClient()
            client.force_authenticate(User.objects.create_user(nome, password='x'))
            esiti.append(client.post('/api/v1/ai/activate-code/', {'code': 'promo'},
                                     format='json').status_code)
        self.assertEqual(esiti, [200, 410])
        self.assertEqual(ActivationCode.objects.get(code='PROMO').times_used, 1)
        self.assertEqual(Profilo.objects.get(utente__username='uno').ai_tier, 'apicoltore')
        self.assertEqual(Profilo.objects.get(utente__username='due').ai_tier, 'free')
