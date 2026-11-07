"""Модели БД по спецификации «Схема данных · основные сущности» (9 таблиц).

Отступления от листа схемы (помечены комментарием H-02 / Р-02):
- USER назван app_user: user — зарезервированное слово PostgreSQL;
- CLIENT.first_appearance_date — дата первого появления клиента (Р-02);
- DOCUMENT_SNAPSHOT.is_novice / is_chronic — два других признака модели Б (Р-02).

Ограничения из листа «05 Ограничения»: CL-01..CL-03, SN-01..SN-06, WC-01.
"""
from datetime import date, datetime

from sqlalchemy import (
    BIGINT,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from db import Base


class Client(Base):
    """Клиент (реквизиты и признаки организации)."""

    __tablename__ = "client"
    __table_args__ = (
        # CL-01: код КЦР уникален; CL-03: название обязательно
        UniqueConstraint("kcr_code", name="uq_client_kcr_code"),
    )

    id: Mapped[int] = mapped_column(BIGINT, primary_key=True)
    kcr_code: Mapped[str] = mapped_column(String(64), nullable=False)
    inn: Mapped[str] = mapped_column(String(12), nullable=False)  # CL-02: не уникален
    kpp: Mapped[str | None] = mapped_column(String(9))
    organization_name: Mapped[str] = mapped_column(String(255), nullable=False)
    client_type: Mapped[str | None] = mapped_column(String(50))
    connection_date: Mapped[date | None] = mapped_column(Date)  # для признака «новичок»
    phone: Mapped[str | None] = mapped_column(String(40))
    email: Mapped[str | None] = mapped_column(String(255))
    is_blocked: Mapped[bool | None] = mapped_column(Boolean)
    is_do_not_work: Mapped[bool | None] = mapped_column(Boolean)  # «Не работать», согласовать
    # H-02/Р-02: дата первого появления клиента в срезах
    first_appearance_date: Mapped[date | None] = mapped_column(Date)

    snapshots: Mapped[list["DocumentSnapshot"]] = relationship(back_populates="client")


class DocumentSnapshot(Base):
    """Срез документов: непереданные документы клиента на дату и квартал.

    SN-01: исторические срезы не перезаписываются и не удаляются.
    """

    __tablename__ = "document_snapshot"
    __table_args__ = (
        # SN-02: непереданных не может быть меньше нуля
        CheckConstraint("missing_documents >= 0", name="ck_snapshot_missing_nonneg"),
        # SN-03: непереданные не больше общего числа, когда total известен
        CheckConstraint(
            "total_documents IS NULL OR missing_documents <= total_documents",
            name="ck_snapshot_missing_le_total",
        ),
        # SN-04: один срез клиента на период и дату (повторная загрузка — запрет/версия, на согласование)
        UniqueConstraint("client_id", "reporting_period", "snapshot_date",
                         name="uq_snapshot_client_period_date"),
    )

    id: Mapped[int] = mapped_column(BIGINT, primary_key=True)
    client_id: Mapped[int] = mapped_column(ForeignKey("client.id"), nullable=False)
    import_batch_id: Mapped[int] = mapped_column(ForeignKey("import_batch.id"), nullable=False)
    reporting_period: Mapped[str] = mapped_column(String(20), nullable=False)  # напр. 2026-Q3
    snapshot_date: Mapped[date] = mapped_column(Date, nullable=False)
    total_documents: Mapped[int | None] = mapped_column(Integer)  # SN-05: NULL в повторных срезах
    missing_documents: Mapped[int] = mapped_column(Integer, nullable=False)
    missing_percent: Mapped[float | None] = mapped_column()  # SN-06: NULL при total=0
    # Базовая динамика: NO_COMPARISON / ALL_TRANSFERRED / FIRST_APPEARED /
    # DECREASING / FLAT_OR_GROWING / REAPPEARED (см. scripts/h02/features.py)
    dynamics_code: Mapped[str | None] = mapped_column(String(40))
    # H-02/Р-02: «новичок» и «хронический» — независимые признаки среза
    is_novice: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_chronic: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    client: Mapped["Client"] = relationship(back_populates="snapshots")


class AppUser(Base):
    """Пользователь сервиса: администратор или оператор.

    В схеме назван USER; здесь app_user — user зарезервирован в PostgreSQL.
    """

    __tablename__ = "app_user"

    id: Mapped[int] = mapped_column(BIGINT, primary_key=True)
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    login: Mapped[str] = mapped_column(String(120), nullable=False, unique=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)  # SEC-01
    role: Mapped[str] = mapped_column(String(30), nullable=False)  # ADMIN | OPERATOR
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class WorkCycle(Base):
    """Цикл работы с клиентом (от первого звонка до закрытия)."""

    __tablename__ = "work_cycle"
    __table_args__ = (
        # WC-01: у клиента не больше одного активного цикла —
        # техническая основа атомарного взятия в работу (Р-03, H-09)
        Index(
            "uq_cycle_one_active_per_client", "client_id", unique=True,
            postgresql_where=text("closed_at IS NULL"),
            sqlite_where=text("closed_at IS NULL"),
        ),
    )

    id: Mapped[int] = mapped_column(BIGINT, primary_key=True)
    client_id: Mapped[int] = mapped_column(ForeignKey("client.id"), nullable=False)
    operator_id: Mapped[int | None] = mapped_column(ForeignKey("app_user.id"))
    stage: Mapped[str] = mapped_column(String(60), nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime)
    close_reason: Mapped[str | None] = mapped_column(Text)


class Communication(Base):
    """Коммуникация: звонок, письмо, комментарий; договорённости и срок клиента."""

    __tablename__ = "communication"

    id: Mapped[int] = mapped_column(BIGINT, primary_key=True)
    client_id: Mapped[int] = mapped_column(ForeignKey("client.id"), nullable=False)
    cycle_id: Mapped[int | None] = mapped_column(ForeignKey("work_cycle.id"))
    user_id: Mapped[int] = mapped_column(ForeignKey("app_user.id"), nullable=False)
    contact_type: Mapped[str] = mapped_column(String(30), nullable=False)  # звонок/письмо/комментарий
    result: Mapped[str | None] = mapped_column(String(100))
    comment: Mapped[str | None] = mapped_column(Text)
    promised_date: Mapped[date | None] = mapped_column(Date)  # срок, который назвал клиент
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())


