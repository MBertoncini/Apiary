"""Test del flusso cantina → vendite e della produzione per colonia.

Coprono i difetti emersi dalla revisione del flusso smielatura → maturatore →
contenitore → vasetti → vendita:

1. Vendite: le righe viaggiano con la vendita, scaricano i vasetti dai lotti
   e li restituiscono quando la vendita viene modificata o eliminata.
2. Maturatori e lotti: correzioni ed eliminazioni riallineano i kg a monte.
3. Produzione per colonia: i kg della smielatura vengono ripartiti fra i
   melari e restano attribuiti alla colonia che li ha prodotti.
4. Dataset ML: meteo e fioriture seguono gli spostamenti della colonia.

Eseguire con:  python manage.py test core.test_cantina
"""

from datetime import date, timedelta
from decimal import Decimal

from django.test import TestCase
from rest_framework.test import APIClient

from .ambiente import esposizione_da_gradiente
from .models import (
    ContenitoreStoccaggio, DettaglioVendita, Fioritura, Invasettamento,
    Maturatore, Melario, MeteoGiornaliero, NomadismoEvent, PesataMelario,
    Smielatura, SmielaturaMelario, Vendita,
)
from .tests import _crea_apiario, _crea_colonia


class _Base(TestCase):
    def setUp(self):
        self.user, self.apiario = _crea_apiario('cantiniere')
        self.colonia = _crea_colonia(self.apiario, numero=1)
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    def _smielatura(self, kg='40.00'):
        return Smielatura.objects.create(
            data=date(2026, 7, 20), apiario=self.apiario, quantita_miele=Decimal(kg),
            tipo_miele='Acacia', utente=self.user)

    def _lotto(self, numero=20, formato=500, giorno=1, tipo='Acacia'):
        sm = self._smielatura()
        return Invasettamento.objects.create(
            data=date(2026, 8, giorno), smielatura=sm, tipo_miele=tipo,
            formato_vasetto=formato, numero_vasetti=numero, utente=self.user)

    def _riga(self, quantita, tipo='Acacia', formato=500, prezzo='6.00'):
        return {'categoria': 'miele', 'tipo_miele': tipo, 'formato_vasetto': formato,
                'quantita': quantita, 'prezzo_unitario': prezzo}

    def _vendita(self, righe, **extra):
        body = {'data': '2026-09-01', 'canale': 'privato', 'pagamento': 'contanti',
                'acquirente_nome': 'Mario', 'dettagli': righe, **extra}
        return self.client.post('/api/v1/vendite/', body, format='json')


