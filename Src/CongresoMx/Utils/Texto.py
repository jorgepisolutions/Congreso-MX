import hashlib
import re
import unicodedata
from datetime import date

MESES_ES: dict[str, int] = {
    "enero": 1,
    "febrero": 2,
    "marzo": 3,
    "abril": 4,
    "mayo": 5,
    "junio": 6,
    "julio": 7,
    "agosto": 8,
    "septiembre": 9,
    "setiembre": 9,
    "octubre": 10,
    "noviembre": 11,
    "diciembre": 12,
}


# Normaliza un nombre para hashing: sin acentos, lowercase, espacios colapsados.
# Asegura que "Rocío Abreu" y "rocio  abreu" produzcan el mismo hash.
def NormalizarParaHash(Texto: str) -> str:
    SinAcentos = "".join(
        Char for Char in unicodedata.normalize("NFD", Texto)
        if unicodedata.category(Char) != "Mn"
    )
    Lower = SinAcentos.lower().strip()
    return re.sub(r"\s+", " ", Lower)


# SHA-256 hex del nombre normalizado. 64 chars hex.
# Sirve como identificador estable entre fuentes y legislaturas.
def NombreHashSha256(NombreCompleto: str) -> str:
    return hashlib.sha256(NormalizarParaHash(NombreCompleto).encode("utf-8")).hexdigest()


# Parsea fechas en formato espanol del SITL: "DD-mes - YYYY" o variantes
# con espacios alrededor de los separadores. Devuelve None si no parsea.
def ParseFechaEspanol(Texto: str) -> date | None:
    if not Texto:
        return None
    Limpio = " ".join(Texto.lower().split())
    Limpio = re.sub(r"\s*-\s*", "-", Limpio)
    Limpio = Limpio.replace(" ", "-").replace("/", "-").replace("_", "-")
    Partes = Limpio.split("-")
    if len(Partes) != 3:
        return None
    try:
        Dia = int(Partes[0])
        MesNombre = NormalizarParaHash(Partes[1])
        Mes = MESES_ES.get(MesNombre)
        Anio = int(Partes[2])
        if Mes is None:
            return None
        return date(Anio, Mes, Dia)
    except ValueError:
        return None


# Heuristica para partir un nombre hispano completo en (Nombre, ApPaterno, ApMaterno).
# Asume formato "ApellidoPaterno ApellidoMaterno Nombre1 Nombre2..." (orden SITL).
# Para nombres con preposiciones (de la, del, etc.) la heuristica es imperfecta;
# en ese caso devolvemos None en los campos que no quedan claros.
def PartirNombreHispano(NombreCompleto: str) -> tuple[str | None, str | None, str | None]:
    Palabras = NombreCompleto.strip().split()
    if not Palabras:
        return None, None, None
    if len(Palabras) == 1:
        return Palabras[0], None, None
    if len(Palabras) == 2:
        return Palabras[1], Palabras[0], None
    return " ".join(Palabras[2:]), Palabras[0], Palabras[1]
