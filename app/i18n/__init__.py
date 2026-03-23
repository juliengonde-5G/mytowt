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

    # ═══ CLIENT GUIDE ═══
    "guide_link_text": {
        "fr": "Comment remplir ce formulaire ?",
        "en": "How to fill this form?"},
    "guide_title": {
        "fr": "Guide de saisie — Packing List",
        "en": "Packing List — Submission Guide"},
    "guide_subtitle": {
        "fr": "Tout ce que vous devez savoir pour remplir votre packing list",
        "en": "Everything you need to know to complete your packing list"},
    "guide_back_to_form": {
        "fr": "Retour au formulaire",
        "en": "Back to form"},
    "guide_toc": {
        "fr": "Sommaire",
        "en": "Table of contents"},
    "guide_tip": {"fr": "Conseil", "en": "Tip"},
    "guide_important": {"fr": "Important", "en": "Important"},
    "guide_warning": {"fr": "Attention", "en": "Warning"},
    "guide_field": {"fr": "Champ", "en": "Field"},
    "guide_required": {"fr": "Requis", "en": "Required"},
    "guide_description": {"fr": "Description", "en": "Description"},
    "guide_example": {"fr": "Exemple", "en": "Example"},
    "guide_optional": {"fr": "Optionnel", "en": "Optional"},
    "guide_recommended": {"fr": "Recommandé", "en": "Recommended"},
    "guide_deadline": {"fr": "Échéance", "en": "Deadline"},
    "guide_action": {"fr": "Action", "en": "Action"},
    "guide_days": {"fr": "jours", "en": "days"},
    "guide_situation": {"fr": "Situation", "en": "Situation"},
    "guide_fee": {"fr": "Frais (EUR)", "en": "Fee (EUR)"},
    "guide_phone": {"fr": "Téléphone", "en": "Phone"},
    "guide_footer": {
        "fr": "Décarboner le fret maritime",
        "en": "Decarbonizing maritime freight"},

    # Section titles
    "guide_s1_title": {
        "fr": "Présentation générale",
        "en": "Overview"},
    "guide_s2_title": {
        "fr": "Les étapes à suivre",
        "en": "Steps to follow"},
    "guide_s3_title": {
        "fr": "Référence des champs",
        "en": "Field reference"},
    "guide_s4_title": {
        "fr": "Fonctionnement des batchs",
        "en": "How batches work"},
    "guide_s5_title": {
        "fr": "Exigences d'emballage",
        "en": "Packaging requirements"},
    "guide_s6_title": {
        "fr": "Délais à respecter",
        "en": "Key deadlines"},
    "guide_s7_title": {
        "fr": "Barème des frais",
        "en": "Fee schedule"},
    "guide_s8_title": {
        "fr": "Expéditions vers les États-Unis",
        "en": "Shipments to the United States"},
    "guide_s9_title": {
        "fr": "Questions fréquentes",
        "en": "Frequently asked questions"},
    "guide_s10_title": {
        "fr": "Contact",
        "en": "Contact"},

    # S1 - Overview
    "guide_s1_p1": {
        "fr": "Ce formulaire en ligne vous permet de renseigner les informations relatives à votre expédition. Ces données servent à préparer les documents essentiels : Bill of Lading (connaissement), manifeste cargo, étiquettes et documents douaniers.",
        "en": "This online form allows you to provide all the information related to your shipment. This data is used to prepare essential documents: Bill of Lading, cargo manifest, labels, and customs documents."},
    "guide_s1_p2": {
        "fr": "Les champs marqués d'un astérisque (*) sont obligatoires. Plus vos informations sont complètes et exactes, plus le traitement de votre dossier sera rapide.",
        "en": "Fields marked with an asterisk (*) are mandatory. The more complete and accurate your information, the faster your file will be processed."},
    "guide_s1_tip": {
        "fr": "Vous pouvez enregistrer votre saisie à tout moment et y revenir plus tard avec le même lien.",
        "en": "You can save your entry at any time and come back later using the same link."},

    # S2 - Steps
    "guide_step1_title": {
        "fr": "Vérifiez les informations voyage",
        "en": "Check the voyage information"},
    "guide_step1_desc": {
        "fr": "En haut de chaque batch, les informations voyage sont pré-remplies par TOWT (navire, port de chargement, destination, date ETD). Vérifiez qu'elles correspondent à votre commande.",
        "en": "At the top of each batch, voyage information is pre-filled by TOWT (vessel, loading port, destination, ETD date). Verify that it matches your order."},
    "guide_step2_title": {
        "fr": "Renseignez l'expéditeur et le destinataire",
        "en": "Fill in shipper and consignee details"},
    "guide_step2_desc": {
        "fr": "Indiquez le nom client, le nom de l'expéditeur (shipper), son adresse complète, ainsi que l'adresse du destinataire (consignee). Ces informations figureront sur le Bill of Lading.",
        "en": "Enter the customer name, shipper name and full address, as well as the consignee address. This information will appear on the Bill of Lading."},
    "guide_step3_title": {
        "fr": "Décrivez la marchandise",
        "en": "Describe the goods"},
    "guide_step3_desc": {
        "fr": "Sélectionnez le type de palette, renseignez la nature des marchandises, le nombre de palettes, et indiquez si les produits sont bio ou classés IMO (marchandises dangereuses).",
        "en": "Select the pallet type, describe the nature of goods, enter the number of pallets, and indicate if the products are organic or IMO classified (dangerous goods)."},
    "guide_step4_title": {
        "fr": "Indiquez les dimensions et le poids",
        "en": "Enter dimensions and weight"},
    "guide_step4_desc": {
        "fr": "Renseignez la longueur, largeur et hauteur de chaque palette (en cm) ainsi que le poids brut (en kg). La hauteur maximale autorisée est de 190 cm.",
        "en": "Enter the length, width and height of each pallet (in cm) as well as the gross weight (in kg). The maximum allowed height is 190 cm."},
    "guide_step5_title": {
        "fr": "Enregistrez et ajoutez des batchs si nécessaire",
        "en": "Save and add batches if needed"},
    "guide_step5_desc": {
        "fr": "Cliquez sur « Enregistrer » pour sauvegarder. Si votre expédition contient plusieurs lots de marchandises différentes, ajoutez un batch par lot via le bouton « Ajouter un batch ».",
        "en": "Click 'Save' to save your data. If your shipment contains multiple different lots of goods, add one batch per lot using the 'Add a batch' button."},

    # S3 - Field descriptions
    "guide_s3_intro": {
        "fr": "Voici le détail de chaque champ du formulaire. Les champs obligatoires (*) doivent être remplis pour que votre packing list soit considérée comme complète.",
        "en": "Here is the detail of each form field. Mandatory fields (*) must be filled for your packing list to be considered complete."},
    "guide_f_customer_name_desc": {
        "fr": "Votre raison sociale ou nom commercial tel qu'il apparaît dans le contrat.",
        "en": "Your company name or trade name as it appears in the contract."},
    "guide_f_freight_forwarder_desc": {
        "fr": "Nom du transitaire en charge de l'acheminement terrestre, s'il y en a un.",
        "en": "Name of the freight forwarder handling land transport, if applicable."},
    "guide_f_code_transitaire_desc": {
        "fr": "Code ou référence interne de votre transitaire.",
        "en": "Internal code or reference of your freight forwarder."},
    "guide_f_shipper_name_desc": {
        "fr": "Nom complet de l'expéditeur. Figurera sur le Bill of Lading.",
        "en": "Full shipper name. Will appear on the Bill of Lading."},
    "guide_f_shipper_address_desc": {
        "fr": "Adresse complète de l'expéditeur : rue, code postal, ville, pays.",
        "en": "Full shipper address: street, postal code, city, country."},
    "guide_f_po_number_desc": {
        "fr": "Numéro de commande (Purchase Order) de votre client, si applicable.",
        "en": "Your client's Purchase Order number, if applicable."},
    "guide_f_batch_id_desc": {
        "fr": "Votre référence interne pour identifier ce lot de marchandises.",
        "en": "Your internal reference to identify this lot of goods."},
    "guide_f_notify_desc": {
        "fr": "Personne ou société à notifier à l'arrivée de la marchandise (souvent le transitaire au port d'arrivée).",
        "en": "Person or company to notify upon cargo arrival (often the forwarder at the destination port)."},
    "guide_f_consignee_desc": {
        "fr": "Nom et adresse complète du destinataire final. Figurera sur le Bill of Lading.",
        "en": "Full name and address of the final consignee. Will appear on the Bill of Lading."},
    "guide_f_pallet_type_desc": {
        "fr": "EPAL (80×120 cm, standard européen), USPAL (100×120 cm, standard US), PORTPAL ou Autre.",
        "en": "EPAL (80×120 cm, European standard), USPAL (100×120 cm, US standard), PORTPAL or Other."},
    "guide_f_goods_desc": {
        "fr": "Description précise de la nature des marchandises transportées.",
        "en": "Precise description of the nature of the transported goods."},
    "guide_f_goods_example": {
        "fr": "Vin rouge AOC, café vert arabica, huile d'olive bio...",
        "en": "Red wine AOC, green arabica coffee, organic olive oil..."},
    "guide_f_bio_desc": {
        "fr": "Indiquez si vos produits sont certifiés bio/organiques.",
        "en": "Indicate if your products are certified organic."},
    "guide_f_qty_desc": {
        "fr": "Nombre de palettes dans ce batch. Le total de tous les batchs doit correspondre à la quantité commandée.",
        "en": "Number of pallets in this batch. The total across all batches should match the ordered quantity."},
    "guide_f_cases_desc": {
        "fr": "Nombre total de colis/cartons sur les palettes de ce batch.",
        "en": "Total number of cases/cartons on the pallets in this batch."},
    "guide_f_units_desc": {
        "fr": "Nombre d'unités par colis (ex : 6 bouteilles par carton).",
        "en": "Number of units per case (e.g., 6 bottles per carton)."},
    "guide_f_imo_desc": {
        "fr": "Si votre marchandise est classée dangereuse (IMDG), sélectionnez la classe IMO. Sinon, laissez vide ou choisissez « Non-Dangerous Goods ».",
        "en": "If your goods are classified as dangerous (IMDG), select the IMO class. Otherwise, leave empty or select 'Non-Dangerous Goods'."},
    "guide_f_value_desc": {
        "fr": "Valeur déclarée de la marchandise en dollars US (pour les déclarations douanières).",
        "en": "Declared cargo value in US dollars (for customs declarations)."},
    "guide_f_length_desc": {
        "fr": "Longueur de la palette chargée, en centimètres.",
        "en": "Length of the loaded pallet, in centimeters."},
    "guide_f_width_desc": {
        "fr": "Largeur de la palette chargée, en centimètres.",
        "en": "Width of the loaded pallet, in centimeters."},
    "guide_f_height_desc": {
        "fr": "Hauteur totale (palette + marchandise), en centimètres. Maximum : 190 cm.",
        "en": "Total height (pallet + goods), in centimeters. Maximum: 190 cm."},
    "guide_f_weight_desc": {
        "fr": "Poids brut par palette (marchandise + palette + emballage), en kilogrammes.",
        "en": "Gross weight per pallet (goods + pallet + packaging), in kilograms."},
    "guide_s3_height_warning": {
        "fr": "La hauteur maximale autorisée par palette est de 190 cm. Les palettes dépassant cette hauteur pourront être refusées au chargement.",
        "en": "The maximum allowed height per pallet is 190 cm. Pallets exceeding this height may be refused at loading."},

    # S4 - Batches
    "guide_s4_p1": {
        "fr": "Un « batch » représente un lot homogène de marchandises. Si toutes vos palettes contiennent le même type de produit vers le même destinataire, un seul batch suffit.",
        "en": "A 'batch' represents a homogeneous lot of goods. If all your pallets contain the same type of product going to the same consignee, a single batch is sufficient."},
    "guide_s4_li1": {
        "fr": "Utilisez plusieurs batchs si vous avez des marchandises différentes (ex : vin et café).",
        "en": "Use multiple batches if you have different goods (e.g., wine and coffee)."},
    "guide_s4_li2": {
        "fr": "Utilisez plusieurs batchs si vous avez des destinataires différents.",
        "en": "Use multiple batches if you have different consignees."},
    "guide_s4_li3": {
        "fr": "Le total des palettes de tous les batchs doit correspondre au nombre commandé.",
        "en": "The total pallets across all batches must match the ordered quantity."},
    "guide_s4_tip": {
        "fr": "Vous pouvez supprimer un batch tant qu'il en reste au moins un. Les informations voyage sont automatiquement copiées dans chaque nouveau batch.",
        "en": "You can delete a batch as long as at least one remains. Voyage information is automatically copied to each new batch."},

    # S5 - Packaging
    "guide_s5_general_title": {
        "fr": "Exigences générales",
        "en": "General requirements"},
    "guide_s5_li1": {
        "fr": "L'emballage doit être de qualité maritime : résistant à l'humidité et aux chocs.",
        "en": "Packaging must be maritime-grade: resistant to moisture and shocks."},
    "guide_s5_li2": {
        "fr": "Cerclage robuste obligatoire pour maintenir la marchandise sur la palette.",
        "en": "Robust strapping is mandatory to secure goods on the pallet."},
    "guide_s5_li3": {
        "fr": "Les marchandises en vrac (breakbulk) doivent être conditionnées en big bags.",
        "en": "Bulk goods (breakbulk) must be packed in big bags."},
    "guide_s5_li4": {
        "fr": "Les marchandises classées IMO doivent respecter le Code IMDG.",
        "en": "IMO-classified goods must comply with the IMDG Code."},
    "guide_s5_pallet_title": {
        "fr": "Palettisation",
        "en": "Palletization"},
    "guide_s5_pli1": {
        "fr": "Double filmage obligatoire, y compris la base de la palette.",
        "en": "Double film wrapping is mandatory, including the pallet base."},
    "guide_s5_pli2": {
        "fr": "Les étiquettes TOWT doivent être apposées sur chaque palette (fournies par TOWT).",
        "en": "TOWT labels must be affixed to each pallet (provided by TOWT)."},
    "guide_s5_pli3": {
        "fr": "Marchandises de haute valeur : filmage noir opaque + ruban inviolable.",
        "en": "High-value goods: opaque black film + tamper-evident tape."},
    "guide_s5_label_title": {
        "fr": "Étiquetage",
        "en": "Labeling"},
    "guide_s5_lli1": {
        "fr": "Chaque palette doit porter une étiquette avec : numéro de lot, description des marchandises, poids, destination.",
        "en": "Each pallet must bear a label with: lot number, goods description, weight, destination."},
    "guide_s5_lli2": {
        "fr": "Les étiquettes TOWT vous seront envoyées par email avant la date de réception en entrepôt.",
        "en": "TOWT labels will be sent to you by email before the warehouse reception date."},
    "guide_s5_wood_warning": {
        "fr": "Tout emballage en bois doit être conforme à la norme ISPM15 (traitement thermique) et porter le cachet IPPC. Le non-respect peut entraîner un refus en douane.",
        "en": "All wood packaging must comply with ISPM15 standards (heat treatment) and bear the IPPC stamp. Non-compliance may result in customs refusal."},

    # S6 - Deadlines
    "guide_s6_d1": {
        "fr": "Soumettre la packing list complète, la facture commerciale et les instructions d'expédition.",
        "en": "Submit the complete packing list, commercial invoice, and shipping instructions."},
    "guide_s6_d2": {
        "fr": "Début de réception en entrepôt. Livrer la marchandise au port désigné (sur rendez-vous).",
        "en": "Warehouse reception starts. Deliver goods to the designated port (by appointment)."},
    "guide_s6_d3": {
        "fr": "Date limite de réception. Toute la marchandise et les documents doivent être prêts.",
        "en": "Reception deadline. All goods and documents must be ready."},
    "guide_s6_warning": {
        "fr": "Si la marchandise n'est pas prête à temps, le navire pourra partir sans elle. Le fret sera facturé comme « dead freight » et des frais supplémentaires s'appliqueront.",
        "en": "If the goods are not ready on time, the vessel may depart without them. Freight will be invoiced as 'dead freight' and additional charges will apply."},
    "guide_s6_after_title": {
        "fr": "Après votre soumission",
        "en": "After your submission"},
    "guide_s6_after1": {
        "fr": "Vos données sont intégrées dans le système sous 24h.",
        "en": "Your data is integrated into the system within 24 hours."},
    "guide_s6_after2": {
        "fr": "Un brouillon de Bill of Lading est émis sous 72h après réception des données complètes et correctes.",
        "en": "A draft Bill of Lading is issued within 72 hours of receiving complete and correct data."},
    "guide_s6_after3": {
        "fr": "Le Bill of Lading final est émis après le départ du navire.",
        "en": "The final Bill of Lading is issued after the vessel's departure."},

    # S7 - Fees
    "guide_s7_intro": {
        "fr": "Afin de garantir un traitement fluide, les situations suivantes entraînent des frais supplémentaires :",
        "en": "To ensure smooth processing, the following situations incur additional charges:"},
    "guide_fee_bl": {
        "fr": "Émission d'un BL original",
        "en": "Issuance of one original BL"},
    "guide_fee_amend1": {
        "fr": "1ère modification du brouillon BL",
        "en": "First BL draft amendment"},
    "guide_fee_amend2": {
        "fr": "Modifications suivantes du BL (chacune)",
        "en": "Subsequent BL amendments (each)"},
    "guide_fee_resubmit": {
        "fr": "Re-soumission de la packing list (erreurs)",
        "en": "Packing list resubmission (errors)"},
    "guide_fee_urgent": {
        "fr": "Traitement urgent (< 72h avant départ)",
        "en": "Urgent processing (< 72h before departure)"},
    "guide_fee_late": {
        "fr": "Soumission très tardive (après la date limite)",
        "en": "Very late submission (after deadline)"},
    "guide_fee_reissue": {
        "fr": "Ré-émission du BL (après émission)",
        "en": "BL re-issuance (post-issuance)"},
    "guide_fee_courier_dom": {
        "fr": "Courrier — national",
        "en": "Courier — domestic"},
    "guide_fee_courier_intl": {
        "fr": "Courrier — international",
        "en": "Courier — cross-border"},
    "guide_fee_manifest": {
        "fr": "Modification manifeste/doc. cargo avancé (douanes)",
        "en": "Advanced manifest/cargo doc amendment (customs)"},
    "guide_s7_tip": {
        "fr": "Soumettez vos informations complètes et correctes du premier coup pour éviter tous ces frais !",
        "en": "Submit your information complete and correct the first time to avoid all these fees!"},

    # S8 - US
    "guide_s8_intro": {
        "fr": "Les expéditions à destination des États-Unis sont soumises à des obligations réglementaires supplémentaires.",
        "en": "Shipments to the United States are subject to additional regulatory requirements."},
    "guide_s8_ams": {
        "fr": "L'AMS est déposé par TOWT après la fin du chargement. Aucune action de votre part n'est requise pour l'AMS.",
        "en": "The AMS is filed by TOWT after loading completion. No action is required from you for the AMS."},
    "guide_s8_isf": {
        "fr": "L'ISF (10+2) doit être déposé par votre transitaire ou vous-même. Il comprend : vendeur, acheteur, fabricant, destinataire, description des marchandises, code HTSUS, pays d'origine, etc.",
        "en": "The ISF (10+2) must be filed by your freight forwarder or yourself. It includes: seller, buyer, manufacturer, consignee, goods description, HTSUS code, country of origin, etc."},
    "guide_s8_warning": {
        "fr": "Le non-respect des obligations ISF peut entraîner des pénalités de la part des douanes américaines (CBP). Assurez-vous que votre transitaire est informé.",
        "en": "Failure to comply with ISF requirements may result in penalties from US Customs (CBP). Make sure your freight forwarder is informed."},

    # S9 - FAQ
    "guide_faq1_q": {
        "fr": "Puis-je modifier mes informations après avoir enregistré ?",
        "en": "Can I modify my information after saving?"},
    "guide_faq1_a": {
        "fr": "Oui, tant que la packing list n'a pas été verrouillée par l'exploitation TOWT. Une fois verrouillée, vous devez contacter exploitation@towt.eu pour toute modification.",
        "en": "Yes, as long as the packing list has not been locked by TOWT operations. Once locked, you must contact exploitation@towt.eu for any changes."},
    "guide_faq2_q": {
        "fr": "Que signifient les zones grisées en haut de chaque batch ?",
        "en": "What do the grey areas at the top of each batch mean?"},
    "guide_faq2_a": {
        "fr": "Ce sont les informations voyage pré-remplies par TOWT (navire, ports, dates). Elles ne sont pas modifiables. Si une erreur s'y trouve, contactez TOWT.",
        "en": "These are voyage details pre-filled by TOWT (vessel, ports, dates). They cannot be edited. If there is an error, contact TOWT."},
    "guide_faq3_q": {
        "fr": "Combien de batchs puis-je créer ?",
        "en": "How many batches can I create?"},
    "guide_faq3_a": {
        "fr": "Autant que nécessaire. Créez un batch par lot homogène de marchandises ou par destinataire différent. Le total des palettes doit correspondre à votre commande.",
        "en": "As many as needed. Create one batch per homogeneous lot of goods or per different consignee. The total pallets must match your order."},
    "guide_faq4_q": {
        "fr": "Que se passe-t-il si je ne remplis pas tous les champs obligatoires ?",
        "en": "What happens if I don't fill all mandatory fields?"},
    "guide_faq4_a": {
        "fr": "Votre packing list sera considérée comme incomplète. L'émission du brouillon de Bill of Lading sera retardée et des frais de traitement supplémentaires pourront s'appliquer.",
        "en": "Your packing list will be considered incomplete. The draft Bill of Lading issuance will be delayed and additional processing fees may apply."},
    "guide_faq5_q": {
        "fr": "Mon lien ne fonctionne plus, que faire ?",
        "en": "My link no longer works, what should I do?"},
    "guide_faq5_a": {
        "fr": "Contactez exploitation@towt.eu en indiquant votre référence de commande. Un nouveau lien pourra vous être envoyé.",
        "en": "Contact exploitation@towt.eu with your order reference. A new link can be sent to you."},

    # S10 - Contact
    "guide_s10_p1": {
        "fr": "Pour toute question relative à votre packing list ou à votre expédition, contactez le service exploitation TOWT :",
        "en": "For any questions about your packing list or shipment, contact the TOWT operations department:"},
    "guide_s10_p2": {
        "fr": "Des mises à jour sur l'ETD/ETA de votre voyage sont envoyées chaque semaine à partir de 4 semaines avant le départ.",
        "en": "Weekly ETD/ETA updates for your voyage are sent starting 4 weeks before departure."},
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