class VenditaLottiTests(_Base):
    def test_la_vendita_scarica_i_lotti_dal_piu_vecchio(self):
        vecchio = self._lotto(numero=5, giorno=1)
        nuovo = self._lotto(numero=20, giorno=10)
        resp = self._vendita([self._riga(8)])
        self.assertEqual(resp.status_code, 201, resp.content)
        self.assertEqual(len(resp.json()['dettagli']), 1)
        self.assertEqual(resp.json()['totale'], 48.0)
        vecchio.refresh_from_db()
        nuovo.refresh_from_db()
        self.assertEqual(vecchio.numero_vasetti_venduti, 5)
        self.assertEqual(vecchio.stato, 'venduto')
        self.assertEqual(nuovo.numero_vasetti_venduti, 3)
        # Lo storico di produzione non cambia.
        self.assertEqual(vecchio.numero_vasetti, 5)

    def test_modificare_la_vendita_non_duplica_le_righe(self):
        lotto = self._lotto(numero=20)
        vendita_id = self._vendita([self._riga(8)]).json()['id']
        resp = self.client.put(
            f'/api/v1/vendite/{vendita_id}/',
            {'data': '2026-09-02', 'canale': 'privato', 'pagamento': 'contanti',
             'acquirente_nome': 'Mario', 'dettagli': [self._riga(3)]},
            format='json')
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertEqual(len(resp.json()['dettagli']), 1)
        self.assertEqual(DettaglioVendita.objects.filter(vendita_id=vendita_id).count(), 1)
        lotto.refresh_from_db()
        self.assertEqual(lotto.numero_vasetti_venduti, 3)

    def test_eliminare_la_vendita_restituisce_i_vasetti(self):
        lotto = self._lotto(numero=6)
        vendita_id = self._vendita([self._riga(6)]).json()['id']
        lotto.refresh_from_db()
        self.assertEqual(lotto.stato, 'venduto')
        resp = self.client.delete(f'/api/v1/vendite/{vendita_id}/')
        self.assertEqual(resp.status_code, 204)
        lotto.refresh_from_db()
        self.assertEqual(lotto.numero_vasetti_venduti, 0)
        self.assertEqual(lotto.stato, 'disponibile')

    def test_vendita_senza_cantina_resta_possibile(self):
        """Chi non tiene i lotti in cantina deve poter registrare la vendita."""
        resp = self._vendita([self._riga(4, tipo='Castagno'),
                              {'categoria': 'cera', 'quantita': 1, 'prezzo_unitario': '10'}])
        self.assertEqual(resp.status_code, 201, resp.content)
        self.assertEqual(len(resp.json()['dettagli']), 2)

    def test_riga_non_valida_non_lascia_vendite_a_meta(self):
        self._lotto(numero=6)
        resp = self._vendita([self._riga(2), self._riga(0)])
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(Vendita.objects.count(), 0)

    def test_client_vecchio_senza_dettagli_non_tocca_le_righe(self):
        vendita_id = self._vendita([self._riga(2, tipo='Castagno')]).json()['id']
        resp = self.client.put(
            f'/api/v1/vendite/{vendita_id}/',
            {'data': '2026-09-03', 'canale': 'privato', 'pagamento': 'contanti',
             'acquirente_nome': 'Mario'}, format='json')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(DettaglioVendita.objects.filter(vendita_id=vendita_id).count(), 1)


class MaturatoreKgTests(_Base):
    def _crea(self, sm, kg='30'):
        resp = self.client.post('/api/v1/maturatori/', {
            'nome': 'M1', 'tipo_miele': 'Acacia', 'capacita_kg': 100, 'kg_attuali': kg,
            'giorni_maturazione': 400, 'data_inizio': str(date.today()),
            'stato': 'in_maturazione', 'smielatura': sm.id}, format='json')
        self.assertEqual(resp.status_code, 201, resp.content)
        return resp.json()['id']

    def test_eliminare_un_maturatore_libera_la_smielatura(self):
        sm = self._smielatura('40')
        mid = self._crea(sm, '30')
        sm.refresh_from_db()
        self.assertEqual(sm.kg_trasferiti, Decimal('30'))
        self.client.delete(f'/api/v1/maturatori/{mid}/')
        sm.refresh_from_db()
        self.assertEqual(sm.kg_trasferiti, Decimal('0'))

    def test_correggere_i_kg_riallinea_la_smielatura(self):
        sm = self._smielatura('40')
        mid = self._crea(sm, '30')
        resp = self.client.patch(f'/api/v1/maturatori/{mid}/', {'kg_attuali': 25}, format='json')
        self.assertEqual(resp.status_code, 200, resp.content)
        sm.refresh_from_db()
        self.assertEqual(sm.kg_trasferiti, Decimal('25'))
        resp = self.client.patch(f'/api/v1/maturatori/{mid}/', {'kg_attuali': 45}, format='json')
        self.assertEqual(resp.status_code, 400)

    def test_trasferimento_e_modifica_non_riaprono_il_maturatore(self):
        sm = self._smielatura('40')
        mid = self._crea(sm, '30')
        resp = self.client.post(f'/api/v1/maturatori/{mid}/trasferisci/', {
            'contenitori': [{'tipo': 'secchio', 'nome': 'S1', 'capacita_kg': 30, 'kg_attuali': 30}],
        }, format='json')
        self.assertEqual(resp.status_code, 200, resp.content)
        m = Maturatore.objects.get(pk=mid)
        self.assertEqual(m.stato, 'svuotato')
        # Il trasferimento a valle non restituisce kg alla smielatura.
        sm.refresh_from_db()
        self.assertEqual(sm.kg_trasferiti, Decimal('30'))
        # Le vecchie versioni dell'app rimandano sempre 'in_maturazione'.
        self.client.patch(f'/api/v1/maturatori/{mid}/',
                          {'nome': 'Nuovo nome', 'stato': 'in_maturazione'}, format='json')
        m.refresh_from_db()
        self.assertEqual(m.stato, 'svuotato')


