from django.urls import path

from .views.export import ExportExcelView, ExportPdfView
from .views.nl_query import NLQueryView
from .views.query_builder import QueryBuilderView
from .views.widgets import (
    AndamentoCovataView,
    AndamentoScorteView,
    BilancioEconomicoView,
    DashboardConfigView,
    FioritureVicineView,
    FrequenzaControlliView,
    PerformanceRegineView,
    ProduzioneAnnualeView,
    ProduzionePerTipoView,
    QuoteGruppoView,
    RegineStatisticheView,
    RiepilogoAttrezzatureView,
    SaluteArnieView,
    VarroaTrendView,
    WidgetListView,
)

urlpatterns = [
    # Catalogo widget
    path('widgets/', WidgetListView.as_view(), name='stats-widget-list'),

    # Widget individuali
    path('widgets/salute_arnie/', SaluteArnieView.as_view(), name='stats-salute-arnie'),
    path('widgets/produzione_annuale/', ProduzioneAnnualeView.as_view(), name='stats-produzione-annuale'),
    path('widgets/frequenza_controlli/', FrequenzaControlliView.as_view(), name='stats-frequenza-controlli'),
    path('widgets/regine_statistiche/', RegineStatisticheView.as_view(), name='stats-regine-statistiche'),
    path('widgets/performance_regine/', PerformanceRegineView.as_view(), name='stats-performance-regine'),
    path('widgets/varroa_trend/', VarroaTrendView.as_view(), name='stats-varroa-trend'),
    path('widgets/bilancio_economico/', BilancioEconomicoView.as_view(), name='stats-bilancio-economico'),
    path('widgets/quote_gruppo/', QuoteGruppoView.as_view(), name='stats-quote-gruppo'),
    path('widgets/fioriture_vicine/', FioritureVicineView.as_view(), name='stats-fioriture-vicine'),
    path('widgets/andamento_scorte/', AndamentoScorteView.as_view(), name='stats-andamento-scorte'),
    path('widgets/andamento_covata/', AndamentoCovataView.as_view(), name='stats-andamento-covata'),
    path('widgets/produzione_per_tipo/', ProduzionePerTipoView.as_view(), name='stats-produzione-per-tipo'),
    path('widgets/riepilogo_attrezzature/', RiepilogoAttrezzatureView.as_view(), name='stats-riepilogo-attrezzature'),

    # Dashboard config
    path('dashboard/', DashboardConfigView.as_view(), name='stats-dashboard-config'),

    # Query builder (Livello 2)
    path('query-builder/', QueryBuilderView.as_view(), name='stats-query-builder'),

    # Natural Language Query (Livello 3)
    path('nl-query/', NLQueryView.as_view(), name='stats-nl-query'),

    # Export
    path('export/excel/', ExportExcelView.as_view(), name='stats-export-excel'),
    path('export/pdf/', ExportPdfView.as_view(), name='stats-export-pdf'),
]
