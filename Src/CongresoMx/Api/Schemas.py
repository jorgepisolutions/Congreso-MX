from datetime import date, datetime
from typing import Generic, TypeVar

from pydantic import BaseModel, ConfigDict

T = TypeVar("T")


# Configuracion base que tolera atributos extra (mas resiliente cuando
# extendemos modelos). El from_attributes permite construir desde ORM rows.
class SchemaBase(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="ignore")


# Resumen minimo de un legislador para listados.
class LegisladorResumen(SchemaBase):
    Id: int
    NombreCompleto: str
    Camara: str
    Partido: str | None = None
    Estado: str | None = None
    TipoEleccion: str


# Detalle de un cargo (LegisladorPeriodo) - una persona puede tener varios.
class CargoDetalle(SchemaBase):
    Id: int
    Camara: str
    LegislaturaNumero: str
    Partido: str | None = None
    Estado: str | None = None
    TipoEleccion: str
    Distrito: int | None = None
    Curul: str | None = None
    EsSuplente: bool = False
    Fuente: str | None = None
    IdExterno: str | None = None


# Detalle completo de un legislador (la persona) con todos sus cargos.
class LegisladorDetalle(SchemaBase):
    Id: int
    NombreCompleto: str
    Nombre: str | None = None
    ApellidoPaterno: str | None = None
    ApellidoMaterno: str | None = None
    Genero: str | None = None
    FechaNacimiento: date | None = None
    FotoUrl: str | None = None
    Cargos: list[CargoDetalle] = []


# Entrada del listado de sesiones.
class SesionResumen(SchemaBase):
    Id: int
    Fecha: date
    Camara: str
    Tipo: str
    Estado: str
    Numero: str | None = None


# Detalle de una sesion.
class SesionDetalle(SesionResumen):
    LegislaturaNumero: str | None = None
    PeriodoAnio: int | None = None
    PeriodoNumero: int | None = None
    PeriodoTipo: str | None = None
    HoraInicio: str | None = None
    HoraFin: str | None = None
    QuorumInicial: int | None = None
    QuorumFinal: int | None = None
    UrlGaceta: str | None = None
    UrlActa: str | None = None
    UrlVideo: str | None = None


# Una fila de asistencia. Aplana datos clave del legislador y la sesion.
class AsistenciaEntry(SchemaBase):
    Id: int
    SesionId: int
    Fecha: date
    Camara: str
    NumeroSesion: str | None = None
    TipoSesion: str
    LegisladorId: int
    NombreCompleto: str
    Partido: str | None = None
    Estado: str  # Asistencia.Estado: Presente/Ausente/etc.
    TipoPaseLista: str | None = None
    Fuente: str


# Wrapper paginado.
class PaginatedResponse(SchemaBase, Generic[T]):
    Items: list[T]
    Total: int
    Limit: int
    Offset: int


# Agregado de asistencia por partido + camara.
class StatPorPartido(SchemaBase):
    Camara: str
    Partido: str
    TotalRegistros: int
    Presentes: int
    Ausentes: int
    Justificados: int
    ComisionOficial: int
    Licencia: int
    PctPresencia: float


# Top inasistentes.
class StatInasistente(SchemaBase):
    LegisladorId: int
    NombreCompleto: str
    Camara: str
    Partido: str | None = None
    Estado: str | None = None
    Ausencias: int
    Justificadas: int


# Stub de Votaciones (no tenemos data hoy).
class VotacionEntry(SchemaBase):
    Id: int
    SesionId: int
    Numero: int
    Asunto: str
    Tipo: str
    Resultado: str | None = None


# Respuesta de evento WebSocket. Lo que publicamos al cliente.
class WsAsistenciaEvent(SchemaBase):
    Camara: str
    SesionId: int
    Fecha: str
    Nuevas: int
    Actualizadas: int
    Cambios: int
    Timestamp: str
    PuntoActual: str | None = None


# Resultado del comando CLI api genkey (no es endpoint, pero util tener tipos).
class ApiKeyGenerada(SchemaBase):
    Nombre: str
    Token: str  # Se muestra UNA SOLA VEZ al usuario
    Id: int
    ExpiresAt: datetime | None = None