class LottiTests(_Base):
    def _contenitore(self, kg='30'):
        return ContenitoreStoccaggio.objects.create(
            utente=self.user, nome='S1', tipo='secchio', capacita_kg=Decimal('30'),
            kg_attuali=Decimal(kg), tipo_miele='Acacia', data_riempimento=date(2026, 8, 1))

    def _invasetta(self, c, numero=20):
        resp = self.client.post(
            f'/api/v1/contenitori-stoccaggio/{c.id}/invasetta/',
            {'formato_vasetto': 500, 'numero_vasetti': numero}, format='json')
        self.assertEqual(resp.status_code, 201, resp.content)
        return resp.json()['id']

    def test_eliminare_un_lotto_restituisce_i_kg_al_contenitore(self):
        c = self._contenitore('30')
        lotto_id = self._invasetta(c, 20)
        c.refresh_from_db()
        self.assertEqual(c.kg_attuali, Decimal('20'))
        self.assertEqual(c.stato, 'parziale')
        self.client.delete(f'/api/v1/invasettamenti/{lotto_id}/')
        c.refresh_from_db()
        self.assertEqual(c.kg_attuali, Decimal('30'))
        self.assertEqual(c.stato, 'pieno')

    def test_lotto_di_cantina_modificabile(self):
        c = self._contenitore('30')
        lotto_id = self._invasetta(c, 20)
        resp = self.client.put(f'/api/v1/invasettamenti/{lotto_id}/', {
            'data': '2026-08-05', 'tipo_miele': 'Acacia', 'formato_vasetto': 500,
            'numero_vasetti': 30, 'lotto': 'L1'}, format='json')
        self.assertEqual(resp.status_code, 200, resp.content)
        c.refresh_from_db()
        self.assertEqual(c.kg_attuali, Decimal('15'))
        # Più vasetti di quanti il contenitore ne regga: rifiutato.
        resp = self.client.patch(f'/api/v1/invasettamenti/{lotto_id}/',
                                 {'numero_vasetti': 100}, format='json')
        self.assertEqual(resp.status_code, 400)

    def test_lotto_resta_visibile_senza_contenitore(self):
        c = self._contenitore('30')
        lotto_id = self._invasetta(c, 20)
        self.client.delete(f'/api/v1/contenitori-stoccaggio/{c.id}/')
        ids = [r['id'] for r in self.client.get('/api/v1/invasettamenti/').json()['results']]
        self.assertIn(lotto_id, ids)

    def test_lotto_diretto_scala_la_smielatura(self):
        sm = self._smielatura('10')
        body = {'smielatura': sm.id, 'data': '2026-08-01', 'tipo_miele': 'Acacia',
                'formato_vasetto': 500, 'numero_vasetti': 12}
        resp = self.client.post('/api/v1/invasettamenti/', body, format='json')
        self.assertEqual(resp.status_code, 201, resp.content)
        sm.refresh_from_db()
        self.assertEqual(sm.kg_trasferiti, Decimal('6'))
        # Restano 4 kg: altri 12 vasetti da 500 g non ci stanno.
        resp = self.client.post('/api/v1/invasettamenti/', body, format='json')
        self.assertEqual(resp.status_code, 400)
        self.client.delete(f"/api/v1/invasettamenti/{Invasettamento.objects.get().id}/")
        sm.refresh_from_db()
        self.assertEqual(sm.kg_trasferiti, Decimal('0'))


