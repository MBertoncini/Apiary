from rest_framework import serializers
from .models import DashboardConfig


class DashboardConfigSerializer(serializers.ModelSerializer):
    class Meta:
        model = DashboardConfig
        fields = ['widget_config', 'aggiornato_il']
        read_only_fields = ['aggiornato_il']


class QueryResultSerializer(serializers.Serializer):
    tipo_visualizzazione = serializers.CharField()
    titolo = serializers.CharField()
    dati = serializers.DictField()
    totale_righe = serializers.IntegerField()
