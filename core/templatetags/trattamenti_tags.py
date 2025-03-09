# core/templatetags/trattamenti_tags.py
from django import template

register = template.Library()

@register.filter
def filter(queryset, attr_eq_val):
    """
    Filtra un queryset in base a un attributo che deve essere True o uguale a un valore.
    
    Uso: {{ queryset|filter:"attributo" }} - Filtra per attributo == True
         {{ queryset|filter:"attributo=valore" }} - Filtra per attributo == valore
    """
    if '=' in attr_eq_val:
        # Formato attributo=valore
        attr, val = attr_eq_val.split('=', 1)
        kwargs = {attr: val}
        return queryset.filter(**kwargs)
    else:
        # Formato attributo (filtra per attributo == True)
        kwargs = {attr_eq_val: True}
        return queryset.filter(**kwargs)