class ProduzionePerColoniaTests(_Base):
    def setUp(self):
        super().setUp()
        self.colonia2 = _crea_colonia(self.apiario, numero=2)

    def _melario(self, colonia, telaini=10, tipo='standard'):
        return Melario.objects.create(
            colonia=colonia, posizione=1, numero_telaini=telaini, tipo_melario=tipo,
            data_posizionamento=date(2026, 5, 1), stato='posizionato')

    def _registra(self, melari, kg='30'):
        resp = self.client.post('/api/v1/smielature/', {
            'data': '2026-07-21', 'apiario': self.apiario.id, 'tipo_miele': 'Acacia',
            'quantita_miele': kg, 'melari': [m.id for m in melari]}, format='json')
        self.assertEqual(resp.status_code, 201, resp.content)
        return resp.json()['id']

    def _kg(self, sid):
        return {r.melario_id: r.kg_miele
                for r in SmielaturaMelario.objects.filter(smielatura_id=sid)}

    def test_ripartizione_per_telaini_e_colonia_fissata(self):
        a = self._melario(self.colonia, telaini=10)
        b = self._melario(self.colonia2, telaini=10, tipo='meta')
        sid = self._registra([a, b], kg='30')
        kg = self._kg(sid)
        self.assertEqual(kg[a.id], Decimal('20.00'))
        self.assertEqual(kg[b.id], Decimal('10.00'))
        riga = SmielaturaMelario.objects.get(smielatura_id=sid, melario=a)
        self.assertEqual(riga.colonia_id, self.colonia.id)

    def test_ripartizione_per_pesate(self):
        a = self._melario(self.colonia)
        b = self._melario(self.colonia2)
        for m, netto in ((a, '18'), (b, '6')):
            PesataMelario.objects.create(
                melario=m, colonia=m.colonia, data=date(2026, 7, 20), tipo='rimozione',
                peso_lordo_kg=Decimal(netto) + 4, tara_kg=Decimal('4'), utente=self.user)
        sid = self._registra([a, b], kg='20')
        kg = self._kg(sid)
        self.assertEqual(kg[a.id], Decimal('15.00'))
        self.assertEqual(kg[b.id], Decimal('5.00'))
        self.assertEqual(PesataMelario.objects.filter(smielatura_id=sid).count(), 2)

    def test_correzione_manuale_e_cambio_quantita(self):
        a = self._melario(self.colonia)
        b = self._melario(self.colonia2)
        sid = self._registra([a, b], kg='30')
        resp = self.client.put(f'/api/v1/smielature/{sid}/ripartizione/',
                               {'righe': [{'melario': a.id, 'kg_miele': 22}]}, format='json')
        self.assertEqual(resp.status_code, 200, resp.content)
        kg = self._kg(sid)
        self.assertEqual((kg[a.id], kg[b.id]), (Decimal('22.00'), Decimal('8.00')))
        # Cambiando il raccolto, il valore manuale resta e l'altro si adegua.
        self.client.patch(f'/api/v1/smielature/{sid}/', {'quantita_miele': '40'}, format='json')
        kg = self._kg(sid)
        self.assertEqual((kg[a.id], kg[b.id]), (Decimal('22.00'), Decimal('18.00')))
        # Più kg del raccolto: rifiutato.
        resp = self.client.put(f'/api/v1/smielature/{sid}/ripartizione/',
                               {'righe': [{'melario': a.id, 'kg_miele': 99}]}, format='json')
        self.assertEqual(resp.status_code, 400)
        # Tornando all'automatico si divide di nuovo a metà.
        self.client.put(f'/api/v1/smielature/{sid}/ripartizione/',
                        {'righe': [{'melario': a.id, 'kg_miele': None}]}, format='json')
        kg = self._kg(sid)
        self.assertEqual((kg[a.id], kg[b.id]), (Decimal('20.00'), Decimal('20.00')))

    def test_il_dataset_attribuisce_alla_colonia_che_ha_prodotto(self):
        from .ml.dataset import build_colonia_dataset
        a = self._melario(self.colonia)
        sid = self._registra([a], kg='12')
        # Il melario viene poi riusato su un'altra colonia.
        Melario.objects.filter(pk=a.pk).update(colonia=self.colonia2)
        eventi = build_colonia_dataset(self.colonia)['smielature_eventi']
        self.assertEqual([(e['smielatura_id'], e['kg_colonia']) for e in eventi], [(sid, 12.0)])
        self.assertTrue(eventi[0]['kg_attribuiti_completi'])
        self.assertEqual(build_colonia_dataset(self.colonia2)['smielature_eventi'], [])