class Task(Base):
    """Задача: запланированное действие и срок."""

    __tablename__ = "task"

    id: Mapped[int] = mapped_column(BIGINT, primary_key=True)
    client_id: Mapped[int] = mapped_column(ForeignKey("client.id"), nullable=False)
    cycle_id: Mapped[int | None] = mapped_column(ForeignKey("work_cycle.id"))
    assigned_user_id: Mapped[int | None] = mapped_column(ForeignKey("app_user.id"))
    task_type: Mapped[str] = mapped_column(String(80), nullable=False)
    due_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="OPEN")


class Claim(Base):
    """Претензия по клиенту."""

    __tablename__ = "claim"

    id: Mapped[int] = mapped_column(BIGINT, primary_key=True)
    client_id: Mapped[int] = mapped_column(ForeignKey("client.id"), nullable=False)
    cycle_id: Mapped[int | None] = mapped_column(ForeignKey("work_cycle.id"))
    claim_number: Mapped[str | None] = mapped_column(String(80))
    claim_date: Mapped[date | None] = mapped_column(Date)
    incident_number: Mapped[str | None] = mapped_column(String(80))
    status: Mapped[str] = mapped_column(String(60), nullable=False)

    sanctions: Mapped[list["Sanction"]] = relationship(back_populates="claim")


class Sanction(Base):
    """Санкция в рамках претензии."""

    __tablename__ = "sanction"

    id: Mapped[int] = mapped_column(BIGINT, primary_key=True)
    claim_id: Mapped[int] = mapped_column(ForeignKey("claim.id"), nullable=False)
    sanction_type: Mapped[str] = mapped_column(String(100), nullable=False)
    status: Mapped[str] = mapped_column(String(60), nullable=False)
    applied_date: Mapped[date | None] = mapped_column(Date)

    claim: Mapped["Claim"] = relationship(back_populates="sanctions")


class ImportBatch(Base):
    """Пакет импорта: история загрузок Excel (IM-01: лог загрузки и ошибок)."""

    __tablename__ = "import_batch"

    id: Mapped[int] = mapped_column(BIGINT, primary_key=True)
    file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    import_type: Mapped[str] = mapped_column(String(30), nullable=False)  # CLIENTS | SNAPSHOTS
    imported_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())
    status: Mapped[str] = mapped_column(String(40), nullable=False)
    created_count: Mapped[int | None] = mapped_column(Integer)
    error_count: Mapped[int | None] = mapped_column(Integer)
