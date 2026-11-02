"""Conservative pre-curation filter for opportunities aimed at Brazil."""

import re
import unicodedata

from buscadin_bot.services.classifier import classify_eligibility
from buscadin_bot.sources.base import RawJob


# Language-targeted roles are not a fit for the initial Brazilian audience by
# default. Portuguese and English remain allowed; the latter is common across
# remote work even though English proficiency is not assumed for publication.
NON_DEFAULT_LANGUAGES = (
    "arabic", "arabe", "bengali", "bulgarian", "cantonese", "chinese", "chines",
    "croatian", "czech", "danish", "dutch", "farsi", "finnish", "french", "frances",
    "german", "alemao", "greek", "hebrew", "hindi", "hungarian", "indonesian",
    "italian", "italiano", "japanese", "japones", "japonesa", "korean", "coreano",
    "mandarin", "norwegian", "persian", "polish", "polones",
    "romanian", "russian", "russo", "serbian", "spanish", "espanol", "swahili",
    "swedish", "tagalog", "tamil", "thai", "turkish", "turco", "ukrainian", "urdu",
    "vietnamese",
)

LANGUAGE_REQUIREMENT = re.compile(
    r"\b(?:native|fluent|fluency|proficient|proficiency|speaker|speaking|bilingual|"
    r"expert|specialist|linguist|language|idioma|fluente|fluencia|nativo|nativa|"
    r"dominio|especialista|falante|requerido|required|must speak|speak)\b"
)


def _plain(value: str) -> str:
    value = unicodedata.normalize("NFKD", value.casefold())
    return "".join(char for char in value if not unicodedata.combining(char))


def brazil_relevance_exclusion(raw: RawJob) -> str | None:
    """Return an exclusion reason, or None when a human should review the job."""
    eligibility, _, _ = classify_eligibility(raw)
    if eligibility == "excluded_br":
        return "A fonte restringe a vaga fora do Brasil ou exclui residentes brasileiros."

    title = _plain(raw.title)
    description = _plain(raw.description)
    explicit_languages = {_plain(item) for item in raw.language_requirements}
    unsupported = next((language for language in NON_DEFAULT_LANGUAGES
                        if any(re.search(rf"\b{re.escape(language)}\b", item)
                               for item in explicit_languages)), None)
    if unsupported:
        return f"Idioma exigido fora do foco inicial: {unsupported}."

    for language in NON_DEFAULT_LANGUAGES:
        match = re.search(rf"\b{re.escape(language)}\b", title)
        if match:
            return f"Vaga direcionada a outro idioma: {language}."

    for language in NON_DEFAULT_LANGUAGES:
        for match in re.finditer(rf"\b{re.escape(language)}\b", description):
            nearby = description[max(0, match.start() - 55):match.end() + 55]
            if LANGUAGE_REQUIREMENT.search(nearby):
                return f"Descrição exige um idioma fora do foco inicial: {language}."

    return None
