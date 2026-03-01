from sqlalchemy import (
    Column, Integer, String, Float, DateTime, ForeignKey, Text, Boolean, func
)
from sqlalchemy.orm import relationship
from app.database import Base


class PortConfig(Base):
    __tablename__ = "port_configs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    port_locode = Column(String(5), ForeignKey("ports.locode"), nullable=False, unique=True, index=True)
    accessible = Column(Boolean, default=True)
    port_cost_total = Column(Float, default=0)      # Coût portuaire total (pilotage+remorquage+lamanage+droits)
    cost_per_palette = Column(Float, default=0)      # Coût moyen manutention par palette
    daily_quay_cost = Column(Float, default=0)       # Coût journalier à quai
    notes = Column(Text, nullable=True)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    port = relationship("Port", backref="config", uselist=False)


class OpexParameter(Base):
    __tablename__ = "opex_parameters"

    id = Column(Integer, primary_key=True, autoincrement=True)
    parameter_name = Column(String(100), unique=True, nullable=False)
    parameter_value = Column(Float, nullable=False)
    unit = Column(String(30), nullable=True)
    category = Column(String(50), nullable=True)
    description = Column(Text, nullable=True)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class LegFinance(Base):
    __tablename__ = "leg_finances"

    id = Column(Integer, primary_key=True, autoincrement=True)
    leg_id = Column(Integer, ForeignKey("legs.id"), unique=True, nullable=False)

    revenue_forecast = Column(Float, default=0)
    revenue_actual = Column(Float, default=0)
    sea_cost_forecast = Column(Float, default=0)
    sea_cost_actual = Column(Float, default=0)
    port_cost_forecast = Column(Float, default=0)
    port_cost_actual = Column(Float, default=0)
    quay_cost_forecast = Column(Float, default=0)    # Coût escale (journalier × jours)
    quay_cost_actual = Column(Float, default=0)
    ops_cost_forecast = Column(Float, default=0)
    ops_cost_actual = Column(Float, default=0)
    result_forecast = Column(Float, default=0)
    result_actual = Column(Float, default=0)
    margin_rate_forecast = Column(Float, default=0)
    margin_rate_actual = Column(Float, default=0)

    notes = Column(Text, nullable=True)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    leg = relationship("Leg", back_populates="finance")

    def compute(self):
        total_f = (self.sea_cost_forecast or 0) + (self.port_cost_forecast or 0) + (self.quay_cost_forecast or 0) + (self.ops_cost_forecast or 0)
        total_a = (self.sea_cost_actual or 0) + (self.port_cost_actual or 0) + (self.quay_cost_actual or 0) + (self.ops_cost_actual or 0)
        self.result_forecast = (self.revenue_forecast or 0) - total_f
        self.result_actual = (self.revenue_actual or 0) - total_a
        self.margin_rate_forecast = (self.result_forecast / self.revenue_forecast * 100) if self.revenue_forecast else 0
        self.margin_rate_actual = (self.result_actual / self.revenue_actual * 100) if self.revenue_actual else 0
