def assess(fake, match):
    """Assess risk from fake/match values of True, False, or None."""
    if fake is True and match is True:
        return (
            "HIGH",
            "Voice matches the registered person BUT looks AI-generated. This is the typical voice-cloning pattern.",
        )
    if fake is True:
        return "HIGH", "Voice looks AI-generated."
    if match is False:
        return "HIGH", "Voice does not match the registered person."
    if fake is None or match is None:
        return "MEDIUM", "Could not get a clear result from one of the checks."
    return "LOW", "Voice looks real and matches the registered person."
