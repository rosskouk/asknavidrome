from ask_sdk_model.slu.entityresolution.status_code import StatusCode


def get_resolved_slot_value(handler_input, slot_name):
    """
    Returns the canonical resolved value for a given slot if entity
    resolution succeeded, otherwise falls back to the raw spoken value.
    Works for any slot type (built-in or custom).
    """
    slots = handler_input.request_envelope.request.intent.slots
    slot = slots.get(slot_name)

    if slot is None:
        return None
    if slot.resolutions and slot.resolutions.resolutions_per_authority:
        for authority in slot.resolutions.resolutions_per_authority:
            if authority.status.code == StatusCode.ER_SUCCESS_MATCH:
                return authority.values[0].value.name

    return slot.value
    