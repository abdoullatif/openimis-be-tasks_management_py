import re


SOURCE_LABELS = {
    "payroll": "Paie",
    "payment_plan": "Plan de paiement",
    "beneficiaryservice": "Beneficiaire",
}

TYPE_LABELS = {
    "accept_payroll": "Validation de paie",
    "payment_plan_create": "Creation du plan de paiement",
    "update": "Mise a jour",
    "create": "Creation",
    "delete": "Suppression",
}


def humanize_technical_value(value):
    if not value:
        return "Non renseigne"
    normalized = str(value).replace(".", " ").replace("_", " ")
    normalized = re.sub(r"(?<!^)(?=[A-Z])", " ", normalized)
    normalized = " ".join(normalized.split()).strip()
    if not normalized:
        return "Non renseigne"
    return normalized[:1].upper() + normalized[1:]


def source_label(source):
    if not source:
        return "Non renseigne"
    key = str(source).strip().lower()
    return SOURCE_LABELS.get(key, humanize_technical_value(source))


def type_label(executor_action_event, business_event):
    raw = executor_action_event or ""
    if not raw and business_event and "." in business_event:
        raw = business_event.split(".")[-1]
    key = str(raw).strip().lower() if raw else ""
    if key in TYPE_LABELS:
        return TYPE_LABELS[key]
    return humanize_technical_value(raw or business_event)


def entity_label(source, business_event):
    if source and business_event:
        return f"{source_label(source)} - {type_label(None, business_event)}"
    if source:
        return source_label(source)
    return humanize_technical_value(business_event)

