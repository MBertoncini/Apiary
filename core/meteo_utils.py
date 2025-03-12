# core/meteo_utils.py

import requests
from django.conf import settings
from django.utils import timezone
from datetime import datetime, timedelta
import time
import json
from django.core.cache import cache

from .models import DatiMeteo, PrevisioneMeteo, Apiario

def aggiorna_dati_meteo(apiario):
    """
    Recupera i dati meteo attuali per un apiario specifico e li salva nel database
    Utilizza la cache per evitare troppe chiamate API
    """
    # Verifica che l'apiario abbia coordinate valide e monitoraggio abilitato
    if not apiario.has_coordinates() or not apiario.monitoraggio_meteo:
        return None
    
    # Controlla la cache prima di chiamare l'API (cache di 30 minuti)
    cache_key = f"meteo_attuale_{apiario.id}"
    cached_data = cache.get(cache_key)
    if cached_data:
        print(f"Usando dati meteo in cache per apiario {apiario.id}")
        if 'json_data' in cached_data:
            data = json.loads(cached_data['json_data'])
            
            # Crea un nuovo record meteo per l'apiario dai dati in cache
            dati_meteo = DatiMeteo(
                apiario=apiario,
                data=timezone.now(),
                temperatura=data.get('main', {}).get('temp'),
                umidita=data.get('main', {}).get('humidity'),
                pressione=data.get('main', {}).get('pressure'),
                velocita_vento=data.get('wind', {}).get('speed'),
                direzione_vento=data.get('wind', {}).get('deg'),
                descrizione=data.get('weather', [{}])[0].get('description'),
                icona=data.get('weather', [{}])[0].get('icon'),
                pioggia=data.get('rain', {}).get('1h', 0)
            )
            dati_meteo.save()
            return dati_meteo
    
    # URL API di OpenWeatherMap (piano Free)
    api_key = settings.OPENWEATHERMAP_API_KEY
    lat = float(apiario.latitudine)
    lon = float(apiario.longitudine)
    url = f"https://api.openweathermap.org/data/2.5/weather?lat={lat}&lon={lon}&units=metric&appid={api_key}&lang=it"
    
    try:
        response = requests.get(url)
        
        if response.status_code == 200:
            data = response.json()
            
            # Salva i dati nella cache per 30 minuti
            cache.set(cache_key, {
                'json_data': json.dumps(data),
                'timestamp': timezone.now().timestamp()
            }, 1800)  # 30 minuti
            
            # Crea un nuovo record meteo per l'apiario
            dati_meteo = DatiMeteo(
                apiario=apiario,
                data=timezone.now(),
                temperatura=data.get('main', {}).get('temp'),
                umidita=data.get('main', {}).get('humidity'),
                pressione=data.get('main', {}).get('pressure'),
                velocita_vento=data.get('wind', {}).get('speed'),
                direzione_vento=data.get('wind', {}).get('deg'),
                descrizione=data.get('weather', [{}])[0].get('description'),
                icona=data.get('weather', [{}])[0].get('icon'),
                pioggia=data.get('rain', {}).get('1h', 0) if 'rain' in data else 0
            )
            dati_meteo.save()
            return dati_meteo
        else:
            print(f"Errore API meteo: {response.status_code}, {response.text}")
            # Se riceviamo 401, stampiamo più dettagli per il debug
            if response.status_code == 401:
                print(f"Errore di autenticazione API. Verifica che l'API key sia corretta e attiva.")
                print(f"API Key utilizzata (primi 5 caratteri): {api_key[:5]}...")
            return None
    except Exception as e:
        print(f"Errore durante la richiesta API meteo: {str(e)}")
        return None

def aggiorna_previsioni_meteo(apiario):
    """
    Recupera le previsioni meteo per un apiario e le salva nel database
    Utilizza l'endpoint delle previsioni a 3 ore disponibile nel piano Free
    """
    # Verifica che l'apiario abbia coordinate valide e monitoraggio abilitato
    if not apiario.has_coordinates() or not apiario.monitoraggio_meteo:
        return []
    
    # Controlla la cache prima di chiamare l'API (cache di 2 ore per le previsioni)
    cache_key = f"previsioni_meteo_{apiario.id}"
    cached_data = cache.get(cache_key)
    if cached_data:
        print(f"Usando previsioni meteo in cache per apiario {apiario.id}")
        if 'json_data' in cached_data:
            data = json.loads(cached_data['json_data'])
            
            # Aggiorna le previsioni dal dato in cache
            return process_forecast_data(apiario, data)
    
    # URL API di OpenWeatherMap per previsioni a 3 ore (piano Free)
    api_key = settings.OPENWEATHERMAP_API_KEY
    lat = float(apiario.latitudine)
    lon = float(apiario.longitudine)
    url = f"https://api.openweathermap.org/data/2.5/forecast?lat={lat}&lon={lon}&units=metric&appid={api_key}&lang=it"
    
    try:
        response = requests.get(url)
        
        if response.status_code == 200:
            data = response.json()
            
            # Salva i dati nella cache per 2 ore
            cache.set(cache_key, {
                'json_data': json.dumps(data),
                'timestamp': timezone.now().timestamp()
            }, 7200)  # 2 ore
            
            # Processa e salva le previsioni
            return process_forecast_data(apiario, data)
        else:
            print(f"Errore API previsioni meteo: {response.status_code}, {response.text}")
            if response.status_code == 401:
                print(f"Errore di autenticazione API. Verifica che l'API key sia corretta e attiva.")
                print(f"API Key utilizzata (primi 5 caratteri): {api_key[:5]}...")
            return []
    except Exception as e:
        print(f"Errore durante la richiesta API previsioni meteo: {str(e)}")
        return []

