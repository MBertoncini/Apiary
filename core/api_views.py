
    @action(detail=False, methods=['post'], url_path='create_from_voice')
    def create_from_voice(self, request):
        """
        Crea un nuovo trattamento da un comando vocale.
        Payload: { arnia_id: int, tipo_trattamento: str, data_inizio: str, note: str }
        """
        arnia_id = request.data.get('arnia_id')
        tipo_trattamento_nome = request.data.get('tipo_trattamento')

        if not arnia_id or not tipo_trattamento_nome:
            return Response({'detail': 'Dati mancanti.'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            arnia = Arnia.objects.get(pk=arnia_id)
            apiario = arnia.apiario
            # Verifica permessi
            if not IsOwnerOrGroupRole().has_object_permission(request, self, apiario):
                raise PermissionDenied()
        except Arnia.DoesNotExist:
            return Response({'detail': 'Arnia non trovata.'}, status=status.HTTP_404_NOT_FOUND)
        except PermissionDenied:
            return Response({'detail': 'Non hai i permessi per questa arnia.'}, status=status.HTTP_403_FORBIDDEN)

        # Cerca o crea un TipoTrattamento
        tipo_trattamento, _ = TipoTrattamento.objects.get_or_create(
            nome__iexact=tipo_trattamento_nome,
            defaults={'nome': tipo_trattamento_nome.capitalize()}
        )

        data = {
            'apiario': apiario.id,
            'tipo_trattamento': tipo_trattamento.id,
            'data_inizio': request.data.get('data_inizio', timezone.now().date().isoformat()),
            'note': request.data.get('note', ''),
            'arnie': [arnia.id], # Associa il trattamento a questa arnia specifica
        }

        serializer = self.get_serializer(data=data)
        if serializer.is_valid():
            self.perform_create(serializer)
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
