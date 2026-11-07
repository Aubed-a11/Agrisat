from datetime import datetime
from sqlalchemy import String, Integer, Float, Boolean, DateTime, ForeignKey, Text, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


def now():
    return datetime.utcnow()


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(60), unique=True)
    full_name: Mapped[str] = mapped_column(String(120))
    role: Mapped[str] = mapped_column(String(20))  # admin, assureur, cooperative, imf, partenaire
    password_hash: Mapped[str] = mapped_column(String(200))
    organisation_id: Mapped[int | None] = mapped_column(Integer, nullable=True)


class Organisation(Base):
    __tablename__ = "organisations"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(160))
    kind: Mapped[str] = mapped_column(String(20))  # cooperative, imf
    commune_id: Mapped[int | None] = mapped_column(Integer, nullable=True)


class Farmer(Base):
    __tablename__ = "farmers"
    id: Mapped[int] = mapped_column(primary_key=True)
    full_name: Mapped[str] = mapped_column(String(160))
    phone: Mapped[str] = mapped_column(String(20), index=True)
    operator: Mapped[str] = mapped_column(String(20), default="mtn")  # mtn, moov, celtiis
    language: Mapped[str] = mapped_column(String(20), default="fr")   # fr, bariba, dendi, ditammari, fon
    commune_id: Mapped[int] = mapped_column(Integer, index=True)
    village: Mapped[str] = mapped_column(String(120), default="")
    cooperative_id: Mapped[int | None] = mapped_column(ForeignKey("organisations.id"), nullable=True)
    gps_lat: Mapped[float | None] = mapped_column(Float, nullable=True)
    gps_lon: Mapped[float | None] = mapped_column(Float, nullable=True)
    consent: Mapped[bool] = mapped_column(Boolean, default=False)
    consent_date: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    is_test_data: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)
    cooperative = relationship("Organisation")


class Credit(Base):
    __tablename__ = "credits"
    id: Mapped[int] = mapped_column(primary_key=True)
    farmer_id: Mapped[int] = mapped_column(ForeignKey("farmers.id"))
    institution_id: Mapped[int] = mapped_column(ForeignKey("organisations.id"))
    amount: Mapped[float] = mapped_column(Float)
    outstanding: Mapped[float] = mapped_column(Float)
    disbursed_at: Mapped[datetime] = mapped_column(DateTime, default=now)
    institution = relationship("Organisation")


class Policy(Base):
    __tablename__ = "policies"
    id: Mapped[int] = mapped_column(primary_key=True)
    number: Mapped[str] = mapped_column(String(30), unique=True)
    farmer_id: Mapped[int] = mapped_column(ForeignKey("farmers.id"), index=True)
    commune_id: Mapped[int] = mapped_column(Integer, index=True)
    crop: Mapped[str] = mapped_column(String(10))
    product: Mapped[str] = mapped_column(String(20), default="indice_pluie")   # indice_pluie, rendement_zone
    coverage: Mapped[float | None] = mapped_column(Float, nullable=True)
    campaign: Mapped[int] = mapped_column(Integer, index=True)
    area_ha: Mapped[float] = mapped_column(Float)
    sum_insured: Mapped[float] = mapped_column(Float)
    premium_total: Mapped[float] = mapped_column(Float)
    premium_farmer: Mapped[float] = mapped_column(Float)
    premium_subsidy: Mapped[float] = mapped_column(Float)
    premium_payment_mode: Mapped[str] = mapped_column(String(20), default="mobile_money")
    premium_paid: Mapped[bool] = mapped_column(Boolean, default=False)
    status: Mapped[str] = mapped_column(String(20), default="en_attente_prime")  # en_attente_prime, active, terminee
    credit_id: Mapped[int | None] = mapped_column(ForeignKey("credits.id"), nullable=True)
    contract_snapshot: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)
    farmer = relationship("Farmer")
    credit = relationship("Credit")


class Payout(Base):
    __tablename__ = "payouts"
    id: Mapped[int] = mapped_column(primary_key=True)
    policy_id: Mapped[int] = mapped_column(ForeignKey("policies.id"), index=True)
    campaign: Mapped[int] = mapped_column(Integer)
    phase: Mapped[int] = mapped_column(Integer)
    index_value: Mapped[float] = mapped_column(Float)
    trigger: Mapped[float] = mapped_column(Float)
    exit: Mapped[float] = mapped_column(Float)
    fraction: Mapped[float] = mapped_column(Float)
    amount: Mapped[float] = mapped_column(Float)
    to_credit: Mapped[float] = mapped_column(Float, default=0.0)
    to_farmer: Mapped[float] = mapped_column(Float, default=0.0)
    data_version: Mapped[str] = mapped_column(String(20), default="definitive")
    status: Mapped[str] = mapped_column(String(20), default="a_valider")  # a_valider, valide, paye, echec, rejete
    validated_by: Mapped[str | None] = mapped_column(String(60), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)
    policy = relationship("Policy")


class Payment(Base):
    __tablename__ = "payments"
    id: Mapped[int] = mapped_column(primary_key=True)
    kind: Mapped[str] = mapped_column(String(20))  # prime, indemnite, remboursement_credit
    reference: Mapped[str] = mapped_column(String(60), index=True)
    policy_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    payout_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    phone: Mapped[str | None] = mapped_column(String(20), nullable=True)
    operator: Mapped[str | None] = mapped_column(String(20), nullable=True)
    amount: Mapped[float] = mapped_column(Float)
    provider: Mapped[str] = mapped_column(String(20))
    status: Mapped[str] = mapped_column(String(20))  # en_cours, reussi, echec
    attempts: Mapped[int] = mapped_column(Integer, default=1)
    message: Mapped[str] = mapped_column(String(255), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=now)


class Claim(Base):
    __tablename__ = "claims"
    id: Mapped[int] = mapped_column(primary_key=True)
    farmer_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    commune_id: Mapped[int] = mapped_column(Integer)
    crop: Mapped[str] = mapped_column(String(10))
    campaign: Mapped[int] = mapped_column(Integer)
    channel: Mapped[str] = mapped_column(String(20), default="agent")
    description: Mapped[str] = mapped_column(Text)
    estimated_loss_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="ouverte")  # ouverte, audit, fondee, non_fondee
    audit_result: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)


class SmsMessage(Base):
    __tablename__ = "sms"
    id: Mapped[int] = mapped_column(primary_key=True)
    farmer_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    phone: Mapped[str] = mapped_column(String(20))
    language: Mapped[str] = mapped_column(String(20))
    channel: Mapped[str] = mapped_column(String(10), default="sms")  # sms, vocal
    category: Mapped[str] = mapped_column(String(30))
    body: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default="envoye")
    provider: Mapped[str] = mapped_column(String(20), default="simulation")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)


class AuditLog(Base):
    __tablename__ = "audit_log"
    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(60))
    action: Mapped[str] = mapped_column(String(60))
    target: Mapped[str] = mapped_column(String(120))
    before: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    after: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)


class Setting(Base):
    __tablename__ = "settings"
    key: Mapped[str] = mapped_column(String(60), primary_key=True)
    value: Mapped[dict] = mapped_column(JSON)
