"""Test di regressione sui flussi segnalati dagli utenti dell'app.

Coprono due aree:

1. Melari e smielatura — il ciclo posiziona → rimuovi → registra smielatura,
   con la verifica che il melario finisca in stato 'smielato' e non resti
   contato fra i "da smielare".
2. Alimentazioni — creazione singola e multipla via API, e il controllo di
   accesso sulla colonia in scrittura.

Eseguire con:  python manage.py test core
"""

from datetime import date

from django.contrib.auth.models import User
from django.test import TestCase
from rest_framework.test import APIClient

from .models import (
    Alimentazione,
    Apiario,
    Arnia,
    Colonia,
    Melario,
    Smielatura,
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
