ALLOWED_DOSSIER_TRANSITIONS = {
    "pending_devis": {"pending_approval", "cancelled"},
    "pending_approval": {"pending_devis", "in_progress", "cancelled"},
    "in_progress": {"paused_pending_approval", "completed", "cancelled", "cancelled_billable"},
    "paused_pending_approval": {"pending_approval", "cancelled", "cancelled_billable"},
    "completed": {"in_progress"},
    "cancelled": set(),
    "cancelled_billable": set(),
}


def transition_dossier_autorisee(statut_actuel: str, nouveau_statut: str) -> bool:
    if statut_actuel == nouveau_statut:
        return True
    return nouveau_statut in ALLOWED_DOSSIER_TRANSITIONS.get(statut_actuel, set())