class DatasetAmbienteTests(_Base):
    def test_meteo_segue_gli_spostamenti(self):
        from .ml.dataset import build_colonia_dataset
        _, altro = _crea_apiario('vicino', nome='Montagna')
        altro.proprietario = self.user
        altro.altitudine_m = 900.0
        altro.esposizione = 'S'
        altro.save()
        oggi = date.today()
        cambio = oggi - timedelta(days=10)
        for apiario in (self.apiario, altro):
            for giorni in (20, 5):
                MeteoGiornaliero.objects.create(
                    apiario=apiario, data=oggi - timedelta(days=giorni), temp_mean=20.0)
        # Arrivata in `self.apiario` dieci giorni fa, prima era in montagna.
        NomadismoEvent.objects.create(
            colonia=self.colonia, apiario_origine=altro, apiario_destinazione=self.apiario,
            data_spostamento=cambio, utente=self.user)
        ds = build_colonia_dataset(self.colonia)
        per_giorno = {m['data']: m['apiario_id'] for m in ds['meteo_giornaliero']}
        self.assertEqual(per_giorno[oggi - timedelta(days=20)], altro.id)
        self.assertEqual(per_giorno[oggi - timedelta(days=5)], self.apiario.id)
        self.assertEqual(len(ds['meteo_giornaliero']), 2)
        montagna = next(a for a in ds['apiari'] if a['id'] == altro.id)
        self.assertEqual((montagna['altitudine_m'], montagna['esposizione']), (900.0, 'S'))

    def test_spostare_un_arnia_registra_il_nomadismo(self):
        _, altro = _crea_apiario('altro', nome='Altro')
        arnia = self.colonia.arnia
        arnia.apiario = altro
        arnia.save()
        ev = NomadismoEvent.objects.get(colonia=self.colonia)
        self.assertEqual((ev.apiario_origine_id, ev.apiario_destinazione_id),
                         (self.apiario.id, altro.id))

    def test_fioriture_vicine(self):
        from .ml.dataset import build_colonia_dataset
        self.apiario.latitudine = Decimal('45.0')
        self.apiario.longitudine = Decimal('9.0')
        self.apiario.altitudine_m = 100.0
        self.apiario.esposizione = 'piano'
        self.apiario.monitoraggio_meteo = False
        self.apiario.save()
        vicina = Fioritura.objects.create(
            pianta='Tiglio', data_inizio=date(2026, 6, 1), latitudine=Decimal('45.01'),
            longitudine=Decimal('9.0'), creatore=self.user)
        Fioritura.objects.create(
            pianta='Castagno', data_inizio=date(2026, 6, 1), latitudine=Decimal('45.2'),
            longitudine=Decimal('9.0'), creatore=self.user)
        vicine = build_colonia_dataset(self.colonia)['fioriture_vicine']
        self.assertEqual([f['id'] for f in vicine], [vicina.id])
        self.assertAlmostEqual(vicine[0]['distanza_km'], 1.11, places=1)


class EsposizioneTests(TestCase):
    def test_versante_rivolto_a_sud(self):
        # Il terreno sale verso nord (10 m ogni 100 m): scende verso sud.
        pendenza, esposizione = esposizione_da_gradiente(0.0, 0.1)
        self.assertEqual(esposizione, 'S')
        self.assertAlmostEqual(pendenza, 5.7, places=1)

    def test_versante_rivolto_a_ovest_e_piano(self):
        self.assertEqual(esposizione_da_gradiente(0.1, 0.0)[1], 'O')
        self.assertEqual(esposizione_da_gradiente(0.001, 0.001)[1], 'piano')