def process_forecast_data(apiario, data):
    """
    Processa i dati delle previsioni da OpenWeatherMap e li salva nel database
    """
    # Elimina previsioni esistenti per questo apiario
    PrevisioneMeteo.objects.filter(apiario=apiario).delete()
    
    # Data attuale per il timestamp della previsione
    now = timezone.now()
    
    # Salva le nuove previsioni (massimo 5 giorni)
    previsioni_salvate = []
    if 'list' in data:
        for item in data.get('list', []):
            # Qui è il problema! Converte il timestamp da naive a aware datetime
            naive_dt = datetime.fromtimestamp(item.get('dt'))
            data_riferimento = timezone.make_aware(naive_dt)
            
            # Limita alle previsioni entro 5 giorni come da piano Free
            if data_riferimento > (now + timedelta(days=5)):
                continue
            
            # Salva la previsione
            previsione = PrevisioneMeteo(
                apiario=apiario,
                data_previsione=now,
                data_riferimento=data_riferimento,
                temperatura=item.get('main', {}).get('temp'),
                temperatura_min=item.get('main', {}).get('temp_min'),
                temperatura_max=item.get('main', {}).get('temp_max'),
                umidita=item.get('main', {}).get('humidity'),
                pressione=item.get('main', {}).get('pressure'),
                velocita_vento=item.get('wind', {}).get('speed'),
                direzione_vento=item.get('wind', {}).get('deg'),
                probabilita_pioggia=int(item.get('pop', 0) * 100),  # Convertita da 0-1 a percentuale
                descrizione=item.get('weather', [{}])[0].get('description'),
                icona=item.get('weather', [{}])[0].get('icon')
            )
            previsione.save()
            previsioni_salvate.append(previsione)
    
    return previsioni_salvate

def ottieni_dati_meteo_correnti(apiario):
    """
    Ottiene i dati meteo più recenti per un apiario, aggiornandoli se necessario
    """
    # Cerca dati meteo recenti (ultimi 60 minuti)
    dati_recenti = DatiMeteo.objects.filter(
        apiario=apiario,
        data__gte=timezone.now() - timedelta(minutes=60)
    ).order_by('-data').first()
    
    # Se non ci sono dati recenti, aggiorna
    if not dati_recenti:
        dati_recenti = aggiorna_dati_meteo(apiario)
    
    return dati_recenti

def ottieni_previsioni_meteo(apiario):
    """
    Ottiene le previsioni meteo per un apiario, aggiornandole se necessario
    """
    # Cerca previsioni recenti (ultime 3 ore)
    previsioni_recenti = PrevisioneMeteo.objects.filter(
        apiario=apiario,
        data_previsione__gte=timezone.now() - timedelta(hours=3)
    ).exists()
    
    # Se non ci sono previsioni recenti, aggiorna
    if not previsioni_recenti:
        aggiorna_previsioni_meteo(apiario)
    
    # Recupera le previsioni (solo per i prossimi 5 giorni, disponibili nel piano Free)
    previsioni = PrevisioneMeteo.objects.filter(
        apiario=apiario,
        data_riferimento__gte=timezone.now(),
        data_riferimento__lte=timezone.now() + timedelta(days=5)
    ).order_by('data_riferimento')
    
    return previsioni

def get_wind_direction_text(gradi):
    """
    Converte i gradi della direzione del vento in testo (N, NE, E, ecc.)
    """
    directions = ['N', 'NNE', 'NE', 'ENE', 'E', 'ESE', 'SE', 'SSE', 
                  'S', 'SSO', 'SO', 'OSO', 'O', 'ONO', 'NO', 'NNO']
    index = round(float(gradi) / 22.5) % 16
    return directions[index]

def limita_richieste_api(max_richieste=58, per_minuti=1):
    """
    Funzione per limitare le richieste API mantenendosi sotto il limite del piano Free
    Utilizza la cache per tracciare le richieste
    Ritorna True se è possibile fare una richiesta, False altrimenti
    """
    # Chiave cache per tracciare le richieste
    cache_key = "openweathermap_api_requests"
    
    # Prendi il contatore corrente dalla cache
    request_tracker = cache.get(cache_key, {"count": 0, "reset_time": time.time()})
    
    # Se è passato il tempo di reset, azzera il contatore
    current_time = time.time()
    if current_time - request_tracker["reset_time"] > (per_minuti * 60):
        request_tracker = {"count": 0, "reset_time": current_time}
    
    # Controlla se abbiamo superato il limite
    if request_tracker["count"] >= max_richieste:
        print(f"Limite di {max_richieste} richieste API al minuto raggiunto. Attendi.")
        return False
    
    # Incrementa il contatore
    request_tracker["count"] += 1
    cache.set(cache_key, request_tracker, per_minuti * 60)
    
    return True