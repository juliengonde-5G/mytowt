"""
Internationalization (i18n) system for TOWT Planning App.

Languages: fr (default), en, es, pt-br, vi
Usage in templates: {{ t('key') }} or {{ t('key', lang='en') }}
Usage in Python: from app.i18n import get_t; t = get_t('en'); t('key')
"""

SUPPORTED_LANGUAGES = {
    "fr": "Français",
    "en": "English",
    "es": "Español",
    "pt-br": "Português (BR)",
    "vi": "Tiếng Việt",
}

DEFAULT_LANG = "fr"

# ─── TRANSLATIONS ───────────────────────────────────────────────
# Keys are grouped by module. Missing keys fall back to French.
# ────────────────────────────────────────────────────────────────

TRANSLATIONS = {
    # ═══ COMMON / GLOBAL ═══
    "save": {"fr": "Enregistrer", "en": "Save", "es": "Guardar", "pt-br": "Salvar", "vi": "Lưu"},
    "cancel": {"fr": "Annuler", "en": "Cancel", "es": "Cancelar", "pt-br": "Cancelar", "vi": "Hủy"},
    "delete": {"fr": "Supprimer", "en": "Delete", "es": "Eliminar", "pt-br": "Excluir", "vi": "Xóa"},
    "edit": {"fr": "Modifier", "en": "Edit", "es": "Editar", "pt-br": "Editar", "vi": "Sửa"},
    "back": {"fr": "Retour", "en": "Back", "es": "Volver", "pt-br": "Voltar", "vi": "Quay lại"},
    "add": {"fr": "Ajouter", "en": "Add", "es": "Añadir", "pt-br": "Adicionar", "vi": "Thêm"},
    "close": {"fr": "Fermer", "en": "Close", "es": "Cerrar", "pt-br": "Fechar", "vi": "Đóng"},
    "search": {"fr": "Rechercher", "en": "Search", "es": "Buscar", "pt-br": "Buscar", "vi": "Tìm kiếm"},
    "yes": {"fr": "Oui", "en": "Yes", "es": "Sí", "pt-br": "Sim", "vi": "Có"},
    "no": {"fr": "Non", "en": "No", "es": "No", "pt-br": "Não", "vi": "Không"},
    "actions": {"fr": "Actions", "en": "Actions", "es": "Acciones", "pt-br": "Ações", "vi": "Hành động"},
    "status": {"fr": "Statut", "en": "Status", "es": "Estado", "pt-br": "Status", "vi": "Trạng thái"},
    "date": {"fr": "Date", "en": "Date", "es": "Fecha", "pt-br": "Data", "vi": "Ngày"},
    "loading": {"fr": "Chargement...", "en": "Loading...", "es": "Cargando...", "pt-br": "Carregando...", "vi": "Đang tải..."},
    "confirm_delete": {"fr": "Confirmer la suppression ?", "en": "Confirm deletion?", "es": "¿Confirmar eliminación?", "pt-br": "Confirmar exclusão?", "vi": "Xác nhận xóa?"},
    "none": {"fr": "Aucun", "en": "None", "es": "Ninguno", "pt-br": "Nenhum", "vi": "Không có"},
    "all": {"fr": "Tous", "en": "All", "es": "Todos", "pt-br": "Todos", "vi": "Tất cả"},
    "not_specified": {"fr": "Non renseigné", "en": "Not specified", "es": "No indicado", "pt-br": "Não informado", "vi": "Chưa điền"},

    # ═══ SIDEBAR / NAV ═══
    "nav_dashboard": {"fr": "Tableau de bord", "en": "Dashboard", "es": "Panel", "pt-br": "Painel", "vi": "Bảng điều khiển"},
    "nav_planning": {"fr": "Planning", "en": "Planning", "es": "Planificación", "pt-br": "Planejamento", "vi": "Kế hoạch"},
    "nav_commercial": {"fr": "Commercial", "en": "Commercial", "es": "Comercial", "pt-br": "Comercial", "vi": "Thương mại"},
    "nav_escale": {"fr": "Escale", "en": "Port Call", "es": "Escala", "pt-br": "Escala", "vi": "Ghé cảng"},
    "nav_cargo": {"fr": "Cargo Docs", "en": "Cargo Docs", "es": "Docs Carga", "pt-br": "Docs Carga", "vi": "Hồ sơ hàng"},
    "nav_kpi": {"fr": "KPI", "en": "KPI", "es": "KPI", "pt-br": "KPI", "vi": "KPI"},
    "nav_finance": {"fr": "Finance", "en": "Finance", "es": "Finanzas", "pt-br": "Finanças", "vi": "Tài chính"},
    "nav_captain": {"fr": "Capitaine", "en": "Captain", "es": "Capitán", "pt-br": "Capitão", "vi": "Thuyền trưởng"},
    "nav_crew": {"fr": "Équipage", "en": "Crew", "es": "Tripulación", "pt-br": "Tripulação", "vi": "Thủy thủ đoàn"},
    "nav_settings": {"fr": "Paramètres", "en": "Settings", "es": "Configuración", "pt-br": "Configurações", "vi": "Cài đặt"},

    # ═══ PACKING LIST (client-facing) ═══
    "pl_title": {"fr": "Packing List", "en": "Packing List", "es": "Lista de empaque", "pt-br": "Lista de embalagem", "vi": "Danh sách đóng gói"},
    "pl_locked_msg": {"fr": "Cette packing list a été verrouillée par l'exploitation. Les modifications ne sont plus possibles.",
                      "en": "This packing list has been locked by operations. Modifications are no longer possible.",
                      "es": "Esta lista de empaque ha sido bloqueada por operaciones. Ya no es posible modificarla.",
                      "pt-br": "Esta lista de embalagem foi bloqueada pela operação. Modificações não são mais possíveis.",
                      "vi": "Danh sách đóng gói này đã bị khóa bởi bộ phận vận hành. Không thể sửa đổi."},
    "pl_saved_msg": {"fr": "Vos informations ont été enregistrées avec succès.",
                     "en": "Your information has been saved successfully.",
                     "es": "Su información ha sido guardada con éxito.",
                     "pt-br": "Suas informações foram salvas com sucesso.",
                     "vi": "Thông tin của bạn đã được lưu thành công."},
    "pl_voyage_info": {"fr": "Informations voyage (pré-remplies par TOWT)", "en": "Voyage information (pre-filled by TOWT)",
                       "es": "Información del viaje (prellenada por TOWT)", "pt-br": "Informações da viagem (preenchidas pela TOWT)",
                       "vi": "Thông tin chuyến đi (được TOWT điền sẵn)"},
    "pl_shipper_section": {"fr": "Expéditeur & destinataire", "en": "Shipper & consignee",
                           "es": "Expedidor y destinatario", "pt-br": "Embarcador e destinatário",
                           "vi": "Người gửi & người nhận"},
    "pl_goods_section": {"fr": "Marchandise", "en": "Goods", "es": "Mercancía", "pt-br": "Mercadoria", "vi": "Hàng hóa"},
    "pl_dimensions_section": {"fr": "Dimensions par palette", "en": "Dimensions per pallet",
                              "es": "Dimensiones por paleta", "pt-br": "Dimensões por palete",
                              "vi": "Kích thước mỗi pallet"},
    "pl_add_batch": {"fr": "Ajouter un batch", "en": "Add a batch", "es": "Añadir un lote",
                     "pt-br": "Adicionar um lote", "vi": "Thêm lô hàng"},
    "pl_delete_batch": {"fr": "Supprimer ce batch", "en": "Delete this batch", "es": "Eliminar este lote",
                        "pt-br": "Excluir este lote", "vi": "Xóa lô hàng này"},
    "pl_batch": {"fr": "Batch", "en": "Batch", "es": "Lote", "pt-br": "Lote", "vi": "Lô hàng"},

    # Fields
    "f_voyage": {"fr": "Voyage", "en": "Voyage", "es": "Viaje", "pt-br": "Viagem", "vi": "Chuyến đi"},
    "f_vessel": {"fr": "Navire", "en": "Vessel", "es": "Buque", "pt-br": "Navio", "vi": "Tàu"},
    "f_loading_date": {"fr": "Date de chargement", "en": "Loading date", "es": "Fecha de carga", "pt-br": "Data de embarque", "vi": "Ngày xếp hàng"},
    "f_booking_ref": {"fr": "Réf. booking", "en": "Booking ref.", "es": "Ref. reserva", "pt-br": "Ref. reserva", "vi": "Mã đặt chỗ"},
    "f_freight_rate": {"fr": "Fret/palette", "en": "Freight/pallet", "es": "Flete/paleta", "pt-br": "Frete/palete", "vi": "Cước/pallet"},
    "f_customer_name": {"fr": "Nom client", "en": "Customer name", "es": "Nombre del cliente", "pt-br": "Nome do cliente", "vi": "Tên khách hàng"},
    "f_freight_forwarder": {"fr": "Transitaire", "en": "Freight forwarder", "es": "Transitario", "pt-br": "Agente de carga", "vi": "Đại lý giao nhận"},
    "f_code_transitaire": {"fr": "Code transitaire", "en": "Forwarder code", "es": "Código transitario", "pt-br": "Código agente", "vi": "Mã đại lý"},
    "f_shipper_name": {"fr": "Nom expéditeur (Shipper)", "en": "Shipper name", "es": "Nombre del expedidor", "pt-br": "Nome do embarcador", "vi": "Tên người gửi"},
    "f_shipper_address": {"fr": "Adresse expéditeur", "en": "Shipper address", "es": "Dirección del expedidor", "pt-br": "Endereço do embarcador", "vi": "Địa chỉ người gửi"},
    "f_po_number": {"fr": "N° PO", "en": "PO number", "es": "N° PO", "pt-br": "N° PO", "vi": "Số PO"},
    "f_batch_id": {"fr": "Batch ID client", "en": "Client batch ID", "es": "ID lote cliente", "pt-br": "ID lote cliente", "vi": "Mã lô khách hàng"},
    "f_notify_address": {"fr": "Adresse Notify", "en": "Notify address", "es": "Dirección Notify", "pt-br": "Endereço Notify", "vi": "Địa chỉ Notify"},
    "f_consignee_address": {"fr": "Adresse Consignee", "en": "Consignee address", "es": "Dirección Consignee", "pt-br": "Endereço Consignatário", "vi": "Địa chỉ người nhận"},
    "f_pallet_type": {"fr": "Type de palette", "en": "Pallet type", "es": "Tipo de paleta", "pt-br": "Tipo de palete", "vi": "Loại pallet"},
    "f_type_of_goods": {"fr": "Nature des marchandises", "en": "Type of goods", "es": "Tipo de mercancía", "pt-br": "Tipo de mercadoria", "vi": "Loại hàng hóa"},
    "f_bio_products": {"fr": "Produits bio", "en": "Organic products", "es": "Productos bio", "pt-br": "Produtos orgânicos", "vi": "Sản phẩm hữu cơ"},
    "f_pallet_quantity": {"fr": "Nb palettes ce batch", "en": "Pallets in this batch", "es": "Paletas en este lote", "pt-br": "Paletes neste lote", "vi": "Số pallet trong lô"},
    "f_cases_quantity": {"fr": "Nb colis", "en": "Cases qty", "es": "Cant. bultos", "pt-br": "Qtd. volumes", "vi": "Số kiện"},
    "f_units_per_case": {"fr": "Unités/colis", "en": "Units/case", "es": "Unidades/bulto", "pt-br": "Unidades/volume", "vi": "Đơn vị/kiện"},
    "f_imo_class": {"fr": "Classification IMO", "en": "IMO classification", "es": "Clasificación OMI", "pt-br": "Classificação IMO", "vi": "Phân loại IMO"},
    "f_cargo_value": {"fr": "Valeur cargo (USD)", "en": "Cargo value (USD)", "es": "Valor carga (USD)", "pt-br": "Valor carga (USD)", "vi": "Giá trị hàng (USD)"},
    "f_length": {"fr": "Longueur (cm)", "en": "Length (cm)", "es": "Largo (cm)", "pt-br": "Comprimento (cm)", "vi": "Dài (cm)"},
    "f_width": {"fr": "Largeur (cm)", "en": "Width (cm)", "es": "Ancho (cm)", "pt-br": "Largura (cm)", "vi": "Rộng (cm)"},
    "f_height": {"fr": "Hauteur (cm)", "en": "Height (cm)", "es": "Alto (cm)", "pt-br": "Altura (cm)", "vi": "Cao (cm)"},
    "f_weight": {"fr": "Poids brut (kg)", "en": "Gross weight (kg)", "es": "Peso bruto (kg)", "pt-br": "Peso bruto (kg)", "vi": "Trọng lượng (kg)"},
    "f_ordered_palettes": {"fr": "Palettes commandées", "en": "Ordered pallets", "es": "Paletas pedidas", "pt-br": "Paletes pedidos", "vi": "Pallet đã đặt"},
    "f_loading": {"fr": "Chargement", "en": "Loading", "es": "Carga", "pt-br": "Embarque", "vi": "Xếp hàng"},
    "f_destination": {"fr": "Destination", "en": "Destination", "es": "Destino", "pt-br": "Destino", "vi": "Điểm đến"},
    "f_other": {"fr": "Autre", "en": "Other", "es": "Otro", "pt-br": "Outro", "vi": "Khác"},

    # ═══ EXPLOITATION CARGO ═══
    "cargo_title": {"fr": "Gestion documentaire cargo", "en": "Cargo document management",
                    "es": "Gestión documental de carga", "pt-br": "Gestão documental de carga",
                    "vi": "Quản lý hồ sơ hàng hóa"},
    "cargo_draft": {"fr": "Brouillon", "en": "Draft", "es": "Borrador", "pt-br": "Rascunho", "vi": "Nháp"},
    "cargo_submitted": {"fr": "Soumis", "en": "Submitted", "es": "Enviado", "pt-br": "Enviado", "vi": "Đã gửi"},
    "cargo_locked": {"fr": "Verrouillé", "en": "Locked", "es": "Bloqueado", "pt-br": "Bloqueado", "vi": "Đã khóa"},
    "cargo_reviewed": {"fr": "Examiné", "en": "Reviewed", "es": "Revisado", "pt-br": "Revisado", "vi": "Đã xem"},
    "cargo_lock": {"fr": "Verrouiller", "en": "Lock", "es": "Bloquear", "pt-br": "Bloquear", "vi": "Khóa"},
    "cargo_unlock": {"fr": "Déverrouiller", "en": "Unlock", "es": "Desbloquear", "pt-br": "Desbloquear", "vi": "Mở khóa"},
    "cargo_history": {"fr": "Historique", "en": "History", "es": "Historial", "pt-br": "Histórico", "vi": "Lịch sử"},
    "cargo_import_excel": {"fr": "Import Excel", "en": "Import Excel", "es": "Importar Excel", "pt-br": "Importar Excel", "vi": "Nhập Excel"},
    "cargo_export_excel": {"fr": "Export Excel", "en": "Export Excel", "es": "Exportar Excel", "pt-br": "Exportar Excel", "vi": "Xuất Excel"},
    "cargo_bill_of_lading": {"fr": "Bill of Lading", "en": "Bill of Lading", "es": "Conocimiento de embarque", "pt-br": "Conhecimento de embarque", "vi": "Vận đơn"},
    "cargo_completion": {"fr": "Complétude", "en": "Completion", "es": "Completitud", "pt-br": "Conclusão", "vi": "Hoàn thành"},
    "cargo_client_link": {"fr": "Lien client", "en": "Client link", "es": "Enlace cliente", "pt-br": "Link cliente", "vi": "Liên kết khách hàng"},
    "cargo_palette_ok": {"fr": "palettes — Conforme", "en": "pallets — Compliant", "es": "paletas — Conforme", "pt-br": "paletes — Conforme", "vi": "pallet — Phù hợp"},
    "cargo_palette_over": {"fr": "Excédent de", "en": "Excess of", "es": "Excedente de", "pt-br": "Excesso de", "vi": "Dư"},
    "cargo_palette_under": {"fr": "Manque", "en": "Missing", "es": "Faltan", "pt-br": "Faltam", "vi": "Thiếu"},
    "cargo_palette_gap": {"fr": "Écart palettes", "en": "Pallet discrepancy", "es": "Discrepancia paletas", "pt-br": "Discrepância paletes", "vi": "Chênh lệch pallet"},
    "cargo_in_batches": {"fr": "dans les batchs", "en": "in batches", "es": "en lotes", "pt-br": "nos lotes", "vi": "trong các lô"},
    "cargo_ordered": {"fr": "commandée(s)", "en": "ordered", "es": "pedida(s)", "pt-br": "pedido(s)", "vi": "đã đặt"},

    # ═══ SETTINGS ═══
    "settings_title": {"fr": "Paramètres", "en": "Settings", "es": "Configuración", "pt-br": "Configurações", "vi": "Cài đặt"},
    "settings_language": {"fr": "Langue de l'interface", "en": "Interface language", "es": "Idioma de la interfaz", "pt-br": "Idioma da interface", "vi": "Ngôn ngữ giao diện"},
    "settings_saved": {"fr": "Paramètres enregistrés", "en": "Settings saved", "es": "Configuración guardada", "pt-br": "Configurações salvas", "vi": "Đã lưu cài đặt"},

    # ═══ DOCUMENT GENERATION ═══
    "doc_choose_lang": {"fr": "Choisir la langue du document", "en": "Choose document language",
                        "es": "Elegir idioma del documento", "pt-br": "Escolher idioma do documento",
                        "vi": "Chọn ngôn ngữ tài liệu"},
    "doc_generate": {"fr": "Générer", "en": "Generate", "es": "Generar", "pt-br": "Gerar", "vi": "Tạo"},
    "doc_french_english_only": {"fr": "Français ou Anglais uniquement", "en": "French or English only",
                                "es": "Solo francés o inglés", "pt-br": "Apenas francês ou inglês",
                                "vi": "Chỉ tiếng Pháp hoặc tiếng Anh"},
}


def t(key: str, lang: str = DEFAULT_LANG) -> str:
    """Get translation for a key in the given language."""
    entry = TRANSLATIONS.get(key)
    if not entry:
        return key
    return entry.get(lang) or entry.get(DEFAULT_LANG) or key


def get_t(lang: str = DEFAULT_LANG):
    """Return a translation function bound to a language."""
    def _t(key: str) -> str:
        return t(key, lang)
    return _t


def get_lang_from_request(request, user=None) -> str:
    """Determine language from user preference, query param, or cookie."""
    # 1. Query param ?lang=xx
    lang = None
    if hasattr(request, 'query_params'):
        lang = request.query_params.get('lang')
    # 2. User preference
    if not lang and user and hasattr(user, 'language') and user.language:
        lang = user.language
    # 3. Cookie
    if not lang:
        lang = request.cookies.get('towt_lang')
    # 4. Default
    if not lang or lang not in SUPPORTED_LANGUAGES:
        lang = DEFAULT_LANG
    return lang
