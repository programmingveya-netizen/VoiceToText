"""
Modul pro detekci zdravotních tvrzení v textu.
Označuje pouze konkrétní závadné fráze, ne celé odstavce.
"""

import re

# Vzory - každý zachytí jen krátkou frázi kolem klíčového výrazu
# Formát: (regex_pattern, popis_důvodu)
# Patterny používají lookaround nebo krátký kontext (max pár slov kolem)

HEALTH_PHRASE_PATTERNS = [
    # "na léčbu [něčeho]"
    (r"na\s+léčbu(?:\s+\w+){0,3}", "léčebné tvrzení"),
    (r"na\s+léčení(?:\s+\w+){0,3}", "léčebné tvrzení"),

    # "léčí / vyléčí [něco]"
    (r"léčí(?:\s+\w+){0,3}", "léčebné tvrzení"),
    (r"vyléčí(?:\s+\w+){0,3}", "léčebné tvrzení"),
    (r"(?:dokáže|může|umí)\s+(?:vy)?léčit(?:\s+\w+){0,3}", "léčebné tvrzení"),
    (r"uzdrav(?:í|uje)(?:\s+\w+){0,3}", "léčebné tvrzení"),

    # "pomáhá při/na/proti [něčem]"
    (r"pomáh[áa]\s+(?:při|na|proti|s)\s+\w+(?:\s+\w+){0,2}", "tvrzení o léčebném účinku"),
    (r"pomůže\s+(?:při|na|proti|s)\s+\w+(?:\s+\w+){0,2}", "tvrzení o léčebném účinku"),

    # "je vhodné/účinné při [diagnóze]"
    (r"(?:je|jsou)\s+(?:vhodn[ýáé]|účinn[ýáé]|prospěšn[ýáé])\s+(?:při|na|proti|pro)\s+\w+(?:\s+\w+){0,2}",
     "tvrzení o vhodnosti při nemoci"),
    (r"(?:je|jsou)\s+doporučen[ýáé]\s+(?:při|na|proti|pro)\s+\w+(?:\s+\w+){0,2}",
     "tvrzení o doporučení při nemoci"),

    # "řeší problém/potíže [s něčím]"
    (r"řeší\s+(?:problém|potíže|obtíže)(?:\s+\w+){0,3}", "tvrzení o řešení zdravotního problému"),
    (r"vyřeší\s+(?:problém|potíže|obtíže)(?:\s+\w+){0,3}", "tvrzení o řešení zdravotního problému"),

    # "odstraní/odstraňuje [něco]"
    (r"odstraň(?:í|uje)\s+\w+(?:\s+\w+){0,2}", "tvrzení o odstranění problému"),
    (r"zmírň(?:í|uje)\s+\w+(?:\s+\w+){0,2}", "tvrzení o zmírnění příznaků"),
    (r"potlačuje\s+\w+(?:\s+\w+){0,2}", "tvrzení o potlačení příznaků"),
    (r"eliminuje\s+\w+(?:\s+\w+){0,2}", "tvrzení o eliminaci problému"),
    (r"zbav(?:í|uje)(?:\s+se)?\s+\w+(?:\s+\w+){0,2}", "tvrzení o zbavení problému"),

    # "zabraňuje / předchází [nemoci]"
    (r"zabraňuje\s+\w+(?:\s+\w+){0,2}", "preventivní zdravotní tvrzení"),
    (r"předchází\s+\w+(?:\s+\w+){0,2}", "preventivní zdravotní tvrzení"),
    (r"chrání\s+před\s+\w+(?:\s+\w+){0,2}", "preventivní zdravotní tvrzení"),
    (r"bojuje\s+proti\s+\w+(?:\s+\w+){0,2}", "tvrzení o boji proti nemoci"),
    (r"působí\s+proti\s+\w+(?:\s+\w+){0,2}", "tvrzení o působení proti nemoci"),

    # Imunita, detox
    (r"posiln?uje\s+imunit\w*", "tvrzení o posílení imunity"),
    (r"posílí\s+imunit\w*", "tvrzení o posílení imunity"),
    (r"zvyšuje\s+(?:imunitu|obranyschopnost)", "tvrzení o posílení imunity"),
    (r"detoxikuje(?:\s+\w+){0,2}", "detoxikační tvrzení"),
    (r"detoxikační(?:\s+\w+){0,2}", "detoxikační tvrzení"),
    (r"očišťuje\s+(?:tělo|organismus|krev|játra)(?:\s+\w+){0,2}", "tvrzení o očistě organismu"),
    (r"očistí\s+(?:tělo|organismus|krev|játra)(?:\s+\w+){0,2}", "tvrzení o očistě organismu"),
    (r"pročistí(?:\s+\w+){0,2}", "tvrzení o očistě organismu"),

    # Snižuje/zvyšuje zdravotní parametry
    (r"snižuje\s+(?:cholesterol|tlak|cukr|hladinu|bolest|zánět)\w*", "tvrzení o snížení zdravotního parametru"),
    (r"sníží\s+(?:cholesterol|tlak|cukr|hladinu|bolest|zánět)\w*", "tvrzení o snížení zdravotního parametru"),
    (r"normalizuje\s+(?:tlak|hladinu|cukr|hormony|trávení|metabolismus)\w*",
     "tvrzení o normalizaci zdravotního parametru"),
    (r"reguluje\s+(?:tlak|hladinu|cukr|hormony|trávení|metabolismus)\w*",
     "tvrzení o regulaci zdravotního parametru"),

    # Přírodní lék
    (r"přírodní\s+(?:lék|léčba|léčivo|antibiotik\w*|alternativa|medicín\w*)", "tvrzení o přírodním léku"),
    (r"zázračn[ýáé]\s+(?:lék|účin\w*|prostředek|přípravek)", "tvrzení o zázračném léku"),
    (r"nahrazuje\s+(?:léky|léčbu|chemoterapii|antibiotik\w*)", "tvrzení o náhradě léčby"),
    (r"místo\s+(?:léků|léčby|antibiotik\w*)", "tvrzení o náhradě léčby"),
    (r"lepší\s+než\s+(?:léky|antibiotik\w*|chemie)", "tvrzení o nadřazenosti nad léky"),

    # Účinkuje na nemoc
    (r"účinkuje\s+(?:na|proti|při)\s+\w+(?:\s+\w+){0,2}", "tvrzení o účinku na nemoc"),
    (r"(?:likviduje|ničí|zabíjí)\s+(?:rakovin\w*|nádor\w*|vir\w*|bakteri\w*|plísn\w*)",
     "tvrzení o likvidaci nemoci"),

    # Klinicky prokázáno
    (r"klinicky\s+(?:prokázan\w*|ověřen\w*|testován\w*)", "nepodložené tvrzení o klinickém ověření"),
    (r"vědecky\s+(?:prokázan\w*|ověřen\w*|dokázan\w*|potvrzena?\w*)", "nepodložené tvrzení o vědeckém ověření"),
    (r"(?:studie|výzkum\w*)\s+(?:prokázal\w*|ukázal\w*|potvrdil\w*)", "nepodložený odkaz na studii"),
    (r"bez\s+vedlejších\s+účinků", "tvrzení o absenci vedlejších účinků"),
    (r"zaručen[ýáé]\s+(?:účin\w*|výsledk\w*)", "tvrzení o zaručených výsledcích"),
    (r"100\s*%\s*(?:účinn\w*|přírodn\w*|bezpečn\w*)", "absolutní zdravotní tvrzení"),
    (r"garantovan[ýáé]\s+(?:účin\w*|výsledk\w*)", "tvrzení o garantovaných výsledcích"),

    # Regenerace
    (r"regeneruje\s+(?:buňky|tkáně|klouby|kůži|organismus)(?:\s+\w+){0,2}", "tvrzení o regeneraci"),
    (r"(?:hojí|zahojí)\s+(?:rány|záněty|kůži|vředy)(?:\s+\w+){0,2}", "tvrzení o hojení"),
    (r"omlazuje(?:\s+\w+){0,2}", "tvrzení o omlazení"),
    (r"zpomaluje\s+stárnutí", "tvrzení o zpomalení stárnutí"),
    (r"proti\s+stárnutí", "anti-aging tvrzení"),
]


def find_health_claims(text: str) -> list[dict]:
    """
    Najde konkrétní zdravotní fráze v textu.
    Vrací seznam s přesnými pozicemi nalezených frází.
    """
    claims = []
    seen_ranges = set()

    text_lower = text.lower()

    for pattern, reason in HEALTH_PHRASE_PATTERNS:
        for match in re.finditer(pattern, text_lower):
            start = match.start()
            end = match.end()

            # Kontrola překryvu - neopakovat stejné místo
            overlap = False
            for s, e in seen_ranges:
                if start < e and end > s:
                    overlap = True
                    break

            if not overlap:
                # Vzít originální text (s velkými písmeny)
                matched_text = text[start:end].strip()
                if matched_text:
                    claims.append({
                        "start": start,
                        "end": end,
                        "text": matched_text,
                        "reason": reason,
                    })
                    seen_ranges.add((start, end))

    # Seřadit podle pozice v textu
    claims.sort(key=lambda c: c["start"])
    return claims
